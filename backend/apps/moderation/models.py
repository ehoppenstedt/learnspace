from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class ReasonCode(models.TextChoices):
    # Experience review
    INCOMPLETE_INFO = "incomplete_info", "Información incompleta / Incomplete information"
    LOW_QUALITY_MEDIA = "low_quality_media", "Fotos o videos de baja calidad / Low-quality media"
    MISLEADING = "misleading", "Contenido engañoso / Misleading content"
    PROHIBITED = "prohibited", "Actividad prohibida / Prohibited activity"
    UNSAFE = "unsafe", "Riesgo de seguridad / Safety risk"
    CONTACT_INFO = "contact_info", "Datos de contacto en el anuncio / Contact info in listing"
    PRICE_ISSUE = "price_issue", "Precio inconsistente / Price issue"
    LOCATION_ISSUE = "location_issue", "Ubicación inválida / Invalid location"
    DUPLICATE = "duplicate", "Duplicado / Duplicate"
    # Provider verification
    ID_UNREADABLE = "id_unreadable", "Identificación ilegible / ID unreadable"
    ID_MISMATCH = "id_mismatch", "Los datos no coinciden / Data mismatch"
    ID_EXPIRED = "id_expired", "Identificación vencida / ID expired"
    # Generic
    OTHER = "other", "Otro / Other"
    APPROVED = "approved", "Aprobado / Approved"


class AdminAction(BaseModel):
    """Append-only audit log. UPDATE/DELETE are blocked by a database trigger."""

    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=40)
    target_type = models.CharField(max_length=40)
    target_id = models.CharField(max_length=64)
    reason_code = models.CharField(max_length=40, blank=True)
    note = models.TextField(blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["target_type", "target_id"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.admin} {self.action} {self.target_type}:{self.target_id}"


class Report(BaseModel):
    class TargetType(models.TextChoices):
        EXPERIENCE = "experience"
        REVIEW = "review"
        MESSAGE = "message"
        USER = "user"

    class Status(models.TextChoices):
        OPEN = "open"
        ACTIONED = "actioned"
        DISMISSED = "dismissed"

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports_filed")
    target_type = models.CharField(max_length=12, choices=TargetType.choices)
    target_id = models.CharField(max_length=64)
    reason_code = models.CharField(max_length=40)
    details = models.TextField(blank=True, max_length=2000)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "created_at"])]
