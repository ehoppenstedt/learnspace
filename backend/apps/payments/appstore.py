"""App Store In-App Purchase (StoreKit 2): verification of Apple-signed transactions and
server notifications, and what a verified purchase or an Apple refund does to a booking.

Apple signs every transaction as a JWS (ES256) whose x5c header carries the certificate chain
leaf -> Apple intermediate -> Apple Root CA G3. We verify the chain up to the pinned root, the
signature, and that the transaction is ours: bundle id, environment, product (price point) and
appAccountToken (the booking id we handed to the app). Nothing in the client is trusted.
"""

import base64
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status

from apps.core.exceptions import DomainError
from apps.payments.models import Payment, Transfer
from apps.payments.pricing import product_id_for

logger = logging.getLogger(__name__)

# Marker extensions Apple puts on StoreKit signing certificates.
LEAF_OID = x509.ObjectIdentifier("1.2.840.113635.100.6.11.1")
INTERMEDIATE_OID = x509.ObjectIdentifier("1.2.840.113635.100.6.2.1")


class InvalidStoreSignature(Exception):
    pass


@dataclass(frozen=True)
class StoreTransaction:
    transaction_id: str
    original_transaction_id: str
    product_id: str
    app_account_token: str
    bundle_id: str
    environment: str
    price_milli: int | None  # price in milliunits of currency (iOS 16+)
    currency: str | None
    revoked: bool = False

    @classmethod
    def from_payload(cls, p: dict) -> "StoreTransaction":
        return cls(str(p.get("transactionId", "")), str(p.get("originalTransactionId", "")), p.get("productId", ""),
                   (p.get("appAccountToken") or "").lower(), p.get("bundleId", ""), p.get("environment", ""),
                   p.get("price"), p.get("currency"), bool(p.get("revocationDate")))


def _cert(b64: str) -> x509.Certificate:
    return x509.load_der_x509_certificate(base64.b64decode(b64))


def verify_jws(token: str) -> dict:
    """Returns the verified payload of an Apple-signed JWS, or raises InvalidStoreSignature."""
    try:
        header = jwt.get_unverified_header(token)
        chain = [_cert(c) for c in header.get("x5c", [])]
        if header.get("alg") != "ES256" or len(chain) != 3:
            raise InvalidStoreSignature("unexpected header")
        leaf, intermediate, root = chain
        root_fp = hashlib.sha256(root.public_bytes(Encoding.DER)).hexdigest()
        if root_fp != settings.APPLE_ROOT_CA_SHA256.lower().replace(":", ""):
            raise InvalidStoreSignature("untrusted root")
        now = datetime.now(UTC)
        for cert in chain:
            if not cert.not_valid_before_utc <= now <= cert.not_valid_after_utc:
                raise InvalidStoreSignature("certificate expired")
        leaf.verify_directly_issued_by(intermediate)
        intermediate.verify_directly_issued_by(root)
        for cert, oid in ((leaf, LEAF_OID), (intermediate, INTERMEDIATE_OID)):
            try:
                cert.extensions.get_extension_for_oid(oid)
            except x509.ExtensionNotFound as exc:
                raise InvalidStoreSignature("not a StoreKit certificate") from exc
        return jwt.decode(token, key=leaf.public_key(), algorithms=["ES256"], options={"verify_aud": False})
    except InvalidStoreSignature:
        raise
    except Exception as exc:  # malformed token, bad signature, bad chain
        raise InvalidStoreSignature(str(exc)) from exc


def verify_transaction(signed_transaction: str) -> StoreTransaction:
    return StoreTransaction.from_payload(verify_jws(signed_transaction))


# ---------------------------------------------------------------------------
# Purchases
# ---------------------------------------------------------------------------


