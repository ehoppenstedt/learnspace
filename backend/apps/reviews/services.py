"""Two-way, double-blind reviews.

Window: opens when the booking's last session ends, closes 14 days later.
Reveal: both sides' entries become visible when the second one is submitted, or when the
window closes (whatever exists then). Nobody can see the other side's rating before
writing their own, so ratings can't be retaliatory.
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status

from apps.booking.models import Booking
from apps.catalog.models import Experience
from apps.core.exceptions import DomainError
from apps.reviews.models import ConductAppeal, ConductRating, Review

# A no-show neither reviews the class nor gets a conduct rating: nobody was there to rate.
LEARNER_REVIEWABLE = {Booking.Status.CONFIRMED, Booking.Status.COMPLETED}
PROVIDER_RATEABLE = LEARNER_REVIEWABLE


def window(booking: Booking) -> tuple:
    return booking.ends_at, booking.ends_at + timedelta(days=settings.REVIEW_WINDOW_DAYS)


def window_open(booking: Booking, now=None) -> bool:
    now = now or timezone.now()
    opens, closes = window(booking)
    return opens <= now < closes


def _two(value) -> Decimal | None:
    return None if value is None else Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _check_window(booking: Booking) -> None:
    opens, closes = window(booking)
    now = timezone.now()
    if now < opens:
        raise DomainError("review_not_open", _("Podrás calificar cuando termine la clase."))
    if now >= closes:
        raise DomainError("review_closed", _("El plazo de 14 días para calificar terminó."))


def submit_review(learner, booking_id, data: dict) -> Review:
    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related("experience").filter(pk=booking_id, learner=learner).first()
        if booking is None:
            raise DomainError("not_found", _("Reserva no encontrada."), status.HTTP_404_NOT_FOUND)
        if booking.status not in LEARNER_REVIEWABLE:
            raise DomainError("not_reviewable", _("Solo puedes calificar clases a las que asististe."))
        _check_window(booking)
        if Review.objects.filter(booking=booking).exists():
            raise DomainError("already_reviewed", _("Ya calificaste esta clase."))
        in_person = booking.experience.modality == Experience.Modality.IN_PERSON
        if in_person and not data.get("facilities"):
            raise DomainError("facilities_required", _("Califica las instalaciones."), status.HTTP_400_BAD_REQUEST)
        review = Review.objects.create(
            booking=booking, experience=booking.experience, author=learner,
            overall=data["overall"], learning=data["learning"], facilitator=data["facilitator"],
            facilities=data.get("facilities") if in_person else None,
            public_text=data.get("public_text", "").strip(), private_feedback=data.get("private_feedback", "").strip(),
        )
        _maybe_reveal(booking)
    review.refresh_from_db()
    return review


def submit_conduct_rating(provider_user, booking_id, data: dict) -> ConductRating:
    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related("experience").filter(
            pk=booking_id, experience__provider_id=provider_user.pk).first()
        if booking is None:
            raise DomainError("not_found", _("Reserva no encontrada."), status.HTTP_404_NOT_FOUND)
        if booking.status not in PROVIDER_RATEABLE:
            raise DomainError("not_rateable", _("Esta reserva no se puede calificar."))
        _check_window(booking)
        if ConductRating.objects.filter(booking=booking).exists():
            raise DomainError("already_rated", _("Ya calificaste a este alumno."))
        rating = ConductRating.objects.create(
            booking=booking, learner=booking.learner, provider=booking.experience.provider,
            respect=data["respect"], punctuality=data["punctuality"], admin_note=data.get("admin_note", "").strip(),
        )
        _maybe_reveal(booking)
    rating.refresh_from_db()
    return rating


def _maybe_reveal(booking: Booking, force=False) -> bool:
    review = Review.objects.filter(booking=booking, revealed_at__isnull=True).first()
    rating = ConductRating.objects.filter(booking=booking, revealed_at__isnull=True).first()
    both = Review.objects.filter(booking=booking).exists() and ConductRating.objects.filter(booking=booking).exists()
    if not (both or force) or not (review or rating):
        return False
    now = timezone.now()
    if review:
        review.revealed_at = now
        review.save(update_fields=["revealed_at", "updated_at"])
        recompute_experience_rating(booking.experience)
    if rating:
        rating.revealed_at = now
        rating.save(update_fields=["revealed_at", "updated_at"])
        recompute_conduct(booking.learner)
    _notify_revealed(booking, review, rating)
    return True


def reveal_closed_windows(now=None) -> int:
    """Hourly job: reveal whatever was submitted once the 14-day window closes."""
    now = now or timezone.now()
    cutoff = now - timedelta(days=settings.REVIEW_WINDOW_DAYS)
    bookings = Booking.objects.filter(ends_at__lte=cutoff).filter(
        Q(review__revealed_at__isnull=True, review__isnull=False)
        | Q(conduct_rating__revealed_at__isnull=True, conduct_rating__isnull=False)
    ).distinct()
    count = 0
    for booking in bookings:
        with transaction.atomic():
            count += _maybe_reveal(booking, force=True)
    return count


def recompute_experience_rating(experience: Experience) -> None:
    visible = Review.objects.filter(experience=experience, revealed_at__isnull=False, moderation=Review.Moderation.VISIBLE)
    agg = visible.aggregate(avg=Avg("overall"), n=Count("id"))
    Experience.objects.filter(pk=experience.pk).update(rating_avg=_two(agg["avg"]), rating_count=agg["n"])
    provider = experience.provider
    pagg = Review.objects.filter(experience__provider=provider, revealed_at__isnull=False,
                                 moderation=Review.Moderation.VISIBLE).aggregate(avg=Avg("overall"), n=Count("id"))
    type(provider).objects.filter(pk=provider.pk).update(rating_avg=_two(pagg["avg"]), rating_count=pagg["n"])


def sync_no_show(booking: Booking) -> None:
    """Attendance can be marked after the host already rated: a no-show's rating stops counting,
    and counts again if the mark is corrected (unless an appeal overturned it)."""
    rating = ConductRating.objects.filter(booking=booking).first()
    if rating is None:
        return
    excluded = booking.status == Booking.Status.NO_SHOW or rating.appeals.filter(status=ConductAppeal.Status.OVERTURNED).exists()
    if rating.excluded != excluded:
        rating.excluded = excluded
        rating.save(update_fields=["excluded", "updated_at"])
        recompute_conduct(booking.learner)


def recompute_conduct(learner) -> None:
    from apps.accounts.models import LearnerProfile

    ratings = ConductRating.objects.filter(learner=learner, revealed_at__isnull=False, excluded=False)
    scores = [r.score for r in ratings]
    LearnerProfile.objects.filter(user=learner).update(
        conduct_score=_two(sum(scores) / len(scores)) if scores else None, conduct_count=len(scores))


def summary(experience: Experience) -> dict:
    visible = Review.objects.filter(experience=experience, revealed_at__isnull=False, moderation=Review.Moderation.VISIBLE)
    agg = visible.aggregate(overall=Avg("overall"), learning=Avg("learning"), facilitator=Avg("facilitator"),
                            facilities=Avg("facilities"), count=Count("id"))
    return {k: (str(_two(v)) if v is not None and k != "count" else v) for k, v in agg.items()}


def pending_for(user) -> dict:
    """What this user still owes: reviews (as learner) and conduct ratings (as provider)."""
    now = timezone.now()
    open_q = Q(ends_at__lte=now, ends_at__gt=now - timedelta(days=settings.REVIEW_WINDOW_DAYS))
    learner = Booking.objects.filter(open_q, learner=user, status__in=LEARNER_REVIEWABLE, review__isnull=True)
    provider = Booking.objects.none()
    if hasattr(user, "provider_profile"):
        provider = Booking.objects.filter(open_q, experience__provider_id=user.pk, status__in=PROVIDER_RATEABLE,
                                          conduct_rating__isnull=True)
    return {"reviews": learner.select_related("experience"), "conduct_ratings": provider.select_related("experience", "learner")}


# ---------------------------------------------------------------------------
# Appeals and moderation
# ---------------------------------------------------------------------------


def appeal(learner, rating_id, statement: str) -> ConductAppeal:
    rating = ConductRating.objects.filter(pk=rating_id, learner=learner, revealed_at__isnull=False).first()
    if rating is None:
        raise DomainError("not_found", _("Calificación no encontrada."), status.HTTP_404_NOT_FOUND)
    if rating.excluded or rating.appeals.exists():
        raise DomainError("already_appealed", _("Esta calificación ya fue apelada."))
    if len(statement.strip()) < 20:
        raise DomainError("statement_too_short", _("Explica qué pasó (mínimo 20 caracteres)."), status.HTTP_400_BAD_REQUEST)
    return ConductAppeal.objects.create(rating=rating, learner=learner, statement=statement.strip())


def decide_appeal(admin, appeal_obj: ConductAppeal, *, overturn: bool, note: str) -> ConductAppeal:
    from apps.moderation import services as audit

    with transaction.atomic():
        appeal_obj = ConductAppeal.objects.select_for_update().select_related("rating").get(pk=appeal_obj.pk)
        if appeal_obj.status != ConductAppeal.Status.OPEN:
            raise DomainError("not_open", _("Esta apelación ya fue resuelta."))
        appeal_obj.status = ConductAppeal.Status.OVERTURNED if overturn else ConductAppeal.Status.UPHELD
        appeal_obj.decided_by, appeal_obj.decided_at, appeal_obj.decision_note = admin, timezone.now(), note
        appeal_obj.save()
        if overturn:
            appeal_obj.rating.excluded = True
            appeal_obj.rating.save(update_fields=["excluded", "updated_at"])
        recompute_conduct(appeal_obj.learner)
        audit.log(admin, "conduct.appeal_" + appeal_obj.status, appeal_obj.rating, note=note,
                  after={"appeal_id": str(appeal_obj.pk)})
    return appeal_obj


def set_review_visibility(admin, review: Review, *, visible: bool, note: str = "") -> Review:
    from apps.moderation import services as audit

    review.moderation = Review.Moderation.VISIBLE if visible else Review.Moderation.HIDDEN
    review.save(update_fields=["moderation", "updated_at"])
    recompute_experience_rating(review.experience)
    audit.log(admin, "review.show" if visible else "review.hide", review, note=note)
    return review


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def notify_window_opened(booking: Booking) -> None:
    from apps.notifications.services import notify

    ctx = {"title": booking.experience.title, "booking_id": str(booking.pk), "code": booking.code,
           "learner": booking.learner.first_name}
    if booking.status in LEARNER_REVIEWABLE:
        notify(booking.learner, "review_prompt", ctx, dedupe=f"review_prompt:{booking.pk}")
    notify(booking.experience.provider.user, "rate_learner_prompt", ctx, dedupe=f"rate_prompt:{booking.pk}", channels=("push",))


def _notify_revealed(booking, review, rating) -> None:
    from apps.notifications.services import notify

    ctx = {"title": booking.experience.title, "booking_id": str(booking.pk), "code": booking.code}
    if review:
        notify(booking.experience.provider.user, "review_received", ctx, dedupe=f"review_received:{booking.pk}", channels=("push",))
    if rating:
        notify(booking.learner, "conduct_received", ctx, dedupe=f"conduct_received:{booking.pk}", channels=("push",))
