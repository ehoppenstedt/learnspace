"""Money movement. Booking logic decides *what* is owed; this module moves it.

Calls to the processor that must not be lost (refunds, transfers) are written to the database
first (status pending, with an idempotency key) and executed by a job after the transaction
commits. A crash between the two leaves a pending row that the job retries; the processor
de-duplicates by key, so nothing is ever paid twice.
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status

from apps.core.exceptions import DomainError
from apps.payments.gateways import get_gateway
from apps.payments.gateways.base import Checkout, GatewayError, GatewayEvent
from apps.payments.models import (
    Payment,
    PaymentAccount,
    PaymentCustomer,
    ProviderTaxProfile,
    Refund,
    Transfer,
    WebhookEvent,
    WithholdingConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


def customer_id_for(user) -> str:
    gateway = get_gateway()
    record = PaymentCustomer.objects.filter(user=user, gateway=gateway.name).first()
    customer_id = gateway.ensure_customer(user, record.external_id if record else None)
    if record is None:
        PaymentCustomer.objects.get_or_create(user=user, gateway=gateway.name, defaults={"external_id": customer_id})
    return customer_id


def start_payment(booking, *, capture_manual: bool, amount_cents: int) -> Checkout:
    gateway = get_gateway()
    try:
        customer_id = customer_id_for(booking.learner)
        checkout = gateway.create_checkout(booking=booking, amount_cents=amount_cents, customer_id=customer_id,
                                           capture_manual=capture_manual, idempotency_key=f"checkout-{booking.pk}")
    except GatewayError as exc:
        logger.error("checkout failed", extra={"booking_id": str(booking.pk), "error": str(exc)})
        booking.status = booking.Status.PAYMENT_FAILED
        booking.save(update_fields=["status", "updated_at"])
        raise DomainError("payment_unavailable", _("No pudimos iniciar el pago. Intenta de nuevo."), status.HTTP_502_BAD_GATEWAY)
    Payment.objects.create(booking=booking, gateway=gateway.name, external_id=checkout.payment_id,
                           amount_cents=amount_cents, capture_manual=capture_manual)
    return checkout


def existing_checkout(booking):
    """Retry of POST /bookings for the same hold: hand back the same payment, never a second one."""
    payment = booking.payments.exclude(gateway=CREDIT).order_by("-created_at").first()
    if payment is None or payment.status != Payment.Status.REQUIRES_PAYMENT:
        return None
    if payment.gateway == APP_STORE:
        return store_checkout(payment)
    gateway = get_gateway()
    checkout = gateway.create_checkout(booking=booking, amount_cents=payment.amount_cents, customer_id=customer_id_for(booking.learner),
                                       capture_manual=payment.capture_manual, idempotency_key=f"checkout-{booking.pk}")
    return checkout


# ---------------------------------------------------------------------------
# Credits and App Store purchases (see apps/payments/credits.py and appstore.py)
# ---------------------------------------------------------------------------

CREDIT, APP_STORE = "credit", "app_store"
MIN_CARD_CHARGE_CENTS = 1000  # Stripe's minimum charge in MXN is $10


@dataclass(frozen=True)
class StoreCheckout:
    """What the iOS app needs to start the In-App Purchase."""

    payment_id: str
    product_id: str
    amount_cents: int
    app_account_token: str  # the booking id; Apple signs it back inside the transaction


def split_credit(channel: str, total_cents: int, available_cents: int) -> tuple[int, int]:
    """(credit used, amount left to charge). App Store charges must land on a price point."""
    from apps.payments.pricing import store_point_at_least

    if available_cents <= 0:
        return 0, total_cents
    if available_cents >= total_cents:
        return total_cents, 0
    if channel == APP_STORE:
        point = store_point_at_least(total_cents - available_cents)
        if point is None or point >= total_cents:
            return 0, total_cents
        return total_cents - point, point
    remainder = total_cents - available_cents
    if remainder < MIN_CARD_CHARGE_CENTS:
        used = max(total_cents - MIN_CARD_CHARGE_CENTS, 0)
        return used, total_cents - used
    return available_cents, remainder


def pay_with_credit(booking, amount_cents: int) -> Payment | None:
    """Must run inside the caller's transaction (after the booking row exists)."""
    from apps.payments import credits

    if amount_cents <= 0:
        return None
    credits.spend(booking.learner, amount_cents, booking=booking, key=f"spend-{booking.pk}")
    return Payment.objects.create(booking=booking, gateway=CREDIT, external_id=f"credit-{booking.pk}", charge_id=f"credit-{booking.pk}",
                                  amount_cents=amount_cents, status=Payment.Status.SUCCEEDED, method=CREDIT)


