import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

import jwt
import phonenumbers
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status

from apps.accounts.models import AuthIdentity, ConsentRecord, LearnerProfile, OTPChallenge, User
from apps.accounts.sms import get_sms_backend
from apps.core.exceptions import DomainError

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize_phone(raw: str) -> str:
    try:
        number = phonenumbers.parse(raw, "MX")
    except phonenumbers.NumberParseException as exc:
        raise DomainError("invalid_phone", _("Número de teléfono inválido."), status.HTTP_400_BAD_REQUEST) from exc
    if not phonenumbers.is_valid_number(number):
        raise DomainError("invalid_phone", _("Número de teléfono inválido."), status.HTTP_400_BAD_REQUEST)
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def normalize_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    if "@" not in email or len(email) > 254:
        raise DomainError("invalid_email", _("Correo electrónico inválido."), status.HTTP_400_BAD_REQUEST)
    return email


def normalize_destination(channel: str, raw: str) -> str:
    return normalize_phone(raw) if channel == OTPChallenge.Channel.SMS else normalize_email(raw)


# ---------------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------------


def _hash_code(challenge_id, code: str) -> str:
    msg = f"{challenge_id}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def request_otp(*, channel: str, destination: str, purpose: str = OTPChallenge.Purpose.LOGIN,
                user: User | None = None, ip: str | None = None) -> OTPChallenge:
    destination = normalize_destination(channel, destination)
    window_start = timezone.now() - timedelta(seconds=settings.OTP_DESTINATION_WINDOW_SECONDS)
    recent = OTPChallenge.objects.filter(destination=destination, created_at__gte=window_start).count()
    if recent >= settings.OTP_MAX_PER_DESTINATION:
        raise DomainError(
            "otp_rate_limited", _("Demasiados códigos solicitados. Intenta más tarde."),
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = OTPChallenge(
        channel=channel, purpose=purpose, destination=destination, user=user, ip=ip,
        expires_at=timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS),
    )
    challenge.code_hash = _hash_code(challenge.id, code)
    challenge.save()
    message = _("Tu código de %(brand)s es %(code)s. No lo compartas.") % {"brand": settings.BRAND_NAME, "code": code}
    if channel == OTPChallenge.Channel.SMS:
        get_sms_backend().send(destination, message)
    else:
        send_mail(_("Tu código de acceso"), message, None, [destination])
    return challenge


