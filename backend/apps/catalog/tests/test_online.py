from datetime import timedelta

import pytest
import time_machine

from apps.booking import services as booking_services
from apps.catalog.models import Experience
from apps.notifications.models import Notification
from conftest import ROMA_NORTE, auth, book, make_live_experience

pytestmark = pytest.mark.django_db
URL = "https://meet.example.com/acuarela"


@pytest.fixture
def online(provider_user):
    exp = make_live_experience(provider_user, title="Acuarela en línea")
    Experience.objects.filter(pk=exp.pk).update(modality="online", online_url=URL)
    exp.refresh_from_db()
    return exp


def feed_titles(api, **headers):
    res = api.get("/api/v1/experiences", {"lat": ROMA_NORTE[0], "lng": ROMA_NORTE[1], "radius_km": 10}, **headers)
    return [r["title"] for r in res.data["results"]]


def test_online_hidden_on_ios_until_store_decision(api, online, settings):
    assert "Acuarela en línea" in feed_titles(api, HTTP_X_CLIENT_PLATFORM="android")
    assert "Acuarela en línea" not in feed_titles(api, HTTP_X_CLIENT_PLATFORM="ios")
    assert api.get(f"/api/v1/experiences/{online.pk}", HTTP_X_CLIENT_PLATFORM="ios").status_code == 404
    settings.ONLINE_EXPERIENCES_ON_IOS = True
    assert "Acuarela en línea" in feed_titles(api, HTTP_X_CLIENT_PLATFORM="ios")


def test_ios_cannot_hold_online_seats(api, learner, online):
    res = auth(api, learner).post("/api/v1/holds", {"seats": 1, "session_id": str(online.sessions.get().pk)},
                                  format="json", HTTP_X_CLIENT_PLATFORM="ios")
    assert res.status_code == 403 and res.data["error"]["code"] == "not_available_on_platform"


def test_link_only_after_booking(api, jobs, learner, online):
    detail = api.get(f"/api/v1/experiences/{online.pk}").data
    assert detail["location"]["online"] is True and detail["location"]["url"] is None
    booking = book(api, jobs, learner, online.sessions.get())
    assert auth(api, learner).get(f"/api/v1/experiences/{online.pk}").data["location"]["url"] == URL
    assert api.get(f"/api/v1/bookings/{booking.pk}").data["location"]["url"] == URL
    assert URL in booking_services.booking_ics(booking)


def test_reminder_carries_link(api, jobs, learner, online):
    booking = book(api, jobs, learner, online.sessions.get())
    with time_machine.travel(booking.starts_at - timedelta(hours=2, minutes=-1), tick=False):
        booking_services.send_reminders()
    n = Notification.objects.get(kind="reminder_2h", channel="email")
    assert URL in str(n.payload)
