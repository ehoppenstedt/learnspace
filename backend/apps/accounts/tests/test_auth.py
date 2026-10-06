import time
from datetime import date, timedelta
from unittest import mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.utils import timezone

from apps.accounts import services
from apps.accounts.models import AuthIdentity, ConsentRecord, OTPChallenge, User
from apps.accounts.sms import LocmemSMSBackend
from conftest import auth, make_user

pytestmark = pytest.mark.django_db


def _code_from_sms() -> str:
    return LocmemSMSBackend.outbox[-1][1].split(" es ")[1][:6]


def _request(api, phone="55 1234 5678"):
    res = api.post("/api/v1/auth/otp/request", {"channel": "sms", "destination": phone})
    assert res.status_code == 202, res.content
    return res.data["challenge_id"]


class TestOTPLogin:
    def test_new_phone_creates_account_and_returns_tokens(self, api):
        challenge = _request(api)
        assert LocmemSMSBackend.outbox[-1][0] == "+525512345678"
        res = api.post("/api/v1/auth/otp/verify", {"challenge_id": challenge, "code": _code_from_sms()})
        assert res.status_code == 200, res.content
        assert res.data["created"] is True
        assert res.data["access"] and res.data["refresh"]
        assert res.data["user"]["phone_verified"] is True
        assert res.data["user"]["profile_complete"] is False

    def test_existing_user_logs_in(self, api, learner):
        challenge = _request(api, learner.phone_e164)
        res = api.post("/api/v1/auth/otp/verify", {"challenge_id": challenge, "code": _code_from_sms()})
        assert res.data["created"] is False
        assert res.data["user"]["id"] == str(learner.pk)

    def test_code_is_single_use(self, api):
        challenge = _request(api)
        code = _code_from_sms()
        assert api.post("/api/v1/auth/otp/verify", {"challenge_id": challenge, "code": code}).status_code == 200
        res = api.post("/api/v1/auth/otp/verify", {"challenge_id": challenge, "code": code})
        assert res.status_code == 400
        assert res.data["error"]["code"] == "otp_invalid"

    def test_wrong_code_counts_attempts_and_locks(self, api, settings):
        challenge = _request(api)
        good = _code_from_sms()
        bad = "000000" if good != "000000" else "111111"
        for _ in range(settings.OTP_MAX_ATTEMPTS):
            assert api.post("/api/v1/auth/otp/verify", {"challenge_id": challenge, "code": bad}).status_code == 400
        assert OTPChallenge.objects.get(pk=challenge).attempts == settings.OTP_MAX_ATTEMPTS
        res = api.post("/api/v1/auth/otp/verify", {"challenge_id": challenge, "code": good})
        assert res.status_code == 429
        assert res.data["error"]["code"] == "otp_locked"

    def test_expired_code_rejected(self, api):
        challenge = _request(api)
        OTPChallenge.objects.filter(pk=challenge).update(expires_at=timezone.now() - timedelta(seconds=1))
        res = api.post("/api/v1/auth/otp/verify", {"challenge_id": challenge, "code": _code_from_sms()})
        assert res.status_code == 400

    def test_per_destination_rate_limit(self, api, settings):
        for _ in range(settings.OTP_MAX_PER_DESTINATION):
            _request(api)
        res = api.post("/api/v1/auth/otp/request", {"channel": "sms", "destination": "5512345678"})
        assert res.status_code == 429
        assert res.data["error"]["code"] == "otp_rate_limited"

    def test_per_ip_throttle(self, api, settings):
        settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "otp_request_ip": "2/hour"}}
        from rest_framework.throttling import SimpleRateThrottle

        with mock.patch.object(SimpleRateThrottle, "THROTTLE_RATES", settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]):
            api.post("/api/v1/auth/otp/request", {"channel": "sms", "destination": "5511111111"})
            api.post("/api/v1/auth/otp/request", {"channel": "sms", "destination": "5522222222"})
            res = api.post("/api/v1/auth/otp/request", {"channel": "sms", "destination": "5533333333"})
        assert res.status_code == 429

    def test_invalid_phone(self, api):
        res = api.post("/api/v1/auth/otp/request", {"channel": "sms", "destination": "123"})
        assert res.status_code == 400
        assert res.data["error"]["code"] == "invalid_phone"

    def test_code_hash_not_plaintext(self, api):
        challenge = _request(api)
        assert _code_from_sms() not in OTPChallenge.objects.get(pk=challenge).code_hash

    def test_email_channel(self, api, mailoutbox):
        res = api.post("/api/v1/auth/otp/request", {"channel": "email", "destination": "Nuevo@Example.com"})
        assert res.status_code == 202
        code = mailoutbox[-1].body.split(" es ")[1][:6]
        res = api.post("/api/v1/auth/otp/verify", {"challenge_id": res.data["challenge_id"], "code": code})
        assert res.data["user"]["email"] == "nuevo@example.com"
        assert res.data["user"]["phone_verified"] is False


