import json
import time

import pytest
from django.core import mail

from apps.accounts import totp
from apps.accounts.models import AdminTOTPDevice, User
from conftest import book, make_live_experience, run_jobs

pytestmark = pytest.mark.django_db


def test_data_export(api, jobs, learner, provider_user):
    book(api, jobs, learner, make_live_experience(provider_user).sessions.get())
    api.force_authenticate(learner)
    assert api.post("/api/v1/me/data-export").status_code == 202
    run_jobs(jobs)
    link = next(m for m in mail.outbox if "datos" in m.subject).body.split("): ")[1].split()[0]
    api.force_authenticate(None)
    res = api.get(link.replace("http://testserver", ""))
    data = json.loads(res.content)
    assert data["account"]["email"] == learner.email and len(data["bookings"]) == 1
    assert api.get("/api/v1/me/data-export/forged").status_code == 404


def test_deletion_blocked_by_upcoming_booking(api, jobs, learner, provider_user):
    book(api, jobs, learner, make_live_experience(provider_user).sessions.get())
    api.force_authenticate(learner)
    res = api.delete("/api/v1/me")
    assert res.status_code == 409 and res.data["error"]["fields"]["blockers"] == ["upcoming_bookings"]


def test_deletion_anonymizes_and_revokes_tokens(api, learner):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = str(RefreshToken.for_user(learner))
    learner.learner_profile.accessibility_needs = "x"
    learner.learner_profile.save()
    api.force_authenticate(learner)
    assert api.delete("/api/v1/me").status_code == 204
    user = User.objects.get(pk=learner.pk)
    assert (user.email, user.phone_e164, user.date_of_birth, user.status) == (None, None, None, "deleted")
    assert user.learner_profile.accessibility_needs is None
    api.force_authenticate(None)
    assert api.post("/api/v1/auth/refresh", {"refresh": refresh}).status_code == 401


class TestAdmin2FA:
    def test_totp_known_vector(self):
        # RFC 6238 test secret "12345678901234567890" at T=59 -> 287082 (6 digits)
        import base64

        secret = base64.b32encode(b"12345678901234567890").decode()
        assert totp.code_at(secret, 59) == "287082"

    def test_login_requires_code_when_enrolled_and_blocks_replay(self, client, admin_user):
        device = AdminTOTPDevice.objects.create(user=admin_user, secret=totp.generate_secret(), confirmed=True)
        creds = {"username": admin_user.email, "password": "correct-horse-battery-staple"}
        res = client.post("/admin/login/", creds)
        assert res.status_code == 200 and "2FA" in res.content.decode()
        code = totp.code_at(device.secret)
        assert client.post("/admin/login/", {**creds, "otp": code}).status_code == 302
        client.logout()
        assert client.post("/admin/login/", {**creds, "otp": code}).status_code == 200  # same code can't be reused

    def test_unenrolled_staff_refused_when_required(self, client, admin_user, settings):
        settings.ADMIN_REQUIRE_2FA = True
        res = client.post("/admin/login/", {"username": admin_user.email, "password": "correct-horse-battery-staple"})
        assert res.status_code == 200 and "enable_admin_2fa" in res.content.decode()

    def test_enrollment_command(self, admin_user):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("enable_admin_2fa", admin_user.email, stdout=out)
        device = AdminTOTPDevice.objects.get(user=admin_user)
        assert "otpauth://" in out.getvalue() and not device.confirmed
        call_command("enable_admin_2fa", admin_user.email, code=totp.code_at(device.secret, time.time()), stdout=out)
        assert AdminTOTPDevice.objects.get(user=admin_user).confirmed


def test_twilio_backend_request(settings):
    from unittest import mock

    from apps.accounts.sms import TwilioSMSBackend

    settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_FROM_NUMBER = "AC1", "tok", "+15550001111"
    response = mock.MagicMock(status=201)
    response.__enter__.return_value = response
    with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
        TwilioSMSBackend().send("+525512345678", "Tu código es 123456")
    request = urlopen.call_args.args[0]
    assert request.full_url.endswith("/Accounts/AC1/Messages.json")
    assert b"To=%2B525512345678" in request.data and request.headers["Authorization"].startswith("Basic ")