def check_otp(challenge_id, code: str, *, purpose: str) -> OTPChallenge:
    """Validates and consumes a challenge. The row lock serializes parallel guesses."""
    invalid = DomainError("otp_invalid", _("Código inválido o vencido."), status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        challenge = OTPChallenge.objects.select_for_update().filter(pk=challenge_id, purpose=purpose).first()
        if challenge is None or challenge.consumed_at or challenge.expires_at <= timezone.now():
            raise invalid
        if challenge.attempts >= settings.OTP_MAX_ATTEMPTS:
            raise DomainError(
                "otp_locked", _("Demasiados intentos. Solicita un código nuevo."), status.HTTP_429_TOO_MANY_REQUESTS
            )
        matched = hmac.compare_digest(challenge.code_hash, _hash_code(challenge.id, (code or "").strip()))
        if matched:
            challenge.consumed_at = timezone.now()
        else:
            challenge.attempts += 1
        challenge.save(update_fields=["consumed_at", "attempts", "updated_at"])
    # Raised outside the atomic block so the failed attempt is committed.
    if not matched:
        raise invalid
    return challenge


@dataclass
class LoginResult:
    user: User
    created: bool


def login_with_otp(challenge_id, code: str) -> LoginResult:
    challenge = check_otp(challenge_id, code, purpose=OTPChallenge.Purpose.LOGIN)
    if challenge.channel == OTPChallenge.Channel.SMS:
        lookup, verified_flag = {"phone_e164": challenge.destination}, "phone_verified"
    else:
        lookup, verified_flag = {"email": challenge.destination}, "email_verified"
    with transaction.atomic():
        user = User.objects.select_for_update().filter(**lookup).first()
        created = user is None
        if created:
            user = User.objects.create_user(**lookup, **{verified_flag: True})
            LearnerProfile.objects.create(user=user)
        elif not getattr(user, verified_flag):
            setattr(user, verified_flag, True)
            user.save(update_fields=[verified_flag])
    _ensure_active(user)
    return LoginResult(user=user, created=created)


def verify_phone_for_user(user: User, challenge_id, code: str) -> User:
    challenge = check_otp(challenge_id, code, purpose=OTPChallenge.Purpose.VERIFY_PHONE)
    if challenge.user_id != user.pk:
        raise DomainError("otp_invalid", _("Código inválido o vencido."), status.HTTP_400_BAD_REQUEST)
    if User.objects.filter(phone_e164=challenge.destination).exclude(pk=user.pk).exists():
        raise DomainError("phone_taken", _("Este teléfono ya está asociado a otra cuenta."))
    user.phone_e164 = challenge.destination
    user.phone_verified = True
    user.save(update_fields=["phone_e164", "phone_verified"])
    return user


def _ensure_active(user: User) -> None:
    if user.status != User.Status.ACTIVE or not user.is_active:
        raise DomainError("account_inactive", _("Esta cuenta no está activa."), status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Apple / Google
# ---------------------------------------------------------------------------

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _jwks_client(url: str) -> jwt.PyJWKClient:
    if url not in _jwks_clients:
        _jwks_clients[url] = jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)
    return _jwks_clients[url]


def _decode_id_token(token: str, *, jwks_url: str, issuers, audiences: list[str]) -> dict:
    if not audiences:
        raise DomainError("social_not_configured", "Social sign-in is not configured.", status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=audiences,
                            options={"require": ["exp", "iat", "iss", "sub", "aud"]})
    except jwt.PyJWTError as exc:
        raise DomainError("invalid_identity_token", _("No pudimos verificar tu identidad."), status.HTTP_401_UNAUTHORIZED) from exc
    if claims["iss"] not in (issuers if isinstance(issuers, tuple) else (issuers,)):
        raise DomainError("invalid_identity_token", _("No pudimos verificar tu identidad."), status.HTTP_401_UNAUTHORIZED)
    return claims


def verify_apple_token(identity_token: str, raw_nonce: str | None) -> dict:
    claims = _decode_id_token(identity_token, jwks_url=APPLE_JWKS_URL, issuers=APPLE_ISSUER,
                              audiences=settings.APPLE_CLIENT_IDS)
    if raw_nonce is not None:
        expected = hashlib.sha256(raw_nonce.encode()).hexdigest()
        if not hmac.compare_digest(claims.get("nonce", ""), expected):
            raise DomainError("invalid_identity_token", _("No pudimos verificar tu identidad."), status.HTTP_401_UNAUTHORIZED)
    return claims


def verify_google_token(id_token: str) -> dict:
    return _decode_id_token(id_token, jwks_url=GOOGLE_JWKS_URL, issuers=GOOGLE_ISSUERS,
                            audiences=settings.GOOGLE_CLIENT_IDS)


def _claim_true(value) -> bool:
    return value is True or str(value).lower() == "true"


def login_with_identity(provider: str, claims: dict) -> LoginResult:
    subject = claims["sub"]
    email = (claims.get("email") or "").lower()
    email_verified = bool(email) and _claim_true(claims.get("email_verified"))
    with transaction.atomic():
        identity = AuthIdentity.objects.select_related("user").filter(provider=provider, subject=subject).first()
        if identity:
            _ensure_active(identity.user)
            return LoginResult(identity.user, created=False)
        user = User.objects.filter(email=email).first() if email_verified else None
        created = user is None
        if created:
            # Never attach an email that another account already owns (unverified claims
            # must not take over or collide with an existing account).
            email_free = bool(email) and not User.objects.filter(email=email).exists()
            user = User.objects.create_user(email=email if email_free else None,
                                            email_verified=email_verified and email_free)
            LearnerProfile.objects.create(user=user)
        AuthIdentity.objects.create(user=user, provider=provider, subject=subject, email=email)
    _ensure_active(user)
    return LoginResult(user, created=created)


# ---------------------------------------------------------------------------
# Profile completion + consent
# ---------------------------------------------------------------------------


def record_consent(user: User, purpose: str) -> ConsentRecord:
    return ConsentRecord.objects.create(user=user, purpose=purpose, notice_version=settings.PRIVACY_NOTICE_VERSION)


def revoke_consent(user: User, purpose: str) -> None:
    ConsentRecord.objects.filter(user=user, purpose=purpose, revoked_at__isnull=True).update(revoked_at=timezone.now())
    profile = LearnerProfile.objects.filter(user=user).first()
    if profile is None:
        return
    # Withdrawing consent deletes the data it covered.
    if purpose == ConsentRecord.Purpose.ACCESSIBILITY:
        profile.accessibility_needs = None
        profile.save(update_fields=["accessibility_needs"])
    elif purpose == ConsentRecord.Purpose.FLUENT_LANGUAGES:
        profile.fluent_languages = []
        profile.save(update_fields=["fluent_languages"])


def has_consent(user: User, purpose: str) -> bool:
    return ConsentRecord.objects.filter(user=user, purpose=purpose, revoked_at__isnull=True).exists()