def restore_credit(booking) -> int:
    """Checkout abandoned or failed: give back the credit it had reserved."""
    from apps.payments import credits

    restored = 0
    for payment in Payment.objects.select_for_update().filter(booking=booking, gateway=CREDIT, status=Payment.Status.SUCCEEDED):
        credits.grant(booking.learner, payment.amount_cents, kind="restore", key=f"restore-{payment.pk}", booking=booking)
        payment.status = Payment.Status.CANCELED
        payment.save(update_fields=["status", "updated_at"])
        restored += payment.amount_cents
    return restored


def start_store_payment(booking, *, amount_cents: int, capture_manual: bool) -> StoreCheckout:
    payment = Payment.objects.create(booking=booking, gateway=APP_STORE, external_id=f"aps-{booking.pk}", amount_cents=amount_cents,
                                     capture_manual=capture_manual)
    return store_checkout(payment)


def store_checkout(payment: Payment) -> StoreCheckout:
    from apps.payments.pricing import product_id_for

    return StoreCheckout(str(payment.pk), product_id_for(payment.amount_cents // 100), payment.amount_cents, str(payment.booking_id))


def capture(booking) -> Payment:
    payment = Payment.objects.select_for_update().filter(booking=booking, status=Payment.Status.AUTHORIZED).first()
    if payment is None:
        raise DomainError("not_authorized", _("No hay un pago autorizado para esta reserva."))
    try:
        get_gateway().capture(payment.external_id, idempotency_key=f"capture-{payment.pk}")
    except GatewayError as exc:
        raise DomainError("capture_failed", _("No pudimos cobrar la reserva; la autorización pudo haber expirado."),
                          status.HTTP_502_BAD_GATEWAY) from exc
    payment.status = Payment.Status.SUCCEEDED
    payment.save(update_fields=["status", "updated_at"])
    return payment


def release_authorization(payment: Payment) -> None:
    if payment.status != Payment.Status.AUTHORIZED:
        return
    payment.status = Payment.Status.CANCELED
    payment.save(update_fields=["status", "updated_at"])
    from apps.payments.tasks import cancel_authorization_task

    transaction.on_commit(lambda: cancel_authorization_task.defer(payment_id=str(payment.pk)))


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------


def refund_booking(booking, *, listed_cents: int, fee_cents: int, surcharge_cents: int = 0, reason: str, cancellation=None,
                   created_by=None, store_already_refunded: bool = False) -> list[Refund]:
    """Spreads one refund over the booking's payments: card/App Store first, then credit.
    Amounts beyond what was actually charged (e.g. an unpaid authorization) are dropped."""
    payments = list(Payment.objects.select_for_update().filter(
        booking=booking, status__in=[Payment.Status.SUCCEEDED, Payment.Status.PARTIALLY_REFUNDED]).order_by("created_at"))
    payments.sort(key=lambda p: p.gateway == CREDIT)
    remaining = {"listed": listed_cents, "fee": fee_cents, "surcharge": surcharge_cents}
    refunds = []
    for payment in payments:
        capacity = payment.amount_cents - payment.refunded_cents
        part = {}
        for key in ("listed", "fee", "surcharge"):
            take = min(remaining[key], capacity)
            part[key], remaining[key], capacity = take, remaining[key] - take, capacity - take
        if sum(part.values()) > 0:
            refunds.append(refund_payment(payment, listed_cents=part["listed"], fee_cents=part["fee"], surcharge_cents=part["surcharge"],
                                          reason=reason, cancellation=cancellation, created_by=created_by,
                                          execute=not (store_already_refunded and payment.gateway == APP_STORE)))
    return refunds


def refund_preview(booking, total_cents: int) -> dict:
    """How a refund of this size would come back: to the card, or as credit (App Store, credit)."""
    out = {"card_cents": 0, "credit_cents": 0}
    left = total_cents
    payments = sorted(booking.payments.filter(status__in=[Payment.Status.SUCCEEDED, Payment.Status.PARTIALLY_REFUNDED]),
                      key=lambda p: (p.gateway == CREDIT, p.created_at))
    for payment in payments:
        take = min(left, payment.amount_cents - payment.refunded_cents)
        out["credit_cents" if payment.gateway in (CREDIT, APP_STORE) else "card_cents"] += take
        left -= take
    return out


def refund_payment(payment: Payment, *, listed_cents: int, fee_cents: int, reason: str, cancellation=None, created_by=None,
                   surcharge_cents: int = 0, execute: bool = True) -> Refund:
    """Records the refund and queues it. Must run inside the caller's transaction.
    execute=False records a refund that already happened elsewhere (Apple refunded the learner)."""
    total = listed_cents + fee_cents + surcharge_cents
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if total <= 0:
        raise ValueError("refund must be positive")
    if payment.refunded_cents + total > payment.amount_cents:
        raise DomainError("refund_exceeds_payment", _("El reembolso excede el pago."))
    refund = Refund.objects.create(
        payment=payment, cancellation=cancellation, listed_refund_cents=listed_cents, fee_refund_cents=fee_cents,
        surcharge_refund_cents=surcharge_cents, total_refund_cents=total, reason=reason, created_by=created_by,
        idempotency_key=f"refund-{payment.pk}-{payment.refunds.count() + 1}",
        status=Refund.Status.PENDING if execute else Refund.Status.SUCCEEDED, external_id="" if execute else "store",
    )
    payment.refunded_cents = F("refunded_cents") + total
    payment.save(update_fields=["refunded_cents", "updated_at"])
    payment.refresh_from_db(fields=["refunded_cents"])
    payment.status = Payment.Status.REFUNDED if payment.refunded_cents == payment.amount_cents else Payment.Status.PARTIALLY_REFUNDED
    payment.save(update_fields=["status", "updated_at"])
    recompute_transfer(payment.booking)
    if execute and payment.gateway in (CREDIT, APP_STORE):
        execute_refund(refund.pk)  # credit is our own ledger: no processor call, so no job needed
    elif execute:
        from apps.payments.tasks import execute_refund_task

        transaction.on_commit(lambda: execute_refund_task.defer(refund_id=str(refund.pk)))
    return refund


def execute_refund(refund_id) -> Refund:
    refund = Refund.objects.select_related("payment").get(pk=refund_id)
    if refund.status != Refund.Status.PENDING:
        return refund
    if refund.payment.gateway in (CREDIT, APP_STORE):
        # Only Apple can refund App Store purchases: those (and credit) come back as credit.
        from apps.payments import credits

        entry = credits.grant(refund.payment.booking.learner, refund.total_refund_cents, kind="refund",
                              key=f"refund-{refund.pk}", booking=refund.payment.booking, refund=refund)
        refund.external_id, refund.status = f"credit-{entry.pk}", Refund.Status.SUCCEEDED
        refund.save(update_fields=["external_id", "status", "updated_at"])
        return refund
    try:
        refund.external_id = get_gateway().refund(
            payment_external_id=refund.payment.external_id, amount_cents=refund.total_refund_cents,
            idempotency_key=refund.idempotency_key, reason=refund.reason,
        )
        refund.status = Refund.Status.SUCCEEDED
    except GatewayError:
        logger.exception("refund failed", extra={"refund_id": str(refund.pk)})
        refund.status = Refund.Status.FAILED  # shows up in the admin refunds queue
    refund.save(update_fields=["external_id", "status", "updated_at"])
    return refund


# ---------------------------------------------------------------------------
# Transfers (provider payouts) and withholding
# ---------------------------------------------------------------------------


def current_withholding(provider) -> tuple[int, int]:
    """ISR/IVA basis points for this provider. Companies (personas morales) are not withheld."""
    profile = ProviderTaxProfile.objects.filter(provider=provider).first()
    if profile and profile.person_type == ProviderTaxProfile.PersonType.MORAL:
        return 0, 0
    config = WithholdingConfig.objects.filter(effective_from__lte=timezone.now()).order_by("-effective_from").first()
    return (config.isr_bps, config.iva_bps) if config else (0, 0)


def _bps(amount: int, bps: int) -> int:
    return (amount * bps + 5000) // 10000


def _fill_amounts(transfer: Transfer, gross: int) -> None:
    transfer.gross_cents = max(gross, 0)
    transfer.isr_withheld_cents = _bps(transfer.gross_cents, transfer.isr_bps)
    transfer.iva_withheld_cents = _bps(transfer.gross_cents, transfer.iva_bps)
    transfer.net_cents = transfer.gross_cents - transfer.isr_withheld_cents - transfer.iva_withheld_cents


def schedule_transfer(booking, *, release_at) -> Transfer:
    provider = booking.experience.provider
    isr, iva = current_withholding(provider)
    transfer, created = Transfer.objects.get_or_create(
        booking=booking, defaults={"provider": provider, "release_at": release_at, "isr_bps": isr, "iva_bps": iva},
    )
    if created:
        recompute_transfer(booking)
    return transfer


def listed_refunded(booking) -> int:
    from apps.payments.models import Refund as R

    return R.objects.filter(payment__booking=booking).aggregate(n=Sum("listed_refund_cents"))["n"] or 0


def recompute_transfer(booking) -> Transfer | None:
    """Provider keeps the listed price minus whatever part of it was refunded to the learner."""
    transfer = Transfer.objects.select_for_update().filter(booking=booking).first()
    if transfer is None:
        return None
    gross = booking.listed_cents - listed_refunded(booking)
    if transfer.status == Transfer.Status.SENT:
        owed_back = transfer.gross_cents - gross
        if owed_back > 0:
            previous_net = transfer.net_cents
            _fill_amounts(transfer, gross)
            reverse = previous_net - transfer.net_cents
            transfer.reversed_cents += reverse
            transfer.status = Transfer.Status.REVERSED if transfer.net_cents == 0 else Transfer.Status.SENT
            transfer.save()
            from apps.payments.tasks import reverse_transfer_task

            transaction.on_commit(lambda: reverse_transfer_task.defer(transfer_id=str(transfer.pk), amount_cents=reverse))
        return transfer
    _fill_amounts(transfer, gross)
    if transfer.gross_cents == 0:
        transfer.status = Transfer.Status.CANCELED
    transfer.save()
    return transfer


def release_due_transfers(now=None) -> int:
    now = now or timezone.now()
    ids = list(Transfer.objects.filter(status=Transfer.Status.SCHEDULED, release_at__lte=now).values_list("pk", flat=True))
    for pk in ids:
        send_transfer(pk)
    return len(ids)


def send_transfer(transfer_id) -> Transfer:
    from apps.booking.models import Booking

    with transaction.atomic():
        transfer = Transfer.objects.select_for_update().select_related("booking", "provider").get(pk=transfer_id)
        if transfer.status != Transfer.Status.SCHEDULED or transfer.net_cents <= 0:
            return transfer
        if transfer.booking.status not in (Booking.Status.CONFIRMED, Booking.Status.COMPLETED, Booking.Status.NO_SHOW,
                                           Booking.Status.CANCELLED):
            return transfer
        account = PaymentAccount.objects.filter(provider=transfer.provider, payouts_enabled=True).first()
        paid = transfer.booking.payments.exclude(charge_id="").exclude(status__in=[Payment.Status.CANCELED, Payment.Status.FAILED])
        payment = paid.exclude(gateway__in=[CREDIT, APP_STORE]).order_by("-created_at").first()
        if account is None or not paid.exists():
            transfer.status, transfer.hold_reason = Transfer.Status.ON_HOLD, "payouts_disabled" if account is None else "no_charge"
            transfer.save(update_fields=["status", "hold_reason", "updated_at"])
            return transfer
        try:
            transfer.external_id = get_gateway().transfer(
                amount_cents=transfer.net_cents, destination=account.external_id, source_charge=payment.charge_id if payment else "",
                group=transfer.booking.code, idempotency_key=f"transfer-{transfer.pk}",
            )
        except GatewayError:
            logger.exception("transfer failed", extra={"transfer_id": str(transfer.pk)})
            return transfer  # stays scheduled; the hourly job retries with the same idempotency key
        transfer.status, transfer.sent_at = Transfer.Status.SENT, timezone.now()
        transfer.save(update_fields=["external_id", "status", "sent_at", "updated_at"])
        from apps.notifications.services import notify

        notify(transfer.provider.user, "transfer_sent", {
            "title": transfer.booking.experience.title, "code": transfer.booking.code, "net": f"${transfer.net_cents / 100:,.2f} MXN",
        }, dedupe=f"transfer_sent:{transfer.pk}", channels=("push",))
    return transfer


# ---------------------------------------------------------------------------
# Provider onboarding (KYC)
# ---------------------------------------------------------------------------


def start_onboarding(provider) -> str:
    gateway = get_gateway()
    account = PaymentAccount.objects.filter(provider=provider).first()
    base = settings.PUBLIC_BASE_URL
    try:
        account_id, url = gateway.onboard_provider(
            provider=provider, existing_account_id=account.external_id if account else None,
            return_url=f"{base}/payments/onboarding/return", refresh_url=f"{base}/payments/onboarding/refresh",
        )
    except GatewayError as exc:
        raise DomainError("onboarding_unavailable", _("No pudimos abrir el registro de pagos."), status.HTTP_502_BAD_GATEWAY) from exc
    if account is None:
        PaymentAccount.objects.create(provider=provider, gateway=gateway.name, external_id=account_id)
    return url


def sync_account(account_id: str, status_obj=None) -> PaymentAccount | None:
    account = PaymentAccount.objects.filter(external_id=account_id).first()
    if account is None:
        return None
    status_obj = status_obj or get_gateway(account.gateway).get_account_status(account_id)
    account.charges_enabled = status_obj.charges_enabled
    account.payouts_enabled = status_obj.payouts_enabled
    account.requirements_due = status_obj.requirements_due
    account.kyc_status = status_obj.kyc_status
    account.save()
    if account.payouts_enabled:
        # Payouts that were waiting for KYC can go now.
        Transfer.objects.filter(provider=account.provider, status=Transfer.Status.ON_HOLD, hold_reason="payouts_disabled").update(
            status=Transfer.Status.SCHEDULED, hold_reason="")
    return account


def provider_ready_for_payouts(provider) -> tuple[bool, list[str]]:
    missing = []
    if not provider.is_verified:
        missing.append("identity")
    if settings.PAYMENTS_REQUIRE_KYC:
        account = PaymentAccount.objects.filter(provider=provider).first()
        if not (account and account.payouts_enabled):
            missing.append("payment_account")
        if not ProviderTaxProfile.objects.filter(provider=provider).exists():
            missing.append("tax_profile")
    return not missing, missing


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


def record_webhook(gateway_name: str, event: GatewayEvent) -> tuple[WebhookEvent, bool]:
    return WebhookEvent.objects.get_or_create(
        gateway=gateway_name, event_id=event.id,
        defaults={"type": event.raw_type, "payload": {"kind": event.kind, "object_id": event.object_id, "data": event.data}},
    )


def process_webhook(webhook_id) -> WebhookEvent:
    from apps.booking import services as booking_services

    with transaction.atomic():
        record = WebhookEvent.objects.select_for_update().get(pk=webhook_id)
        if record.processed_at:
            return record  # duplicate delivery or retried job
        record.attempts += 1
        kind, object_id, data = record.payload["kind"], record.payload["object_id"], record.payload["data"]
        if kind in ("payment_succeeded", "payment_authorized", "payment_failed", "payment_canceled", "dispute_created"):
            payment = Payment.objects.select_for_update().filter(gateway=record.gateway, external_id=object_id).first()
            if payment is not None:
                if kind == "payment_succeeded":
                    if payment.status in (Payment.Status.REQUIRES_PAYMENT, Payment.Status.AUTHORIZED, Payment.Status.FAILED):
                        payment.status = Payment.Status.SUCCEEDED
                    payment.charge_id = data.get("charge_id") or payment.charge_id
                    payment.method = data.get("method") or payment.method
                    payment.save()
                    booking_services.on_payment_captured(payment)
                elif kind == "payment_authorized":
                    if payment.status == Payment.Status.REQUIRES_PAYMENT:
                        payment.status = Payment.Status.AUTHORIZED
                        payment.method = data.get("method") or payment.method
                        payment.save()
                        booking_services.on_payment_authorized(payment)
                elif kind == "payment_failed":
                    if payment.status == Payment.Status.REQUIRES_PAYMENT:
                        payment.failure_reason = data.get("reason", "")
                        payment.save(update_fields=["failure_reason", "updated_at"])
                        booking_services.on_payment_failed(payment)
                elif kind == "payment_canceled":
                    if payment.status in (Payment.Status.REQUIRES_PAYMENT, Payment.Status.AUTHORIZED):
                        payment.status = Payment.Status.CANCELED
                        payment.save(update_fields=["status", "updated_at"])
                elif kind == "dispute_created":
                    _open_dispute(payment, data)
        elif kind == "account_updated":
            from apps.payments.gateways.base import AccountStatus

            sync_account(object_id, AccountStatus(data.get("charges_enabled", False), data.get("payouts_enabled", False),
                                                  data.get("requirements_due", [])))
        elif kind == "refund_failed":
            Refund.objects.filter(external_id=object_id).update(status=Refund.Status.FAILED)
        record.processed_at = timezone.now()
        record.save(update_fields=["processed_at", "attempts", "updated_at"])
    return record


def _open_dispute(payment: Payment, data: dict) -> None:
    from apps.moderation.models import Report

    payment.status = Payment.Status.DISPUTED
    payment.save(update_fields=["status", "updated_at"])
    Transfer.objects.filter(booking=payment.booking, status=Transfer.Status.SCHEDULED).update(
        status=Transfer.Status.ON_HOLD, hold_reason="chargeback")
    Report.objects.create(reporter=payment.booking.learner, target_type="booking", target_id=str(payment.booking_id),
                          reason_code="chargeback", details=f"Dispute {data.get('dispute_id')}: {data.get('reason')}")
