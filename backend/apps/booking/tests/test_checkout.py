from datetime import timedelta
from decimal import Decimal

import pytest
import time_machine
from django.core import mail
from django.utils import timezone

from apps.booking import services
from apps.booking.models import Booking
from apps.catalog.models import Experience, Session
from apps.notifications.models import Notification
from apps.payments.gateways.fake import FakeGateway
from apps.payments.models import Payment, Transfer, WebhookEvent
from conftest import book, hold_and_checkout, make_live_experience, make_user, pay, run_jobs

pytestmark = pytest.mark.django_db


@pytest.fixture
def session(provider_user):
    return make_live_experience(provider_user, price_cents=50000).sessions.get()


def test_full_booking_flow(api, jobs, learner, session):
    booking = hold_and_checkout(api, learner, session=session, seats=2)
    # Price frozen at checkout: 2 x 500 listed + 10% fee.
    assert (booking.listed_cents, booking.fee_cents, booking.total_cents) == (100000, 10000, 110000)
    assert booking.status == "pending_payment" and booking.policy_snapshot["code"] == "standard"
    assert FakeGateway.calls[-1][0] == "create_checkout" and FakeGateway.calls[-1][1]["amount"] == 110000

    booking = pay(api, jobs, booking)
    assert booking.status == "confirmed" and booking.seats_counted
    session.refresh_from_db()
    assert session.seats_booked == 2
    transfer = Transfer.objects.get(booking=booking)
    assert transfer.gross_cents == 100000 and transfer.status == "scheduled"
    assert transfer.release_at == session.ends_at + timedelta(hours=48)

    # Confirmation email with calendar attachment; provider notified.
    confirm = [m for m in mail.outbox if m.to == [learner.email]][0]
    assert confirm.attachments[0][0] == "clase.ics" and "BEGIN:VEVENT" in confirm.attachments[0][1]
    assert Notification.objects.filter(kind="booking_new_for_provider", user=session.experience.provider.user).exists()

    # Exact address unlocked for this learner only.
    detail = api.get(f"/api/v1/bookings/{booking.pk}").data
    assert detail["location"]["approximate"] is False and detail["location"]["address_line"].startswith("Colima 123")
    assert api.get(f"/api/v1/experiences/{session.experience_id}").data["location"]["approximate"] is False
    ics = api.get(detail["calendar_url"].replace("http://testserver", ""))
    assert ics.status_code == 200 and ics["Content-Type"].startswith("text/calendar")


def test_webhook_is_idempotent(api, jobs, learner, session):
    booking = hold_and_checkout(api, learner, session=session)
    payment = booking.payments.get()
    body_event = FakeGateway.build_event("payment_succeeded", payment.external_id, charge_id="ch_1")
    from apps.payments.gateways.fake import SIGNATURE_HEADER

    for _ in range(3):  # processor retries the same event
        res = api.generic("POST", "/api/v1/webhooks/payments/fake", body_event, content_type="application/json",
                          **{f"HTTP_{SIGNATURE_HEADER.upper().replace('-', '_')}": FakeGateway.sign(body_event)})
        assert res.status_code == 200
    run_jobs(jobs)
    session.refresh_from_db()
    assert WebhookEvent.objects.count() == 1 and session.seats_booked == 1
    # A *different* event for the same payment (e.g. late duplicate) doesn't double-count either.
    pay(api, jobs, booking)
    session.refresh_from_db()
    assert session.seats_booked == 1


def test_webhook_rejects_bad_signature(api):
    from apps.payments.gateways.fake import FakeGateway

    body = FakeGateway.build_event("payment_succeeded", "pi_x")
    res = api.generic("POST", "/api/v1/webhooks/payments/fake", body, content_type="application/json", HTTP_X_FAKE_SIGNATURE="nope")
    assert res.status_code == 400 and WebhookEvent.objects.count() == 0


def test_retrying_checkout_returns_same_payment(api, learner, session):
    api.force_authenticate(learner)
    hold = api.post("/api/v1/holds", {"session_id": str(session.pk), "seats": 1}).data
    first = api.post("/api/v1/bookings", {"hold_id": hold["hold_id"]}).data
    second = api.post("/api/v1/bookings", {"hold_id": hold["hold_id"]}).data
    assert first["booking"]["id"] == second["booking"]["id"]
    assert first["payment_sheet"]["payment_intent_client_secret"] == second["payment_sheet"]["payment_intent_client_secret"]
    assert Payment.objects.count() == 1


def test_expired_hold_cannot_start_checkout(api, learner, session):
    api.force_authenticate(learner)
    hold = api.post("/api/v1/holds", {"session_id": str(session.pk), "seats": 1}).data
    with time_machine.travel(timezone.now() + timedelta(minutes=11)):
        res = api.post("/api/v1/bookings", {"hold_id": hold["hold_id"]})
    assert res.status_code == 410 and res.data["error"]["code"] == "hold_expired"


