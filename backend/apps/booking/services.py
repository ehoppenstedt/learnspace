"""Booking lifecycle: seat holds, checkout, confirmation, approval, cancellation, attendance.

Inventory rule: available = capacity - seats_booked - seats in live holds.
Every write that changes inventory locks the session (or cohort) row with SELECT ... FOR
UPDATE first, so two learners can never both take the last seat. The CHECK constraint
seats_booked <= capacity is the database-level backstop.
"""

import secrets
from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status

from apps.booking.models import Booking, BookingSession, Cancellation, SeatHold
from apps.catalog import services as catalog
from apps.catalog.models import Cohort, Experience, Session
from apps.core.exceptions import DomainError
from apps.payments.pricing import current_fee_bps, price

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
QUOTE_SALT = "cancellation-quote"
QUOTE_TTL_SECONDS = 120


def _code() -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not Booking.objects.filter(code=code).exists():
            return code


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def _target_kwargs(target) -> dict:
    return {"session": target} if isinstance(target, Session) else {"cohort": target}


def _lock_target(*, session_id=None, cohort_id=None):
    model = Session if session_id else Cohort
    pk = session_id or cohort_id
    target = model.objects.select_for_update().select_related("experience").filter(pk=pk).first()
    if target is None:
        raise DomainError("not_found", _("Fecha no encontrada."), status.HTTP_404_NOT_FOUND)
    return target


def _held_seats(target, exclude_hold_id=None) -> int:
    qs = SeatHold.objects.filter(status=SeatHold.Status.ACTIVE, expires_at__gt=timezone.now(), **_target_kwargs(target))
    if exclude_hold_id:
        qs = qs.exclude(pk=exclude_hold_id)
    return qs.aggregate(n=Sum("seats"))["n"] or 0


def available_seats(target) -> int:
    return max(target.capacity - target.seats_booked - _held_seats(target), 0)


def _first_start(target):
    if isinstance(target, Session):
        return target.starts_at
    return target.sessions.filter(status=Session.Status.SCHEDULED).order_by("starts_at").values_list("starts_at", flat=True).first()


def _sessions_of(target) -> list[Session]:
    if isinstance(target, Session):
        return [target]
    return list(target.sessions.filter(status=Session.Status.SCHEDULED).order_by("starts_at"))


def _adjust_counters(target, delta: int) -> None:
    """Change booked seats on a session, or on a cohort and all of its sessions."""
    type(target).objects.filter(pk=target.pk).update(seats_booked=F("seats_booked") + delta)
    if isinstance(target, Cohort):
        Session.objects.filter(cohort=target).update(seats_booked=F("seats_booked") + delta)
    target.refresh_from_db(fields=["seats_booked"])


def _count_seats(booking: Booking) -> bool:
    """Move the booking's seats into seats_booked. False if they're gone (hold expired and sold out)."""
    if booking.seats_counted:
        return True
    target = _lock_target(session_id=booking.session_id, cohort_id=booking.cohort_id)
    hold = SeatHold.objects.select_for_update().filter(pk=booking.hold_id).first() if booking.hold_id else None
    if hold and hold.is_live:
        hold.status = SeatHold.Status.CONVERTED
        hold.save(update_fields=["status", "updated_at"])
    else:
        # The hold lapsed (e.g. slow 3-D Secure). Book only if seats are still free.
        if hold and hold.status == SeatHold.Status.ACTIVE:
            hold.status = SeatHold.Status.EXPIRED
            hold.save(update_fields=["status", "updated_at"])
        if booking.seats > available_seats(target):
            return False
    _adjust_counters(target, booking.seats)
    booking.seats_counted = True
    booking.save(update_fields=["seats_counted", "updated_at"])
    catalog.refresh_denorm(target.experience)
    return True


def _release_seats(booking: Booking) -> None:
    if not booking.seats_counted:
        return
    target = _lock_target(session_id=booking.session_id, cohort_id=booking.cohort_id)
    _adjust_counters(target, -booking.seats)
    booking.seats_counted = False
    booking.save(update_fields=["seats_counted", "updated_at"])
    catalog.refresh_denorm(target.experience)