def complete_purchase(user, booking_id, txn: StoreTransaction) -> Payment:
    """A verified App Store transaction pays the booking's App Store payment."""
    from apps.booking import services as booking_services

    with transaction.atomic():
        payment = (Payment.objects.select_for_update().select_related("booking")
                   .filter(booking_id=booking_id, booking__learner=user, gateway="app_store").first())
        if payment is None:
            raise DomainError("not_found", _("Reserva no encontrada."), status.HTTP_404_NOT_FOUND)
        if payment.charge_id == txn.transaction_id and payment.status != Payment.Status.REQUIRES_PAYMENT:
            return payment  # the app retried after a network error
        problems = []
        if txn.bundle_id != settings.APPLE_BUNDLE_ID:
            problems.append("bundle")
        if txn.environment not in settings.APPLE_ALLOWED_ENVIRONMENTS:
            problems.append("environment")
        if txn.app_account_token != str(payment.booking_id):
            problems.append("account_token")
        if txn.product_id != product_id_for(payment.amount_cents // 100):
            problems.append("product")
        if txn.currency and (txn.currency != "MXN" or txn.price_milli != payment.amount_cents * 10):
            problems.append("price")
        if txn.revoked:
            problems.append("revoked")
        if Payment.objects.filter(gateway="app_store", charge_id=txn.transaction_id).exclude(pk=payment.pk).exists():
            problems.append("replayed")
        if problems:
            logger.warning("app store transaction rejected", extra={"booking_id": str(booking_id), "problems": problems})
            raise DomainError("store_transaction_invalid", _("No pudimos validar la compra con Apple."), fields={"problems": problems})
        if payment.status != Payment.Status.REQUIRES_PAYMENT:
            raise DomainError("already_paid", _("Esta reserva ya está pagada."))
        payment.charge_id, payment.method, payment.status = txn.transaction_id, "app_store", Payment.Status.SUCCEEDED
        payment.save(update_fields=["charge_id", "method", "status", "updated_at"])
        # Apple can't authorize-and-capture: approval bookings are charged now and refunded as credit if declined.
        if payment.capture_manual:
            booking_services.on_payment_authorized(payment)
        else:
            booking_services.on_payment_captured(payment)
    return payment


# ---------------------------------------------------------------------------
# Server notifications (V2): Apple refunded or revoked a purchase
# ---------------------------------------------------------------------------


def store_refunded(transaction_id: str, *, reason: str = "store_refund") -> Payment | None:
    """Apple gave the learner their money back. If the class hasn't started, the booking is
    cancelled and any credit portion returned. If it has, the provider's payout is held for an
    admin decision, the same as a card chargeback."""
    from apps.booking import services as booking_services
    from apps.booking.models import Booking, Cancellation
    from apps.moderation.models import Report
    from apps.payments import services as payments

    payment = Payment.objects.select_for_update().select_related("booking").filter(gateway="app_store", charge_id=transaction_id).first()
    if payment is None or payment.status in (Payment.Status.REFUNDED, Payment.Status.DISPUTED):
        return payment
    booking = Booking.objects.select_for_update().get(pk=payment.booking_id)
    upcoming = booking.status in (Booking.Status.CONFIRMED, Booking.Status.PENDING_APPROVAL) and booking.starts_at > timezone.now()
    if upcoming:
        quote = booking_services.full_refund_quote(booking, reason)
        cancellation = Cancellation.objects.create(
            booking=booking, actor_role=Cancellation.Actor.SYSTEM, hours_before_start=booking_services._hours_before(booking),
            rule_snapshot={"reason": reason}, listed_refund_cents=booking.listed_cents, fee_refund_cents=booking.fee_cents,
            refund_cents=booking.total_cents, reason_code=reason)
        booking_services._release_seats(booking)
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status", "updated_at"])
        payments.refund_booking(booking, listed_cents=quote.listed_refund_cents, fee_cents=quote.fee_refund_cents,
                                surcharge_cents=quote.surcharge_refund_cents, reason=reason, cancellation=cancellation,
                                store_already_refunded=True)
        booking_services._notify(booking.experience.provider.user, "booking_cancelled_for_provider", booking)
        return payment
    payment.status = Payment.Status.DISPUTED
    payment.save(update_fields=["status", "updated_at"])
    Transfer.objects.filter(booking=booking, status=Transfer.Status.SCHEDULED).update(status=Transfer.Status.ON_HOLD, hold_reason=reason)
    Report.objects.create(reporter=booking.learner, target_type="booking", target_id=str(booking.pk), reason_code=reason,
                          details=f"Apple refunded App Store transaction {transaction_id} after the class started.")
    return payment


def handle_notification(signed_payload: str) -> str:
    """Verifies and records an App Store Server Notification V2; returns the notification type."""
    from apps.payments.models import WebhookEvent

    payload = verify_jws(signed_payload)
    kind = payload.get("notificationType", "")
    data = payload.get("data") or {}
    if data.get("bundleId") and data["bundleId"] != settings.APPLE_BUNDLE_ID:
        raise InvalidStoreSignature("bundle mismatch")
    txn = verify_transaction(data["signedTransactionInfo"]) if data.get("signedTransactionInfo") else None
    with transaction.atomic():
        record, created = WebhookEvent.objects.get_or_create(
            gateway="app_store", event_id=payload.get("notificationUUID", ""),
            defaults={"type": kind, "payload": {"kind": kind, "object_id": txn.transaction_id if txn else "", "data": {}}})
        if not created and record.processed_at:
            return kind
        if kind in ("REFUND", "REVOKE") and txn:
            store_refunded(txn.transaction_id)
        record.processed_at = timezone.now()
        record.attempts += 1
        record.save(update_fields=["processed_at", "attempts", "updated_at"])
    return kind
