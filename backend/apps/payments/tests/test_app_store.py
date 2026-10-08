"""App Store In-App Purchase (group online classes on iOS), credits, and Apple refunds."""

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import jwt
import pytest
import time_machine
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from apps.booking import services as booking_services
from apps.booking.models import Booking
from apps.catalog.models import Experience
from apps.moderation.models import Report
from apps.payments import credits
from apps.payments.appstore import INTERMEDIATE_OID, LEAF_OID
from apps.payments.gateways.fake import FakeGateway
from apps.payments.models import CreditEntry, Payment, Transfer
from apps.payments.pricing import store_price
from conftest import auth, book, make_live_experience, run_jobs

pytestmark = pytest.mark.django_db
IOS = {"HTTP_X_CLIENT_PLATFORM": "ios"}


@pytest.fixture
def online(provider_user):
    exp = make_live_experience(provider_user, title="Retrato en línea", price_cents=50000)
    Experience.objects.filter(pk=exp.pk).update(modality="online", online_url="https://meet.example.com/x")
    exp.refresh_from_db()
    return exp


def ios_checkout(api, learner, experience, **body):
    auth(api, learner)
    hold = api.post("/api/v1/holds", {"seats": 1, "session_id": str(experience.sessions.get().pk)}, format="json", **IOS)
    assert hold.status_code == 201, hold.content
    res = api.post("/api/v1/bookings", {"hold_id": hold.data["hold_id"], **body}, format="json", **IOS)
    assert res.status_code == 201, res.content
    return Booking.objects.get(pk=res.data["booking"]["id"]), res.data


def simulate(api, booking):
    assert api.post(f"/api/v1/dev/app-store/{booking.pk}/simulate", {}, format="json").status_code == 200
    booking.refresh_from_db()
    return booking


def test_store_price_covers_commission_and_vat(settings):
    p = store_price(50000, 5000)
    assert (p.total_cents, p.surcharge_cents, p.product_id) == (74900, 19900, "mx.learnspace.app.class.mxn749")
    net = p.total_cents * 10000 // 11600 * 8500 // 10000  # after Apple keeps VAT and 15%
    assert net >= 50000 + 5000 * 10000 // 11600  # provider's price + our fee net of VAT
    assert store_price(10_000_000, 1_000_000) is None  # above the highest price point


def test_ios_group_online_pays_through_app_store(api, jobs, learner, online):
    booking, data = ios_checkout(api, learner, online)
    assert data["payment_sheet"] is None
    assert data["app_store"] == {"product_id": "mx.learnspace.app.class.mxn749", "amount_cents": 74900,
                                 "app_account_token": str(booking.pk), "test_mode": True}
    assert (booking.channel, booking.total_cents, booking.store_surcharge_cents) == ("app_store", 74900, 19900)
    assert not any(op == "create_checkout" for op, _ in FakeGateway.calls)  # Stripe never involved
    booking = simulate(api, booking)
    assert booking.status == "confirmed"
    transfer = Transfer.objects.get(booking=booking)
    assert transfer.gross_cents == 50000  # the provider gets the same as on Android/web
    with time_machine.travel(booking.ends_at + timedelta(hours=49), tick=False):
        from apps.payments.services import release_due_transfers

        release_due_transfers()
    transfer.refresh_from_db()
    assert transfer.status == "sent"  # paid from the platform balance (no Stripe charge to link)


def test_one_to_one_online_on_ios_uses_card(api, jobs, learner, online):
    Experience.objects.filter(pk=online.pk).update(default_capacity=1)
    online.sessions.update(capacity=1)
    _booking, data = ios_checkout(api, learner, online)
    assert data["app_store"] is None and data["payment_sheet"]["gateway"] == "fake"


def test_learner_cancellation_refunds_as_credit_without_surcharge(api, jobs, learner, online):
    booking = simulate(api, ios_checkout(api, learner, online)[0])
    with time_machine.travel(booking.starts_at - timedelta(hours=30), tick=False):
        quote = api.get(f"/api/v1/bookings/{booking.pk}/cancellation-quote").data
        assert (quote["refund_cents"], quote["credit_cents"], quote["card_cents"]) == (55000, 55000, 0)
        assert api.post(f"/api/v1/bookings/{booking.pk}/cancel", {"quote_token": quote["quote_token"]}).status_code == 200
    run_jobs(jobs)
    assert credits.balance(learner) == 55000
    assert not any(op == "refund" for op, _ in FakeGateway.calls)
    assert auth(api, learner).get("/api/v1/me/credits").data["balance_cents"] == 55000