# ---------------------------------------------------------------------------
# Holds
# ---------------------------------------------------------------------------


@dataclass
class HoldResult:
    hold: SeatHold
    listed_cents: int
    fee_cents: int
    total_cents: int


def create_hold(user, *, seats: int, session_id=None, cohort_id=None) -> HoldResult:
    if bool(session_id) == bool(cohort_id):
        raise DomainError("invalid_target", _("Elige una fecha o un grupo."), status.HTTP_400_BAD_REQUEST)
    if not 1 <= seats <= settings.MAX_SEATS_PER_BOOKING:
        raise DomainError("invalid_seats", _("Puedes reservar de 1 a %(n)s lugares.") % {"n": settings.MAX_SEATS_PER_BOOKING},
                          status.HTTP_400_BAD_REQUEST)
    if not user.profile_complete:
        raise DomainError("profile_incomplete", _("Completa tu perfil para reservar."), status.HTTP_403_FORBIDDEN)
    now = timezone.now()
    with transaction.atomic():
        target = _lock_target(session_id=session_id, cohort_id=cohort_id)
        experience = target.experience
        if experience.status != Experience.Status.LIVE:
            raise DomainError("not_bookable", _("Esta experiencia no está disponible."))
        if experience.provider_id == user.pk:
            raise DomainError("own_experience", _("No puedes reservar tu propia experiencia."))
        if isinstance(target, Session) and (target.cohort_id or target.status != Session.Status.SCHEDULED):
            raise DomainError("not_bookable", _("Esta fecha no se puede reservar por separado."))
        start = _first_start(target)
        if start is None or start <= now:
            raise DomainError("already_started", _("Esta fecha ya comenzó."))
        kw = _target_kwargs(target)
        # One live hold per learner per date: a new hold replaces the old one.
        SeatHold.objects.filter(user=user, status=SeatHold.Status.ACTIVE, **kw).update(status=SeatHold.Status.RELEASED)
        SeatHold.objects.filter(status=SeatHold.Status.ACTIVE, expires_at__lte=now, **kw).update(status=SeatHold.Status.EXPIRED)
        available = available_seats(target)
        if seats > available:
            raise DomainError("seat_unavailable", _("Ya no hay suficientes lugares."), fields={"available": available})
        hold = SeatHold.objects.create(
            user=user, experience=experience, seats=seats, expires_at=now + timedelta(minutes=settings.SEAT_HOLD_MINUTES), **kw
        )
    quote = price(experience.listed_price_cents, current_fee_bps(), seats)
    return HoldResult(hold, quote.listed_cents, quote.fee_cents, quote.total_cents)


def release_hold(user, hold_id) -> None:
    SeatHold.objects.filter(pk=hold_id, user=user, status=SeatHold.Status.ACTIVE).update(status=SeatHold.Status.RELEASED)


def expire_holds() -> int:
    return SeatHold.objects.filter(status=SeatHold.Status.ACTIVE, expires_at__lte=timezone.now()).update(
        status=SeatHold.Status.EXPIRED
    )


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


def _policy_snapshot(experience: Experience) -> dict:
    policy = experience.cancellation_policy
    return {
        "code": policy.code,
        "name_es": policy.name_es,
        "name_en": policy.name_en,
        "rules": [
            {"applies_to": r.applies_to, "min_hours_before": r.min_hours_before, "max_hours_before": r.max_hours_before,
             "listed_refund_pct": r.listed_refund_pct, "refund_fee": r.refund_fee}
            for r in policy.rules.all()
        ],
    }


def needs_approval(experience: Experience, learner) -> bool:
    threshold = experience.requires_approval_below
    score = getattr(getattr(learner, "learner_profile", None), "conduct_score", None)
    # Learners without a score yet are not penalized.
    return threshold is not None and score is not None and Decimal(score) < Decimal(threshold)