def test_slow_payment_after_hold_expired_still_confirms_if_seats_left(api, jobs, learner, session):
    booking = hold_and_checkout(api, learner, session=session)
    with time_machine.travel(timezone.now() + timedelta(minutes=15)):
        booking = pay(api, jobs, booking)
    assert booking.status == "confirmed"


def test_slow_payment_after_sell_out_is_fully_refunded(api, jobs, learner, session):
    Session.objects.filter(pk=session.pk).update(capacity=1)
    slow = hold_and_checkout(api, learner, session=session)
    other = make_user(email="fast@example.com", phone="+525512340000")
    with time_machine.travel(timezone.now() + timedelta(minutes=11)):
        fast = book(api, jobs, other, session)
        assert fast.status == "confirmed"
        slow = pay(api, jobs, slow)
    assert slow.status == "cancelled"
    assert slow.cancellations.get().reason_code == "sold_out"
    refund = slow.payments.get().refunds.get()
    assert refund.total_refund_cents == slow.total_cents and refund.status == "succeeded"
    assert ("refund", {"payment": slow.payments.get().external_id, "amount": slow.total_cents,
                       "key": refund.idempotency_key}) in FakeGateway.calls
    session.refresh_from_db()
    assert session.seats_booked == 1


def test_payment_failed(api, jobs, learner, session):
    booking = hold_and_checkout(api, learner, session=session)
    booking = pay(api, jobs, booking, kind="payment_failed")
    assert booking.status == "payment_failed" and not booking.seats_counted


def test_checkout_gateway_outage(api, learner, session):
    FakeGateway.fail_next = {"create_checkout"}
    api.force_authenticate(learner)
    hold = api.post("/api/v1/holds", {"session_id": str(session.pk), "seats": 1}).data
    res = api.post("/api/v1/bookings", {"hold_id": hold["hold_id"]})
    assert res.status_code == 502 and res.data["error"]["code"] == "payment_unavailable"


class TestApproval:
    @pytest.fixture
    def flagged(self, session, learner):
        Experience.objects.filter(pk=session.experience_id).update(requires_approval_below=Decimal("4.00"))
        learner.learner_profile.conduct_score = Decimal("3.20")
        learner.learner_profile.save()
        return session

    def test_new_learners_without_score_are_not_held_back(self, api, jobs, session):
        Experience.objects.filter(pk=session.experience_id).update(requires_approval_below=Decimal("4.00"))
        newbie = make_user(email="new@example.com", phone="+525512349999")
        assert book(api, jobs, newbie, session).status == "confirmed"

    def test_low_score_requires_approval_then_capture(self, api, jobs, learner, flagged, provider_user):
        booking = hold_and_checkout(api, learner, session=flagged)
        assert booking.payments.get().capture_manual
        booking = pay(api, jobs, booking, kind="payment_authorized")
        assert booking.status == "pending_approval" and booking.seats_counted and booking.approval_deadline
        assert Notification.objects.filter(kind="approval_requested", user=provider_user).exists()
        api.force_authenticate(provider_user)
        listed = api.get("/api/v1/provider/bookings", {"status": "pending_approval"}).data
        assert listed[0]["learner"]["conduct_score"] == "3.20"
        res = api.post(f"/api/v1/provider/bookings/{booking.pk}/approve")
        assert res.status_code == 200 and res.data["status"] == "confirmed"
        assert any(op == "capture" for op, _ in FakeGateway.calls)
        assert Transfer.objects.filter(booking=booking).exists()

    def test_decline_releases_seats_and_authorization(self, api, jobs, learner, flagged, provider_user):
        booking = pay(api, jobs, hold_and_checkout(api, learner, session=flagged), kind="payment_authorized")
        api.force_authenticate(provider_user)
        assert api.post(f"/api/v1/provider/bookings/{booking.pk}/decline").data["status"] == "declined"
        run_jobs(jobs)
        flagged.refresh_from_db()
        assert flagged.seats_booked == 0
        assert any(op == "cancel_authorization" for op, _ in FakeGateway.calls)
        assert Booking.objects.get(pk=booking.pk).payments.get().status == "canceled"

    def test_unanswered_requests_expire(self, api, jobs, learner, flagged):
        booking = pay(api, jobs, hold_and_checkout(api, learner, session=flagged), kind="payment_authorized")
        with time_machine.travel(booking.approval_deadline + timedelta(minutes=1)):
            assert services.expire_approvals() == 1
        assert Booking.objects.get(pk=booking.pk).status == "declined"

    def test_other_provider_cannot_decide(self, api, jobs, learner, flagged):
        from apps.accounts.models import ProviderProfile

        booking = pay(api, jobs, hold_and_checkout(api, learner, session=flagged), kind="payment_authorized")
        intruder = make_user(email="i@example.com", phone="+525512348888")
        ProviderProfile.objects.create(user=intruder, display_name="X")
        api.force_authenticate(intruder)
        assert api.post(f"/api/v1/provider/bookings/{booking.pk}/approve").status_code == 404
