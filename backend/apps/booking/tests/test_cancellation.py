from datetime import timedelta

import pytest
import time_machine
from django.utils import timezone

from apps.booking import services
from apps.booking.models import Booking, Cancellation
from apps.catalog.models import CancellationRule, Experience
from apps.moderation.models import Report
from apps.payments import services as payments
from apps.payments.gateways.fake import FakeGateway
from apps.payments.models import Transfer
from conftest import book, make_live_experience, make_user, run_jobs

pytestmark = pytest.mark.django_db


@pytest.fixture
def session(provider_user):
    return make_live_experience(provider_user, price_cents=50000).sessions.get()


@pytest.fixture
def booking(api, jobs, learner, session):
    return book(api, jobs, learner, session)  # listed 500.00, fee 50.00, total 550.00


def _cancel(api, booking, at):
    with time_machine.travel(at, tick=False):
        quote = api.get(f"/api/v1/bookings/{booking.pk}/cancellation-quote").data
        res = api.post(f"/api/v1/bookings/{booking.pk}/cancel", {"quote_token": quote["quote_token"]})
    return quote, res


def test_24h_or_more_refunds_everything_including_fee(api, jobs, booking, session):
    quote, res = _cancel(api, booking, booking.starts_at - timedelta(hours=30))
    assert (quote["listed_refund_cents"], quote["fee_refund_cents"], quote["refund_cents"]) == (50000, 5000, 55000)
    assert res.status_code == 200 and res.data["refund_cents"] == 55000
    run_jobs(jobs)
    booking.refresh_from_db()
    session.refresh_from_db()
    assert booking.status == "cancelled" and session.seats_booked == 0
    refund = booking.payments.get().refunds.get()
    assert (refund.total_refund_cents, refund.status) == (55000, "succeeded")
    assert booking.payments.get().status == "refunded"
    assert Transfer.objects.get(booking=booking).status == "canceled"  # provider owed nothing
    log = Cancellation.objects.get(booking=booking)
    assert log.actor_role == "learner" and log.rule_snapshot["listed_refund_pct"] == 100 and log.hours_before_start == 30


def test_exactly_24h_is_still_full_refund(api, booking):
    quote, _ = _cancel(api, booking, booking.starts_at - timedelta(hours=24))
    assert quote["refund_cents"] == 55000


def test_under_24h_refunds_half_of_listed_and_keeps_fee(api, jobs, booking):
    quote, res = _cancel(api, booking, booking.starts_at - timedelta(hours=23, minutes=59))
    assert (quote["listed_refund_cents"], quote["fee_refund_cents"], quote["refund_cents"]) == (25000, 0, 25000)
    run_jobs(jobs)
    transfer = Transfer.objects.get(booking=booking)
    assert transfer.gross_cents == 25000 and transfer.status == "scheduled"  # provider keeps the other half
    assert booking.payments.get().status == "partially_refunded"


def test_half_refund_rounds_half_up_on_odd_centavos(api, jobs, learner, provider_user):
    session = make_live_experience(provider_user, title="Clase de precio impar", price_cents=33333).sessions.get()
    b = book(api, jobs, learner, session)
    quote, _ = _cancel(api, b, b.starts_at - timedelta(hours=2))
    assert quote["listed_refund_cents"] == 16667  # 16666.5 -> 16667


def test_quote_cannot_be_reused_after_window_changes(api, booking):
    with time_machine.travel(booking.starts_at - timedelta(hours=24, seconds=30), tick=False):
        token = api.get(f"/api/v1/bookings/{booking.pk}/cancellation-quote").data["quote_token"]
    with time_machine.travel(booking.starts_at - timedelta(hours=23, minutes=59, seconds=30), tick=False):
        res = api.post(f"/api/v1/bookings/{booking.pk}/cancel", {"quote_token": token})
    assert res.status_code == 409 and res.data["error"]["code"] == "quote_changed"
    assert Booking.objects.get(pk=booking.pk).status == "confirmed"


def test_quote_expires_and_cannot_be_forged(api, booking):
    with time_machine.travel(booking.starts_at - timedelta(hours=40), tick=False):
        token = api.get(f"/api/v1/bookings/{booking.pk}/cancellation-quote").data["quote_token"]
    with time_machine.travel(booking.starts_at - timedelta(hours=40) + timedelta(minutes=3), tick=False):
        assert api.post(f"/api/v1/bookings/{booking.pk}/cancel", {"quote_token": token}).data["error"]["code"] == "quote_expired"
    assert api.post(f"/api/v1/bookings/{booking.pk}/cancel", {"quote_token": token[:-2] + "xx"}).status_code == 409