def start_checkout(user, hold_id):
    """Creates the booking for a live hold and a payment at the gateway. Idempotent per hold."""
    from apps.payments import services as payments

    with transaction.atomic():
        hold = SeatHold.objects.select_for_update(of=("self",)).select_related("experience__cancellation_policy").filter(pk=hold_id, user=user).first()
        if hold is None:
            raise DomainError("hold_not_found", _("Reserva temporal no encontrada."), status.HTTP_404_NOT_FOUND)
        existing = Booking.objects.filter(hold=hold).first()
        if existing:
            return existing, payments.existing_checkout(existing)
        if not hold.is_live:
            raise DomainError("hold_expired", _("Se acabó el tiempo para pagar. Vuelve a elegir tus lugares."), status.HTTP_410_GONE)
        experience = hold.experience
        target = hold.session or hold.cohort
        sessions = _sessions_of(target)
        quote = price(experience.listed_price_cents, current_fee_bps(), hold.seats)
        booking = Booking.objects.create(
            code=_code(), learner=user, experience=experience, session=hold.session, cohort=hold.cohort, hold=hold,
            seats=hold.seats, listed_cents=quote.listed_cents, fee_cents=quote.fee_cents, total_cents=quote.total_cents,
            fee_bps_snapshot=quote.fee_bps, policy_snapshot=_policy_snapshot(experience),
            starts_at=sessions[0].starts_at, ends_at=sessions[-1].ends_at,
        )
        BookingSession.objects.bulk_create([BookingSession(booking=booking, session=s) for s in sessions])
        capture_manual = needs_approval(experience, user)
    checkout = payments.start_payment(booking, capture_manual=capture_manual)
    return booking, checkout


# ---------------------------------------------------------------------------
# Payment outcomes (called from webhook processing)
# ---------------------------------------------------------------------------


def _transfer_release_at(booking: Booking):
    first = booking.booking_sessions.select_related("session").order_by("session__starts_at").first()
    end = first.session.ends_at if first else booking.ends_at
    return end + timedelta(hours=settings.TRANSFER_DELAY_HOURS)


def _context(booking: Booking, **extra) -> dict:
    local = timezone.localtime(booking.starts_at)
    return {"title": booking.experience.title, "code": booking.code, "booking_id": str(booking.pk),
            "when": local.strftime("%d/%m %H:%M"), "time": local.strftime("%H:%M"),
            "seats": booking.seats, "learner": booking.learner.first_name, **extra}


def _notify(user, kind, booking, *, suffix="", **extra):
    from apps.notifications.services import notify

    notify(user, kind, _context(booking, **extra), dedupe=f"{kind}:{booking.pk}{suffix}")


def _sold_out(booking: Booking, payment) -> None:
    from apps.payments import services as payments

    booking.status = Booking.Status.CANCELLED
    booking.save(update_fields=["status", "updated_at"])
    cancellation = Cancellation.objects.create(
        booking=booking, actor_role=Cancellation.Actor.SYSTEM, hours_before_start=_hours_before(booking),
        rule_snapshot={"reason": "sold_out"}, listed_refund_cents=booking.listed_cents, fee_refund_cents=booking.fee_cents,
        refund_cents=booking.total_cents, reason_code="sold_out",
    )
    if payment.status == payment.Status.AUTHORIZED:
        payments.release_authorization(payment)
    else:
        payments.refund_payment(payment, listed_cents=booking.listed_cents, fee_cents=booking.fee_cents,
                                reason="sold_out", cancellation=cancellation)
    _notify(booking.learner, "sold_out_refund", booking, refund=_money(booking.total_cents))


def on_payment_captured(payment) -> None:
    """Money is captured: confirm (auto-capture) or finish an approved booking."""
    from apps.payments import services as payments

    booking = Booking.objects.select_for_update().get(pk=payment.booking_id)
    if booking.status in (Booking.Status.PENDING_PAYMENT, Booking.Status.PAYMENT_FAILED):
        if not _count_seats(booking):
            return _sold_out(booking, payment)
    elif booking.status != Booking.Status.PENDING_APPROVAL:
        return  # already confirmed/cancelled: duplicate or late event
    booking.status = Booking.Status.CONFIRMED
    booking.confirmed_at = timezone.now()
    booking.save(update_fields=["status", "confirmed_at", "updated_at"])
    payments.schedule_transfer(booking, release_at=_transfer_release_at(booking))
    _notify(booking.learner, "booking_confirmed", booking, ics=booking_ics(booking))
    _notify(booking.experience.provider.user, "booking_new_for_provider", booking)