def test_provider_cancellation_returns_everything_as_credit(api, jobs, learner, provider_user, online):
    booking = simulate(api, ios_checkout(api, learner, online)[0])
    assert auth(api, provider_user).post(f"/api/v1/provider/sessions/{booking.session_id}/cancel", {}, format="json").status_code == 200
    run_jobs(jobs)
    assert credits.balance(learner) == 74900  # surcharge included: the learner did nothing wrong


def test_credit_pays_a_card_booking_in_full(api, jobs, learner, provider_user):
    credits.grant(learner, 60000, kind="adjustment", key="gift-1")
    session = make_live_experience(provider_user).sessions.get()
    auth(api, learner)
    hold = api.post("/api/v1/holds", {"seats": 1, "session_id": str(session.pk)}, format="json")
    assert hold.data["credit_available_cents"] == 60000
    res = api.post("/api/v1/bookings", {"hold_id": hold.data["hold_id"]}, format="json")
    assert res.data["payment_sheet"] is None and res.data["credit_applied_cents"] == 55000
    assert res.data["booking"]["status"] == "confirmed"
    assert credits.balance(learner) == 5000
    assert not any(op == "create_checkout" for op, _ in FakeGateway.calls)


def test_partial_credit_then_card_and_refund_goes_card_first(api, jobs, learner, provider_user):
    credits.grant(learner, 20000, kind="adjustment", key="gift-2")
    session = make_live_experience(provider_user).sessions.get()
    booking = book(api, jobs, learner, session)
    card = booking.payments.exclude(gateway="credit").get()
    assert card.amount_cents == 35000 and booking.payments.get(gateway="credit").amount_cents == 20000
    with time_machine.travel(booking.starts_at - timedelta(hours=30), tick=False):
        quote = api.get(f"/api/v1/bookings/{booking.pk}/cancellation-quote").data
        assert (quote["card_cents"], quote["credit_cents"]) == (35000, 20000)
        api.post(f"/api/v1/bookings/{booking.pk}/cancel", {"quote_token": quote["quote_token"]})
    run_jobs(jobs)
    assert [a["amount"] for op, a in FakeGateway.calls if op == "refund"] == [35000]
    assert credits.balance(learner) == 20000


def test_small_card_remainder_respects_stripe_minimum(api, jobs, learner, provider_user):
    credits.grant(learner, 54500, kind="adjustment", key="gift-3")  # would leave $5 on the card
    session = make_live_experience(provider_user).sessions.get()
    booking = book(api, jobs, learner, session)
    assert booking.payments.exclude(gateway="credit").get().amount_cents == 1000
    assert credits.balance(learner) == 54500 - 54000


def test_credit_on_app_store_lands_on_a_price_point(api, jobs, learner, online):
    credits.grant(learner, 20000, kind="adjustment", key="gift-4")
    booking, data = ios_checkout(api, learner, online)
    assert data["app_store"]["amount_cents"] == 54900 and data["app_store"]["product_id"].endswith("mxn549")
    assert data["credit_applied_cents"] == 20000
    assert simulate(api, booking).status == "confirmed"


def test_abandoned_checkout_gives_credit_back(api, jobs, learner, provider_user):
    credits.grant(learner, 20000, kind="adjustment", key="gift-5")
    session = make_live_experience(provider_user).sessions.get()
    auth(api, learner)
    hold = api.post("/api/v1/holds", {"seats": 1, "session_id": str(session.pk)}, format="json")
    api.post("/api/v1/bookings", {"hold_id": hold.data["hold_id"]}, format="json")
    assert credits.balance(learner) == 0
    with time_machine.travel(datetime.now(UTC) + timedelta(hours=1), tick=False):
        booking_services.expire_unpaid()
        booking_services.expire_unpaid()  # idempotent
    assert credits.balance(learner) == 20000


