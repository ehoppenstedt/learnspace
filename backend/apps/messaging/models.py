from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class MessageThread(BaseModel):
    """One conversation per learner and experience: starts as a pre-booking question,
    continues after booking (booking is linked when one exists)."""

    experience = models.ForeignKey("catalog.Experience", on_delete=models.CASCADE, related_name="threads")
    learner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="threads_as_learner")
    provider = models.ForeignKey("accounts.ProviderProfile", on_delete=models.CASCADE, related_name="threads")
    booking = models.ForeignKey("booking.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    learner_read_at = models.DateTimeField(null=True, blank=True)
    provider_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["experience", "learner"], name="uniq_thread")]


class Message(BaseModel):
    thread = models.ForeignKey(MessageThread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    body = models.TextField(max_length=2000)
    # Contact/payment details detected before a booking existed (sent after an explicit warning).
    detected = models.JSONField(default=list, blank=True)
    hidden = models.BooleanField(default=False, help_text="Removed by admin after a report")

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["thread", "created_at"])]