def on_payment_authorized(payment) -> None:
    """Card authorized but not captured: the provider must approve within the window."""
    booking = Booking.objects.select_for_update().get(pk=payment.booking_id)
    if booking.status != Booking.Status.PENDING_PAYMENT:
        return
    if not _count_seats(booking):
        return _sold_out(booking, payment)
    window_end = timezone.now() + timedelta(hours=settings.APPROVAL_WINDOW_HOURS)
    booking.status = Booking.Status.PENDING_APPROVAL
    booking.approval_deadline = min(window_end, booking.starts_at - timedelta(hours=1))
    booking.save(update_fields=["status", "approval_deadline", "updated_at"])
    deadline = timezone.localtime(booking.approval_deadline).strftime("%d/%m %H:%M")
    _notify(booking.experience.provider.user, "approval_requested", booking, deadline=deadline)
    _notify(booking.learner, "approval_pending_learner", booking)


def on_payment_failed(payment) -> None:
    booking = Booking.objects.select_for_update().get(pk=payment.booking_id)
    if booking.status == Booking.Status.PENDING_PAYMENT:
        booking.status = Booking.Status.PAYMENT_FAILED
        booking.save(update_fields=["status", "updated_at"])
        _notify(booking.learner, "payment_failed", booking)


# ---------------------------------------------------------------------------
# Provider approval
# ---------------------------------------------------------------------------


def _provider_booking(provider_user, booking_id) -> Booking:
    booking = Booking.objects.select_for_update().select_related("experience").filter(
        pk=booking_id, experience__provider_id=provider_user.pk
    ).first()
    if booking is None:
        raise DomainError("not_found", _("Reserva no encontrada."), status.HTTP_404_NOT_FOUND)
    return booking


def approve(provider_user, booking_id) -> Booking:
    from apps.payments import services as payments

    with transaction.atomic():
        booking = _provider_booking(provider_user, booking_id)
        if booking.status != Booking.Status.PENDING_APPROVAL:
            raise DomainError("not_pending", _("Esta reserva ya no está pendiente."))
        payment = payments.capture(booking)
        on_payment_captured(payment)
    booking.refresh_from_db()
    return booking


def decline(booking_id, *, provider_user=None, reason="declined") -> Booking:
    from apps.payments import services as payments

    with transaction.atomic():
        if provider_user:
            booking = _provider_booking(provider_user, booking_id)
        else:
            booking = Booking.objects.select_for_update().get(pk=booking_id)
        if booking.status != Booking.Status.PENDING_APPROVAL:
            raise DomainError("not_pending", _("Esta reserva ya no está pendiente."))
        _release_seats(booking)
        booking.status = Booking.Status.DECLINED
        booking.save(update_fields=["status", "updated_at"])
        payment = booking.payments.order_by("-created_at").first()
        if payment:
            payments.release_authorization(payment)
        _notify(booking.learner, "approval_declined", booking)
    return booking


def expire_approvals() -> int:
    ids = list(Booking.objects.filter(status=Booking.Status.PENDING_APPROVAL, approval_deadline__lte=timezone.now())
               .values_list("pk", flat=True))
    for pk in ids:
        try:
            decline(pk, reason="timeout")
        except DomainError:
            continue
    return len(ids)


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def _hours_before(booking, now=None) -> Decimal:
    seconds = (booking.starts_at - (now or timezone.now())).total_seconds()
    return Decimal(seconds / 3600).quantize(Decimal("0.01"))


def _pct(amount: int, pct: int) -> int:
    return (amount * pct + 50) // 100  # round half up


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f} MXN"


@dataclass(frozen=True)
class Quote:
    booking_id: str
    listed_refund_cents: int
    fee_refund_cents: int
    refund_cents: int
    hours_before_start: str
    rule: dict
    not_charged: bool = False