def test_approval_on_app_store_is_charged_then_declined_as_credit(api, jobs, learner, provider_user, online):
    Experience.objects.filter(pk=online.pk).update(requires_approval_below=Decimal("4.00"))
    learner.learner_profile.conduct_score = Decimal("3.00")
    learner.learner_profile.save()
    booking = simulate(api, ios_checkout(api, learner, online)[0])
    assert booking.status == "pending_approval"
    assert auth(api, provider_user).post(f"/api/v1/provider/bookings/{booking.pk}/decline").data["status"] == "declined"
    run_jobs(jobs)
    assert credits.balance(learner) == 74900


def test_approval_on_app_store_approve_confirms_without_capture(api, jobs, learner, provider_user, online):
    Experience.objects.filter(pk=online.pk).update(requires_approval_below=Decimal("4.00"))
    learner.learner_profile.conduct_score = Decimal("3.00")
    learner.learner_profile.save()
    booking = simulate(api, ios_checkout(api, learner, online)[0])
    assert auth(api, provider_user).post(f"/api/v1/provider/bookings/{booking.pk}/approve").data["status"] == "confirmed"


# ---------------------------------------------------------------- signed transactions (StoreKit 2)


def _cert(subject, issuer, key, issuer_key, *, ca, oid=None):
    now = datetime.now(UTC)
    builder = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)]))
               .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer)])).public_key(key.public_key())
               .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
               .not_valid_after(now + timedelta(days=365))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if oid:
        builder = builder.add_extension(x509.UnrecognizedExtension(oid, b"\x05\x00"), critical=False)
    return builder.sign(issuer_key, hashes.SHA256())


@pytest.fixture
def apple(settings):
    """A stand-in Apple PKI: root (pinned by fingerprint) -> intermediate -> leaf."""
    root_key, mid_key, leaf_key = (ec.generate_private_key(ec.SECP256R1()) for _ in range(3))
    root = _cert("Test Root", "Test Root", root_key, root_key, ca=True)
    mid = _cert("Test WWDR", "Test Root", mid_key, root_key, ca=True, oid=INTERMEDIATE_OID)
    leaf = _cert("Test StoreKit", "Test WWDR", leaf_key, mid_key, ca=False, oid=LEAF_OID)
    settings.APP_STORE_GATEWAY = "apple"
    settings.APPLE_ROOT_CA_SHA256 = hashlib.sha256(root.public_bytes(serialization.Encoding.DER)).hexdigest()
    import base64

    x5c = [base64.b64encode(c.public_bytes(serialization.Encoding.DER)).decode() for c in (leaf, mid, root)]

    def sign(payload, key=leaf_key):
        return jwt.encode(payload, key, algorithm="ES256", headers={"x5c": x5c})
    return sign


def _txn(booking, amount=74900, **over):
    return {"transactionId": f"2000000{booking.code}", "originalTransactionId": f"2000000{booking.code}",
            "productId": f"mx.learnspace.app.class.mxn{amount // 100}", "appAccountToken": str(booking.pk),
            "bundleId": "mx.learnspace.app", "environment": "Sandbox", "price": amount * 10, "currency": "MXN",
            "type": "Consumable", **over}


def test_signed_transaction_confirms_booking(api, jobs, learner, online, apple):
    booking, _ = ios_checkout(api, learner, online)
    res = api.post(f"/api/v1/bookings/{booking.pk}/app-store-transaction", {"signed_transaction": apple(_txn(booking))}, format="json")
    assert res.status_code == 200 and res.data["status"] == "confirmed"
    # The app retries after a timeout: same transaction, same result, no double processing.
    res = api.post(f"/api/v1/bookings/{booking.pk}/app-store-transaction", {"signed_transaction": apple(_txn(booking))}, format="json")
    assert res.status_code == 200
    assert Payment.objects.get(booking=booking).charge_id == f"2000000{booking.code}"


