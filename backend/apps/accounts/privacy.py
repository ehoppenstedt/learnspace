"""LFPDPPP rights: access (export) and cancellation (account deletion by anonymization).

Deletion anonymizes instead of deleting rows: bookings, payments and refunds must be kept
for tax and dispute purposes, but they stop pointing at an identifiable person.
"""

import json

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.core.exceptions import DomainError
from apps.core.ids import uuid7

EXPORT_SALT = "data-export"
EXPORT_TTL = 60 * 60 * 24


def build_export(user) -> dict:
    from apps.booking.models import Booking
    from apps.notifications.models import Notification

    profile = getattr(user, "learner_profile", None)
    provider = getattr(user, "provider_profile", None)
    data = {
        "generated_at": timezone.now().isoformat(),
        "account": {
            "id": str(user.pk), "email": user.email, "phone": user.phone_e164, "first_name": user.first_name,
            "last_name": user.last_name, "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
            "ui_language": user.ui_language, "date_joined": user.date_joined.isoformat(),
        },
        "learner_profile": {
            "bio": profile.bio, "fluent_languages": profile.fluent_languages, "accessibility_needs": profile.accessibility_needs,
            "feed_filters": profile.feed_filters, "notification_prefs": profile.notification_prefs,
            "conduct_score": str(profile.conduct_score) if profile.conduct_score is not None else None,
        } if profile else None,
        "consents": [
            {"purpose": c.purpose, "notice_version": c.notice_version, "granted_at": c.granted_at.isoformat(),
             "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None}
            for c in user.consents.all()
        ],
        "interests": list(user.interests.values_list("category__slug", flat=True)),
        "sign_in_methods": list(user.identities.values_list("provider", flat=True)),
        "bookings": [
            {"code": b.code, "experience": b.experience.title, "status": b.status, "seats": b.seats,
             "starts_at": b.starts_at.isoformat(), "listed_cents": b.listed_cents, "fee_cents": b.fee_cents,
             "total_cents": b.total_cents,
             "cancellations": [{"at": c.cancelled_at.isoformat(), "by": c.actor_role, "refund_cents": c.refund_cents}
                               for c in b.cancellations.all()]}
            for b in Booking.objects.filter(learner=user).select_related("experience")
        ],
        "notifications": [
            {"kind": n.kind, "channel": n.channel, "status": n.status, "created_at": n.created_at.isoformat()}
            for n in Notification.objects.filter(user=user).order_by("-created_at")[:500]
        ],
    }
    if provider:
        data["provider_profile"] = {
            "display_name": provider.display_name, "about_me": provider.about_me, "about_school": provider.about_school,
            "verification_status": provider.verification_status,
            "experiences": list(provider.experiences.values("id", "title", "status")),
            "tax_profile": (lambda t: {"rfc": t.rfc, "legal_name": t.legal_name, "person_type": t.person_type} if t else None)(
                getattr(provider, "tax_profile", None)),
        }
    return data


def run_export(user_id) -> str:
    from apps.accounts.models import User
    from apps.catalog.storage import get_storage
    from apps.notifications.services import notify

    user = User.objects.get(pk=user_id)
    key = f"exports/{user.pk}/{uuid7()}.json"
    get_storage().write(key, json.dumps(build_export(user), ensure_ascii=False, indent=2, default=str).encode(), "application/json")
    token = signing.dumps({"u": str(user.pk), "k": key}, salt=EXPORT_SALT)
    url = f"{settings.PUBLIC_BASE_URL}/api/v1/me/data-export/{token}"
    notify(user, "data_export_ready", {"url": url}, dedupe=f"export:{key}", channels=("email",))
    return url


def read_export(token: str) -> bytes:
    from apps.catalog.storage import get_storage

    data = signing.loads(token, salt=EXPORT_SALT, max_age=EXPORT_TTL)
    return get_storage().read(data["k"])


def deletion_blockers(user) -> list[str]:
    from apps.booking.models import Booking
    from apps.payments.models import Transfer

    blockers = []
    if Booking.objects.filter(learner=user, status__in=["confirmed", "pending_approval"], ends_at__gt=timezone.now()).exists():
        blockers.append("upcoming_bookings")
    provider = getattr(user, "provider_profile", None)
    if provider:
        if Booking.objects.filter(experience__provider=provider, status__in=["confirmed", "pending_approval"],
                                  ends_at__gt=timezone.now()).exists():
            blockers.append("provider_upcoming_bookings")
        if Transfer.objects.filter(provider=provider, status__in=["scheduled", "on_hold"]).exists():
            blockers.append("pending_payouts")
    return blockers


def delete_account(user) -> None:
    from apps.notifications.models import Device

    blockers = deletion_blockers(user)
    if blockers:
        raise DomainError("deletion_blocked", _("Antes de eliminar tu cuenta, resuelve: %(b)s.") % {"b": ", ".join(blockers)},
                          fields={"blockers": blockers})
    with transaction.atomic():
        profile = getattr(user, "learner_profile", None)
        if profile:
            profile.bio, profile.fluent_languages, profile.accessibility_needs = "", [], None
            profile.feed_filters, profile.notification_prefs = {}, {}
            profile.save()
        provider = getattr(user, "provider_profile", None)
        if provider:
            provider.experiences.exclude(status="expired").update(status="expired")
            provider.display_name, provider.about_me, provider.about_school = "Cuenta eliminada", "", ""
            provider.save()
        user.identities.all().delete()
        user.interests.all().delete()
        Device.objects.filter(user=user).delete()
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        user.email = None
        user.phone_e164 = None
        user.first_name, user.last_name = "Usuario", "eliminado"
        user.date_of_birth = None
        user.email_verified = user.phone_verified = False
        user.status, user.is_active, user.deleted_at = user.Status.DELETED, False, timezone.now()
        user.set_unusable_password()
        user.save()
