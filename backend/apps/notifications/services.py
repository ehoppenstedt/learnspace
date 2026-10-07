import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from apps.notifications.messages import MESSAGES, OPTIONAL_KINDS
from apps.notifications.models import Device, Notification
from apps.notifications.push import get_push_backend

logger = logging.getLogger(__name__)

DEFAULT_PREFS = {"push": True, "email": True, "reminders": True}


def prefs_for(user) -> dict:
    profile = getattr(user, "learner_profile", None)
    return {**DEFAULT_PREFS, **((profile.notification_prefs if profile else None) or {})}


def notify(user, kind: str, context: dict, *, dedupe: str, channels=("push", "email")) -> list[Notification]:
    """Queue a message. Same dedupe key => sent at most once per channel, ever."""
    if kind not in MESSAGES:
        raise ValueError(f"unknown notification kind {kind}")
    if user.status != "active":
        return []
    prefs = prefs_for(user)
    if kind in OPTIONAL_KINDS and not prefs["reminders"]:
        return []
    created = []
    for channel in channels:
        if channel == "push" and not prefs["push"]:
            continue
        if channel == "email" and (not user.email or (kind in OPTIONAL_KINDS and not prefs["email"])):
            continue
        notification, is_new = Notification.objects.get_or_create(
            dedupe_key=f"{dedupe}:{channel}"[:160],
            defaults={"user": user, "kind": kind, "channel": channel, "payload": context},
        )
        if is_new:
            created.append(notification)
            from apps.notifications.tasks import send_notification_task

            transaction.on_commit(lambda pk=str(notification.pk): send_notification_task.defer(notification_id=pk))
    return created


def render(notification: Notification) -> tuple[str, str]:
    lang = notification.user.ui_language if notification.user.ui_language in ("es", "en") else "es"
    title, body = MESSAGES[notification.kind][lang]
    ctx = notification.payload
    return title.format(**ctx), body.format(**ctx)


def send(notification_id) -> Notification:
    notification = Notification.objects.select_related("user").get(pk=notification_id)
    if notification.status != Notification.Status.PENDING:
        return notification
    title, body = render(notification)
    try:
        if notification.channel == Notification.Channel.PUSH:
            tokens = list(Device.objects.filter(user=notification.user).values_list("expo_token", flat=True))
            if not tokens:
                notification.status = Notification.Status.SKIPPED
            else:
                dead = get_push_backend().send(tokens, title, body, {"kind": notification.kind, **_deeplink(notification)})
                Device.objects.filter(expo_token__in=dead).delete()
                notification.status = Notification.Status.SENT
        else:
            message = EmailMessage(subject=title, body=f"{body}\n\n— {settings.BRAND_NAME}", to=[notification.user.email])
            ics = notification.payload.get("ics")
            if ics:
                message.attach("clase.ics", ics, "text/calendar")
            message.send()
            notification.status = Notification.Status.SENT
    except Exception as exc:  # delivery failures must not break the job queue
        logger.exception("notification failed", extra={"notification_id": str(notification.pk)})
        notification.status, notification.error = Notification.Status.FAILED, str(exc)[:500]
    notification.sent_at = timezone.now()
    notification.save(update_fields=["status", "error", "sent_at", "updated_at"])
    return notification


def _deeplink(notification) -> dict:
    if thread_id := notification.payload.get("thread_id"):
        return {"url": f"learnspace://inbox/{thread_id}"}
    booking_id = notification.payload.get("booking_id")
    return {"url": f"learnspace://bookings/{booking_id}"} if booking_id else {}