def test_cannot_cancel_after_start_or_someone_elses(api, booking):
    with time_machine.travel(booking.starts_at + timedelta(minutes=1)):
        assert api.get(f"/api/v1/bookings/{booking.pk}/cancellation-quote").data["error"]["code"] == "already_started"
    api.force_authenticate(make_user(email="o@example.com", phone="+525511119999"))
    assert api.get(f"/api/v1/bookings/{booking.pk}/cancellation-quote").status_code == 404


def test_policy_edits_do_not_affect_existing_bookings(api, booking):
    CancellationRule.objects.filter(policy__code="standard", applies_to="learner_cancel", min_hours_before=24).update(listed_refund_pct=10)
    quote, _ = _cancel(api, booking, booking.starts_at - timedelta(hours=30))
    assert quote["listed_refund_cents"] == 50000


def test_refund_failure_is_recorded_for_admin(api, jobs, booking):
    FakeGateway.fail_next = {"refund"}
    _cancel(api, booking, booking.starts_at - timedelta(hours=30))
    run_jobs(jobs)
    assert booking.payments.get().refunds.get().status == "failed"


class TestProviderCancellation:
    def test_everyone_refunded_in_full_and_penalty(self, api, jobs, booking, session, provider_user):
        other = book(api, jobs, make_user(email="b@example.com", phone="+525511112223"), session, seats=2)
        api.force_authenticate(provider_user)
        res = api.post(f"/api/v1/provider/sessions/{session.pk}/cancel", {"reason": "Enfermedad"})
        assert res.data["cancelled_bookings"] == 2
        run_jobs(jobs)
        for b in (booking, other):
            b.refresh_from_db()
            assert b.status == "cancelled"
            assert b.payments.get().refunds.get().total_refund_cents == b.total_cents  # fee included
            assert b.cancellations.get().actor_role == "provider"
        session.refresh_from_db()
        assert session.status == "cancelled" and session.seats_booked == 0
        provider_user.provider_profile.refresh_from_db()
        assert provider_user.provider_profile.penalty_points == 1

    def test_three_cancellations_in_90_days_pause_listings(self, api, jobs, learner, provider_user):
        experience = make_live_experience(provider_user)
        from apps.catalog import services as catalog

        start = experience.sessions.get().starts_at
        catalog.create_sessions(experience, [(start + timedelta(days=d), start + timedelta(days=d, hours=2)) for d in (1, 2)])
        api.force_authenticate(provider_user)
        for s in experience.sessions.all():
            book(api, jobs, learner, s)
            api.force_authenticate(provider_user)
            api.post(f"/api/v1/provider/sessions/{s.pk}/cancel")
        assert Experience.objects.get(pk=experience.pk).status == "paused"


class TestAttendance:
    def test_no_show_keeps_payment_and_can_be_disputed(self, api, jobs, booking, session, provider_user, learner):
        api.force_authenticate(provider_user)
        with time_machine.travel(session.starts_at + timedelta(minutes=30)):
            roster = api.get(f"/api/v1/provider/sessions/{session.pk}/roster").data
            assert roster["attendees"][0]["learner"]["first_name"] == "Ana"
            res = api.post(f"/api/v1/provider/sessions/{session.pk}/attendance",
                           {"marks": [{"booking_id": str(booking.pk), "attendance": "absent"}]}, format="json")
            assert res.data["updated"] == 1
        booking.refresh_from_db()
        assert booking.status == "no_show"
        assert Transfer.objects.get(booking=booking).gross_cents == 50000  # no-show rule: 0% refund
        api.force_authenticate(learner)
        with time_machine.travel(session.starts_at + timedelta(hours=3)):
            res = api.post(f"/api/v1/bookings/{booking.pk}/dispute-no-show", {"details": "Sí fui, llegué tarde."})
        assert res.status_code == 201
        assert Transfer.objects.get(booking=booking).status == "on_hold"
        assert Report.objects.get(target_id=str(booking.pk)).reason_code == "no_show_dispute"

    def test_attendance_window(self, api, booking, session, provider_user):
        api.force_authenticate(provider_user)
        marks = {"marks": [{"booking_id": str(booking.pk), "attendance": "present"}]}
        assert api.post(f"/api/v1/provider/sessions/{session.pk}/attendance", marks, format="json").status_code == 409
        with time_machine.travel(session.ends_at + timedelta(hours=49)):
            assert api.post(f"/api/v1/provider/sessions/{session.pk}/attendance", marks, format="json").status_code == 409

    def test_roster_shares_accessibility_needs_only_with_consent(self, api, jobs, session, provider_user):
        from apps.accounts.models import ConsentRecord

        user = make_user(email="acc@example.com", phone="+525511113334")
        user.learner_profile.accessibility_needs = "Uso silla de ruedas"
        user.learner_profile.save()
        book(api, jobs, user, session)
        api.force_authenticate(provider_user)
        row = api.get(f"/api/v1/provider/sessions/{session.pk}/roster").data["attendees"][0]
        assert row["learner"]["accessibility_needs"] is None
        ConsentRecord.objects.create(user=user, purpose="sensitive_accessibility", notice_version="v1")
        row = api.get(f"/api/v1/provider/sessions/{session.pk}/roster").data["attendees"][0]
        assert row["learner"]["accessibility_needs"] == "Uso silla de ruedas"