def quote_cancellation(booking: Booking, now=None) -> Quote:
    now = now or timezone.now()
    if booking.status == Booking.Status.PENDING_APPROVAL:
        # Card was only authorized: cancelling releases it; nothing to refund.
        return Quote(str(booking.pk), 0, 0, 0, str(_hours_before(booking, now)), {"reason": "authorization_released"}, True)
    if booking.status != Booking.Status.CONFIRMED:
        raise DomainError("not_cancellable", _("Esta reserva no se puede cancelar."))
    if now >= booking.starts_at:
        raise DomainError("already_started", _("La clase ya comenzó; ya no se puede cancelar."))
    hours = (booking.starts_at - now).total_seconds() / 3600
    rule = next(
        (r for r in booking.policy_snapshot["rules"]
         if r["applies_to"] == "learner_cancel" and r["min_hours_before"] <= hours
         and (r["max_hours_before"] is None or hours < r["max_hours_before"])),
        None,
    )
    if rule is None:  # policies are validated in admin; this is defensive
        rule = {"applies_to": "learner_cancel", "listed_refund_pct": 0, "refund_fee": False}
    listed = _pct(booking.listed_cents, rule["listed_refund_pct"])
    fee = booking.fee_cents if rule["refund_fee"] else 0
    return Quote(str(booking.pk), listed, fee, listed + fee, f"{hours:.2f}", rule)


def sign_quote(quote: Quote) -> str:
    return signing.dumps({"b": quote.booking_id, "l": quote.listed_refund_cents, "f": quote.fee_refund_cents}, salt=QUOTE_SALT)


def cancel_by_learner(user, booking_id, quote_token: str) -> Cancellation:
    try:
        signed = signing.loads(quote_token, salt=QUOTE_SALT, max_age=QUOTE_TTL_SECONDS)
    except signing.BadSignature:
        raise DomainError("quote_expired", _("El cálculo del reembolso expiró. Revísalo de nuevo."))
    with transaction.atomic():
        booking = Booking.objects.select_for_update().filter(pk=booking_id, learner=user).first()
        if booking is None or signed["b"] != str(booking.pk):
            raise DomainError("not_found", _("Reserva no encontrada."), status.HTTP_404_NOT_FOUND)
        quote = quote_cancellation(booking)
        # The learner is never refunded a different amount than the one they confirmed.
        if (quote.listed_refund_cents, quote.fee_refund_cents) != (signed["l"], signed["f"]):
            raise DomainError("quote_changed", _("El reembolso cambió porque pasó el plazo. Revísalo de nuevo."))
        cancellation = _apply_cancellation(booking, quote, actor=user, role=Cancellation.Actor.LEARNER, reason_code="learner_request")
    _notify(booking.learner, "booking_cancelled_learner", booking, refund=_money(quote.refund_cents))
    _notify(booking.experience.provider.user, "booking_cancelled_for_provider", booking)
    return cancellation


def _apply_cancellation(booking, quote: Quote, *, actor, role, reason_code, note="") -> Cancellation:
    from apps.payments import services as payments

    cancellation = Cancellation.objects.create(
        booking=booking, actor=actor, actor_role=role, hours_before_start=Decimal(quote.hours_before_start),
        rule_snapshot=quote.rule, listed_refund_cents=quote.listed_refund_cents, fee_refund_cents=quote.fee_refund_cents,
        refund_cents=quote.refund_cents, reason_code=reason_code, note=note,
    )
    was_authorized_only = booking.status == Booking.Status.PENDING_APPROVAL
    _release_seats(booking)
    booking.status = Booking.Status.CANCELLED
    booking.save(update_fields=["status", "updated_at"])
    payment = booking.payments.filter(status__in=["succeeded", "partially_refunded", "authorized"]).order_by("-created_at").first()
    if payment and was_authorized_only:
        payments.release_authorization(payment)
    elif payment and quote.refund_cents:
        payments.refund_payment(payment, listed_cents=quote.listed_refund_cents, fee_cents=quote.fee_refund_cents,
                                reason=reason_code, cancellation=cancellation)
    elif payment:
        payments.recompute_transfer(booking)
    return cancellation


def full_refund_quote(booking: Booking, reason: str) -> Quote:
    return Quote(str(booking.pk), booking.listed_cents, booking.fee_cents, booking.total_cents,
                 str(_hours_before(booking)), {"reason": reason, "listed_refund_pct": 100, "refund_fee": True},
                 booking.status == Booking.Status.PENDING_APPROVAL)


