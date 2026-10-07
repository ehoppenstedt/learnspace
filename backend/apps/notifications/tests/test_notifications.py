from datetime import timedelta

import pytest
import time_machine
from django.core import mail

from apps.booking import services as booking_services
from apps.notifications.models import Device, Notification
from apps.notifications.push import LocmemPushBackend
from apps.notifications.services import notify
from conftest import book, make_live_experience, run_jobs

pytestmark = pytest.mark.django_db


def test_dedupe_means_once_per_channel(learner, jobs):
    Device.objects.create(user=learner, expo_token="ExponentPushToken[abc]")
    for _ in range(3):
        notify(learner, "payment_failed", {"title": "X", "booking_id": "1"}, dedupe="payment_failed:1")
    run_jobs(jobs)
    assert Notification.objects.count() == 2  # push + email
    assert len(LocmemPushBackend.outbox) == 1 and len(mail.outbox) == 1
    assert LocmemPushBackend.outbox[0]["data"]["url"] == "learnspace://bookings/1"


def test_push_without_devices_is_skipped(learner, jobs):
    notify(learner, "payment_failed", {"title": "X"}, dedupe="k", channels=("push",))
    run_jobs(jobs)
    assert Notification.objects.get().status == "skipped"


def test_language_follows_user(learner, jobs):
    learner.ui_language = "en"
    learner.save()
    notify(learner, "payment_failed", {"title": "Pottery"}, dedupe="k2", channels=("email",))
    run_jobs(jobs)
    assert mail.outbox[0].subject == "Payment not completed"


def test_reminders_respect_prefs_and_fire_once(api, jobs, learner, provider_user):
    session = make_live_experience(provider_user).sessions.get()
    booking = book(api, jobs, learner, session)
    with time_machine.travel(booking.starts_at - timedelta(hours=24) + timedelta(minutes=2)):
        assert booking_services.send_reminders() == 1
        booking_services.send_reminders()  # next scheduler tick: same window
    with time_machine.travel(booking.starts_at - timedelta(hours=2) + timedelta(minutes=2)):
        booking_services.send_reminders()
    kinds = list(Notification.objects.filter(user=learner, kind__startswith="reminder").values_list("kind", "channel"))
    assert sorted(kinds) == [("reminder_24h", "email"), ("reminder_24h", "push"), ("reminder_2h", "email"), ("reminder_2h", "push")]

    learner.learner_profile.notification_prefs = {"push": True, "email": True, "reminders": False}
    learner.learner_profile.save()
    Notification.objects.filter(kind__startswith="reminder").delete()
    with time_machine.travel(booking.starts_at - timedelta(hours=2) + timedelta(minutes=2)):
        booking_services.send_reminders()
    assert not Notification.objects.filter(kind__startswith="reminder").exists()


def test_device_registration_and_prefs_api(api, learner):
    api.force_authenticate(learner)
    assert api.post("/api/v1/me/devices", {"expo_token": "ExponentPushToken[xyz]", "platform": "ios"}).status_code == 204
    assert api.post("/api/v1/me/devices", {"expo_token": "not-a-token"}).status_code == 400
    assert api.put("/api/v1/me/notification-prefs", {"push": False, "email": True, "reminders": True}).data["push"] is False