class TestTransfers:
    def test_released_after_class_with_withholding(self, api, jobs, booking, session):
        from apps.payments.models import WithholdingConfig

        Transfer.objects.filter(booking=booking).update(isr_bps=100, iva_bps=800)  # illustrative rates only
        payments.recompute_transfer(booking)
        assert payments.release_due_transfers(now=timezone.now()) == 0  # not yet
        with time_machine.travel(session.ends_at + timedelta(hours=48, minutes=1)):
            assert payments.release_due_transfers() == 1
        t = Transfer.objects.get(booking=booking)
        assert (t.gross_cents, t.isr_withheld_cents, t.iva_withheld_cents, t.net_cents) == (50000, 500, 4000, 45500)
        assert t.status == "sent" and ("transfer", {"amount": 45500, "destination": t.provider.payment_account.external_id,
                                                    "group": booking.code}) in FakeGateway.calls
        assert WithholdingConfig.objects.count() == 0  # rates come from the tax advisor, not defaults

    def test_moral_person_is_not_withheld(self, booking):
        from apps.payments.models import ProviderTaxProfile, WithholdingConfig

        WithholdingConfig.objects.create(isr_bps=100, iva_bps=800)
        provider = booking.experience.provider
        ProviderTaxProfile.objects.filter(provider=provider).update(person_type="moral")
        assert payments.current_withholding(provider) == (0, 0)

    def test_payouts_disabled_holds_then_resumes(self, api, jobs, booking, session):
        from apps.payments.gateways.base import AccountStatus

        account = booking.experience.provider.payment_account
        account.payouts_enabled = False
        account.save()
        with time_machine.travel(session.ends_at + timedelta(hours=49)):
            payments.release_due_transfers()
            assert Transfer.objects.get(booking=booking).status == "on_hold"
            payments.sync_account(account.external_id, AccountStatus(True, True, []))
            assert Transfer.objects.get(booking=booking).status == "scheduled"
            payments.release_due_transfers()
        assert Transfer.objects.get(booking=booking).status == "sent"

    def test_admin_refund_after_payout_reverses_transfer(self, api, jobs, booking, session):
        with time_machine.travel(session.ends_at + timedelta(hours=49)):
            payments.release_due_transfers()
        from django.db import transaction

        with transaction.atomic():
            payments.refund_payment(booking.payments.get(), listed_cents=20000, fee_cents=0, reason="dispute_resolution")
        run_jobs(jobs)
        t = Transfer.objects.get(booking=booking)
        assert t.gross_cents == 30000 and t.reversed_cents == 20000
        assert any(op == "reverse_transfer" and kw["amount"] == 20000 for op, kw in FakeGateway.calls)

    def test_chargeback_holds_transfer_and_opens_case(self, api, jobs, booking):
        from conftest import post_fake_event

        post_fake_event(api, "dispute_created", booking.payments.get().external_id, dispute_id="dp_1", reason="fraudulent")
        run_jobs(jobs)
        assert Transfer.objects.get(booking=booking).status == "on_hold"
        assert booking.payments.get().status == "disputed"
        assert Report.objects.filter(reason_code="chargeback").exists()


def test_completion_and_review_window(booking, session):
    with time_machine.travel(session.ends_at + timedelta(minutes=1)):
        assert services.complete_finished() == 1
    booking.refresh_from_db()
    assert booking.status == "completed" and booking.review_window_closes_at