@pytest.mark.parametrize("override,problem", [
    ({"productId": "mx.learnspace.app.class.mxn49"}, "product"),
    ({"appAccountToken": "00000000-0000-0000-0000-000000000000"}, "account_token"),
    ({"bundleId": "com.other.app"}, "bundle"),
    ({"price": 4900}, "price"),
])
def test_transaction_for_something_else_is_rejected(api, learner, online, apple, override, problem):
    booking, _ = ios_checkout(api, learner, online)
    res = api.post(f"/api/v1/bookings/{booking.pk}/app-store-transaction", {"signed_transaction": apple(_txn(booking, **override))}, format="json")
    assert res.status_code == 409 and problem in res.data["error"]["fields"]["problems"]
    booking.refresh_from_db()
    assert booking.status == "pending_payment"


def test_forged_or_untrusted_signatures_are_rejected(api, learner, online, apple, settings):
    booking, _ = ios_checkout(api, learner, online)
    forged = apple(_txn(booking), key=ec.generate_private_key(ec.SECP256R1()))
    res = api.post(f"/api/v1/bookings/{booking.pk}/app-store-transaction", {"signed_transaction": forged}, format="json")
    assert res.status_code == 400
    settings.APPLE_ROOT_CA_SHA256 = "00" * 32  # chain doesn't end at the pinned Apple root
    res = api.post(f"/api/v1/bookings/{booking.pk}/app-store-transaction", {"signed_transaction": apple(_txn(booking))}, format="json")
    assert res.status_code == 400


def test_transaction_cannot_pay_two_bookings(api, learner, provider_user, online, apple):
    first, _ = ios_checkout(api, learner, online)
    api.post(f"/api/v1/bookings/{first.pk}/app-store-transaction", {"signed_transaction": apple(_txn(first))}, format="json")
    other = make_live_experience(provider_user, title="Otra en línea")
    Experience.objects.filter(pk=other.pk).update(modality="online", online_url="https://meet.example.com/y")
    other.refresh_from_db()
    second, _ = ios_checkout(api, learner, other)
    replay = _txn(second, transactionId=f"2000000{first.code}")
    res = api.post(f"/api/v1/bookings/{second.pk}/app-store-transaction", {"signed_transaction": apple(replay)}, format="json")
    assert "replayed" in res.data["error"]["fields"]["problems"]


def _notify_refund(api, apple, booking, uuid="n-1"):
    payload = {"notificationType": "REFUND", "notificationUUID": uuid,
               "data": {"bundleId": "mx.learnspace.app", "signedTransactionInfo": apple(_txn(booking))}}
    return api.post("/api/v1/webhooks/app-store", {"signedPayload": apple(payload)}, format="json")


def test_apple_refund_before_class_cancels_booking_without_double_refund(api, jobs, learner, online, apple):
    credits.grant(learner, 20000, kind="adjustment", key="gift-6")
    booking, _ = ios_checkout(api, learner, online)
    api.post(f"/api/v1/bookings/{booking.pk}/app-store-transaction", {"signed_transaction": apple(_txn(booking, amount=54900))}, format="json")
    assert _notify_refund(api, apple, booking).status_code == 200
    assert _notify_refund(api, apple, booking).status_code == 200  # Apple retries: processed once
    run_jobs(jobs)
    booking.refresh_from_db()
    assert booking.status == "cancelled"
    assert credits.balance(learner) == 20000  # only the credit part comes back as credit; Apple refunded the rest
    assert Transfer.objects.get(booking=booking).status == "canceled"
    assert CreditEntry.objects.filter(user=learner, kind="refund").count() == 1


def test_apple_refund_after_class_holds_payout_for_review(api, jobs, learner, online, apple):
    booking, _ = ios_checkout(api, learner, online)
    api.post(f"/api/v1/bookings/{booking.pk}/app-store-transaction", {"signed_transaction": apple(_txn(booking))}, format="json")
    with time_machine.travel(booking.ends_at + timedelta(hours=1), tick=False):
        assert _notify_refund(api, apple, booking).status_code == 200
    assert Transfer.objects.get(booking=booking).hold_reason == "store_refund"
    assert Report.objects.filter(reason_code="store_refund", target_id=str(booking.pk)).exists()


def test_notification_with_bad_signature_is_rejected(api):
    assert api.post("/api/v1/webhooks/app-store", {"signedPayload": "x.y.z"}, format="json").status_code == 400
