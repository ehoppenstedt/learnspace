from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Device(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="devices")
    expo_token = models.CharField(max_length=200, unique=True)
    platform = models.CharField(max_length=10, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)


class Notification(BaseModel):
    """One message to one user on one channel. dedupe_key makes every send idempotent
    (a retried job or a re-run scheduler never double-notifies)."""

    class Channel(models.TextChoices):
        PUSH = "push"
        EMAIL = "email"

    class Status(models.TextChoices):
        PENDING = "pending"
        SENT = "sent"
        SKIPPED = "skipped"
        FAILED = "failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=40)
    channel = models.CharField(max_length=5, choices=Channel.choices)
    payload = models.JSONField(default=dict)
    dedupe_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    sent_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
