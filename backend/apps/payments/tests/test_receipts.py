from datetime import timedelta

import pytest
import time_machine
from django.utils import timezone

from apps.payments import services as payments
from conftest import book, make_live_experience, make_user

pytestmark = pytest.mark.django_db


def _get(api, url):
    api.force_authenticate(None)
    return api.get(url.replace("http://testserver", ""))


def test_booking_receipt(api, jobs, learner, provider_user):
    booking = book(api, jobs, learner, make_live_experience(provider_user, price_cents=50000).sessions.get(), seats=2)
    api.force_authenticate(learner)
    url = api.get(f"/api/v1/bookings/{booking.pk}/receipt").data["url"]
    res = _get(api, url)
    html = res.content.decode()
    assert res.status_code == 200 and res["Content-Type"].startswith("text/html")
    assert booking.code in html and "$1,100.00 MXN" in html and "$100.00 MXN" in html  # total and 10% fee
    assert "no es un comprobante fiscal" in html and "Modo de prueba" in html


def test_receipt_only_for_own_booking_and_signed(api, jobs, learner, provider_user):
    booking = book(api, jobs, learner, make_live_experience(provider_user).sessions.get())
    api.force_authenticate(make_user(email="z@example.com", phone="+525511110000"))
    assert api.get(f"/api/v1/bookings/{booking.pk}/receipt").status_code == 404
    assert api.get("/api/v1/receipts/forged-token").status_code == 404


def test_provider_monthly_statement(api, jobs, learner, provider_user):
    session = make_live_experience(provider_user, price_cents=50000).sessions.get()
    booking = book(api, jobs, learner, session)
    with time_machine.travel(session.ends_at + timedelta(hours=49)):
        payments.release_due_transfers()
    month = timezone.localtime(booking.transfer.release_at).strftime("%Y-%m")
    api.force_authenticate(provider_user)
    assert api.get("/api/v1/provider/statements", {"month": "2026-13"}).status_code == 400
    html = _get(api, api.get("/api/v1/provider/statements", {"month": month}).data["url"]).content.decode()
    assert booking.code in html and "$500.00 MXN" in html and "Estado de cuenta" in html


def test_earnings_flags_missing_withholding_rates(api, provider_user):
    from apps.payments.models import WithholdingConfig

    api.force_authenticate(provider_user)
    data = api.get("/api/v1/provider/earnings").data
    assert data["withholding_configured"] is False and data["test_mode"] is True
    WithholdingConfig.objects.create(isr_bps=100, iva_bps=800)
    assert api.get("/api/v1/provider/earnings").data["withholding_configured"] is True