def _payload(**overrides):
    data = {"first_name": "Luis", "last_name": "Pérez", "email": "luis@example.com",
            "date_of_birth": "1995-02-01", "accept_privacy_notice": True}
    data.update(overrides)
    return data


class TestCompleteProfile:
    @pytest.fixture
    def fresh(self, db):
        return User.objects.create_user(phone_e164="+525500000001", phone_verified=True)

    def test_completes_and_records_privacy_consent(self, api, fresh):
        res = auth(api, fresh).post("/api/v1/me/complete-profile", _payload())
        assert res.status_code == 200, res.content
        assert res.data["profile_complete"] is True
        assert ConsentRecord.objects.filter(user=fresh, purpose="privacy_notice").exists()

    @pytest.mark.parametrize(("today", "dob", "ok"), [
        (date(2026, 10, 6), date(2008, 10, 6), True),    # 18th birthday today
        (date(2026, 10, 6), date(2008, 10, 7), False),   # turns 18 tomorrow
        (date(2026, 10, 6), date(2015, 1, 1), False),
        (date(2026, 2, 28), date(2008, 2, 29), False),   # leap-day birthday: not 18 until Mar 1
        (date(2026, 3, 1), date(2008, 2, 29), True),
    ])
    def test_18_plus_gate(self, api, fresh, today, dob, ok):
        with mock.patch("apps.accounts.serializers.local_today", return_value=today):
            res = auth(api, fresh).post("/api/v1/me/complete-profile", _payload(date_of_birth=dob.isoformat()))
        assert (res.status_code == 200) is ok, res.content
        if not ok:
            assert "date_of_birth" in res.data["error"]["fields"]

    def test_requires_privacy_acceptance(self, api, fresh):
        res = auth(api, fresh).post("/api/v1/me/complete-profile", _payload(accept_privacy_notice=False))
        assert res.status_code == 400

    def test_requires_verified_phone(self, api, db):
        user = User.objects.create_user(email="x@example.com", email_verified=True)
        res = auth(api, user).post("/api/v1/me/complete-profile", _payload())
        assert res.status_code == 400
        assert res.data["error"]["code"] == "phone_not_verified"

    def test_accessibility_needs_require_express_consent(self, api, fresh):
        res = auth(api, fresh).post("/api/v1/me/complete-profile", _payload(accessibility_needs="Silla de ruedas"))
        assert res.status_code == 400
        assert "consent_accessibility" in res.data["error"]["fields"]
        res = api.post("/api/v1/me/complete-profile",
                       _payload(accessibility_needs="Silla de ruedas", consent_accessibility=True))
        assert res.status_code == 200
        assert res.data["has_accessibility_needs"] is True
        assert ConsentRecord.objects.filter(user=fresh, purpose="sensitive_accessibility").exists()

    def test_revoking_consent_deletes_data(self, api, fresh):
        auth(api, fresh).post("/api/v1/me/complete-profile",
                              _payload(accessibility_needs="Silla de ruedas", consent_accessibility=True))
        assert api.delete("/api/v1/me/consents/sensitive_accessibility").status_code == 204
        fresh.learner_profile.refresh_from_db()
        assert fresh.learner_profile.accessibility_needs is None

    def test_email_unique(self, api, fresh, learner):
        res = auth(api, fresh).post("/api/v1/me/complete-profile", _payload(email=learner.email.upper()))
        assert res.status_code == 400

    def test_phone_verification_for_email_users(self, api, db):
        user = User.objects.create_user(email="y@example.com", email_verified=True)
        auth(api, user)
        res = api.post("/api/v1/me/phone", {"phone": "5544443333"})
        assert res.status_code == 202
        res = api.post("/api/v1/me/phone/verify", {"challenge_id": res.data["challenge_id"], "code": _code_from_sms()})
        assert res.status_code == 200
        assert res.data["phone_verified"] is True

    def test_profile_required_to_become_provider(self, api, fresh):
        assert auth(api, fresh).post("/api/v1/provider/activate").status_code == 403