def cancel_by_provider(provider_user, *, session_id=None, cohort_id=None, reason: str = "") -> int:
    """Provider cancels a date (or a whole course group): everyone gets 100% back, fee included."""
    with transaction.atomic():
        target = _lock_target(session_id=session_id, cohort_id=cohort_id)
        if target.experience.provider_id != provider_user.pk:
            raise DomainError("not_found", _("Fecha no encontrada."), status.HTTP_404_NOT_FOUND)
        if isinstance(target, Session) and target.cohort_id:
            raise DomainError("cohort_session", _("Para cursos, cancela el grupo completo."))
        if _first_start(target) is None or _first_start(target) <= timezone.now():
            raise DomainError("already_started", _("Ya comenzó; contacta a soporte."))
        bookings = list(Booking.objects.select_for_update().filter(
            Q(status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING_APPROVAL]), **_target_kwargs(target)))
        for booking in bookings:
            _apply_cancellation(booking, full_refund_quote(booking, "provider_cancelled"), actor=provider_user,
                                role=Cancellation.Actor.PROVIDER, reason_code="provider_cancelled", note=reason)
        SeatHold.objects.filter(status=SeatHold.Status.ACTIVE, **_target_kwargs(target)).update(status=SeatHold.Status.RELEASED)
        for session in _sessions_of(target):
            session.status = Session.Status.CANCELLED
            session.save(update_fields=["status", "updated_at"])
        catalog.refresh_denorm(target.experience)
        if bookings:
            _penalize(target.experience.provider)
    for booking in bookings:
        _notify(booking.learner, "session_cancelled_by_provider", booking, refund=_money(booking.total_cents))
    return len(bookings)


def _penalize(provider) -> None:
    from apps.accounts.models import ProviderProfile

    ProviderProfile.objects.filter(pk=provider.pk).update(penalty_points=F("penalty_points") + 1)
    since = timezone.now() - timedelta(days=90)
    recent = (
        Cancellation.objects.filter(actor_role=Cancellation.Actor.PROVIDER, booking__experience__provider=provider,
                                    cancelled_at__gte=since)
        .values("booking__session_id", "booking__cohort_id").distinct().count()
    )
    if recent >= settings.PROVIDER_PENALTY_PAUSE_THRESHOLD:
        Experience.objects.filter(provider=provider, status=Experience.Status.LIVE).update(status=Experience.Status.PAUSED)


# ---------------------------------------------------------------------------
# Attendance, completion, reminders
# ---------------------------------------------------------------------------


def mark_attendance(provider_user, session_id, marks: list[dict]) -> list[BookingSession]:
    now = timezone.now()
    with transaction.atomic():
        session = Session.objects.select_related("experience").filter(pk=session_id, experience__provider_id=provider_user.pk).first()
        if session is None:
            raise DomainError("not_found", _("Fecha no encontrada."), status.HTTP_404_NOT_FOUND)
        if not session.starts_at <= now <= session.ends_at + timedelta(hours=settings.ATTENDANCE_WINDOW_HOURS):
            raise DomainError("attendance_closed", _("La asistencia se registra desde el inicio hasta 48 horas después."))
        updated = []
        for mark in marks:
            bs = BookingSession.objects.select_for_update().select_related("booking").filter(
                session=session, booking_id=mark["booking_id"],
                booking__status__in=[Booking.Status.CONFIRMED, Booking.Status.COMPLETED, Booking.Status.NO_SHOW],
            ).first()
            if bs is None:
                continue
            bs.attendance, bs.marked_by, bs.marked_at = mark["attendance"], provider_user, now
            bs.save(update_fields=["attendance", "marked_by", "marked_at"])
            _sync_no_show(bs.booking)
            updated.append(bs)
    return updated


