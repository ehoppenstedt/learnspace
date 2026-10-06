from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class FeeConfig(BaseModel):
    """Learner service fee, in basis points (500 = 5%). Latest row with effective_from <= now wins.

    Rows are never edited after they take effect; a change is a new row, so every booking
    can point at the exact fee it was charged.
    """

    fee_bps = models.PositiveIntegerField(help_text="Basis points. 500 = 5%. Includes IVA.")
    effective_from = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-effective_from"]
        constraints = [models.CheckConstraint(condition=models.Q(fee_bps__lte=5000), name="fee_bps_sane")]

    def __str__(self):
        return f"{self.fee_bps / 100:.2f}% from {self.effective_from:%Y-%m-%d %H:%M}"