class TestSocial:
    @pytest.fixture
    def signer(self, settings):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        settings.APPLE_CLIENT_IDS = ["com.learnspace.app"]
        settings.GOOGLE_CLIENT_IDS = ["web-client.apps.googleusercontent.com"]

        class FakeJWKS:
            def get_signing_key_from_jwt(self, token):
                return mock.Mock(key=key.public_key())

        with mock.patch.object(services, "_jwks_client", return_value=FakeJWKS()):
            def sign(**claims):
                now = int(time.time())
                base = {"iat": now, "exp": now + 600, "sub": "sub-1"}
                return jwt.encode({**base, **claims}, key, algorithm="RS256")
            yield sign

    def test_apple_creates_user_with_nonce(self, api, signer):
        import hashlib

        token = signer(iss="https://appleid.apple.com", aud="com.learnspace.app", email="a@privaterelay.appleid.com",
                       email_verified="true", nonce=hashlib.sha256(b"raw").hexdigest())
        res = api.post("/api/v1/auth/apple", {"identity_token": token, "nonce": "raw", "first_name": "Eva"})
        assert res.status_code == 200, res.content
        assert res.data["created"] is True
        assert AuthIdentity.objects.filter(provider="apple", subject="sub-1").exists()
        # Second login returns the same user
        res2 = api.post("/api/v1/auth/apple", {"identity_token": token, "nonce": "raw"})
        assert res2.data["user"]["id"] == res.data["user"]["id"]

    def test_apple_rejects_wrong_nonce(self, api, signer):
        token = signer(iss="https://appleid.apple.com", aud="com.learnspace.app", nonce="nope")
        assert api.post("/api/v1/auth/apple", {"identity_token": token, "nonce": "raw"}).status_code == 401

    def test_apple_rejects_wrong_audience(self, api, signer):
        token = signer(iss="https://appleid.apple.com", aud="com.other.app")
        assert api.post("/api/v1/auth/apple", {"identity_token": token}).status_code == 401

    def test_google_links_to_existing_verified_email(self, api, signer, learner):
        token = signer(iss="https://accounts.google.com", aud="web-client.apps.googleusercontent.com",
                       email=learner.email, email_verified=True, sub="g-1")
        res = api.post("/api/v1/auth/google", {"id_token": token})
        assert res.status_code == 200
        assert res.data["user"]["id"] == str(learner.pk)

    def test_google_unverified_email_does_not_take_over_account(self, api, signer, learner):
        token = signer(iss="https://accounts.google.com", aud="web-client.apps.googleusercontent.com",
                       email=learner.email, email_verified=False, sub="g-2")
        res = api.post("/api/v1/auth/google", {"id_token": token})
        assert res.status_code == 200
        assert res.data["user"]["id"] != str(learner.pk)

    def test_expired_token(self, api, signer):
        token = signer(iss="https://accounts.google.com", aud="web-client.apps.googleusercontent.com",
                       exp=int(time.time()) - 10)
        assert api.post("/api/v1/auth/google", {"id_token": token}).status_code == 401


def test_refresh_rotation_and_logout(api, learner):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = str(RefreshToken.for_user(learner))
    res = api.post("/api/v1/auth/refresh", {"refresh": refresh})
    assert res.status_code == 200
    new_refresh = res.data["refresh"]
    # Old refresh token is blacklisted after rotation.
    assert api.post("/api/v1/auth/refresh", {"refresh": refresh}).status_code == 401
    assert api.post("/api/v1/auth/logout", {"refresh": new_refresh}).status_code == 204
    assert api.post("/api/v1/auth/refresh", {"refresh": new_refresh}).status_code == 401


def test_suspended_user_cannot_log_in(api):
    user = make_user(email="s@example.com", phone="+525511112222")
    user.status = User.Status.SUSPENDED
    user.save()
    challenge = _request(api, user.phone_e164)
    res = api.post("/api/v1/auth/otp/verify", {"challenge_id": challenge, "code": _code_from_sms()})
    assert res.status_code == 403