def _sync_no_show(booking: Booking) -> None:
    """A booking is a no-show when every one of its sessions so far was marked absent."""
    marks = list(booking.booking_sessions.exclude(attendance=BookingSession.Attendance.UNKNOWN).values_list("attendance", flat=True))
    all_absent = bool(marks) and all(m == BookingSession.Attendance.ABSENT for m in marks)
    if all_absent and booking.status in (Booking.Status.CONFIRMED, Booking.Status.COMPLETED):
        booking.status = Booking.Status.NO_SHOW
    elif not all_absent and booking.status == Booking.Status.NO_SHOW:
        booking.status = Booking.Status.COMPLETED if booking.ends_at <= timezone.now() else Booking.Status.CONFIRMED
    booking.save(update_fields=["status", "updated_at"])


def dispute_no_show(user, booking_id, details: str):
    from apps.moderation.models import Report
    from apps.payments.models import Transfer

    with transaction.atomic():
        booking = Booking.objects.select_for_update().filter(pk=booking_id, learner=user).first()
        if booking is None or booking.status != Booking.Status.NO_SHOW:
            raise DomainError("not_disputable", _("Solo puedes disputar una inasistencia registrada."))
        last_mark = booking.booking_sessions.exclude(marked_at=None).order_by("-marked_at").values_list("marked_at", flat=True).first()
        if last_mark and timezone.now() > last_mark + timedelta(hours=settings.NO_SHOW_DISPUTE_HOURS):
            raise DomainError("dispute_window_closed", _("El plazo para disputar terminó."))
        Transfer.objects.filter(booking=booking, status=Transfer.Status.SCHEDULED).update(
            status=Transfer.Status.ON_HOLD, hold_reason="no_show_dispute")
        return Report.objects.create(reporter=user, target_type="booking", target_id=str(booking.pk),
                                     reason_code="no_show_dispute", details=details[:2000])


def complete_finished() -> int:
    """Mark finished classes completed and open the review window (with prompts to both sides)."""
    from apps.reviews.services import notify_window_opened

    now = timezone.now()
    ids = list(Booking.objects.filter(status=Booking.Status.CONFIRMED, ends_at__lte=now).values_list("pk", flat=True))
    Booking.objects.filter(pk__in=ids).update(
        status=Booking.Status.COMPLETED, review_window_closes_at=F("ends_at") + timedelta(days=settings.REVIEW_WINDOW_DAYS))
    for booking in Booking.objects.filter(pk__in=ids).select_related("experience__provider__user", "learner"):
        notify_window_opened(booking)
    return len(ids)


def expire_unpaid() -> int:
    """Checkouts abandoned well past the hold: mark failed so they leave the learner's list."""
    cutoff = timezone.now() - timedelta(minutes=settings.SEAT_HOLD_MINUTES + 20)
    return Booking.objects.filter(status=Booking.Status.PENDING_PAYMENT, created_at__lte=cutoff).update(
        status=Booking.Status.PAYMENT_FAILED)


def send_reminders() -> int:
    now = timezone.now()
    sent = 0
    for kind, lead in (("reminder_24h", timedelta(hours=24)), ("reminder_2h", timedelta(hours=2))):
        due = Booking.objects.filter(
            status=Booking.Status.CONFIRMED, starts_at__gt=now + lead - timedelta(minutes=20), starts_at__lte=now + lead,
        ).select_related("experience__space", "learner")
        for booking in due:
            space = booking.experience.space
            where = booking.experience.online_url if booking.experience.modality == "online" else (space.address_line if space else "")
            _notify(booking.learner, kind, booking, address=where or "")
            sent += 1
    return sent


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


def booking_ics(booking: Booking) -> str:
    from apps.booking.ics import build_ics

    space = booking.experience.space
    events = [(bs.session.starts_at, bs.session.ends_at) for bs in booking.booking_sessions.select_related("session").order_by("session__starts_at")]
    if booking.experience.modality == "online":
        location = booking.experience.online_url or ""
    else:
        location = f"{space.address_line}, {space.neighborhood}, {space.city}" if space else ""
    return build_ics(uid=booking.code, events=events, summary=booking.experience.title,
                     description=f"{settings.BRAND_NAME} · {booking.code} · {booking.seats} lugar(es)", location=location)


def quote_as_dict(quote: Quote) -> dict:
    data = asdict(quote)
    data["quote_token"] = sign_quote(quote)
    data["valid_for_seconds"] = QUOTE_TTL_SECONDS
    return data
