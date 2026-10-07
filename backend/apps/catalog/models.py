from datetime import time

from django.conf import settings
from django.contrib.gis.db import models as gis
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db import models
from django.db.models.functions import Upper
from django.utils import timezone
from django.utils.translation import get_language

from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel

MX_TZ = "America/Mexico_City"


class Category(models.Model):
    slug = models.SlugField(unique=True)
    name_es = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80)
    icon = models.CharField(max_length=40, blank=True, help_text="Icon name used by the mobile app")
    cover_url = models.URLField(blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "slug"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name_es

    @property
    def name(self) -> str:
        return self.name_en if (get_language() or "es").startswith("en") else self.name_es


class Area(models.Model):
    """Seeded neighborhoods. Fallback location when the user denies GPS permission."""

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    borough = models.CharField(max_length=80, help_text="Alcaldía")
    city = models.CharField(max_length=80, default="Ciudad de México")
    centroid = gis.PointField(geography=True, srid=4326)

    class Meta:
        ordering = ["name"]
        indexes = [GinIndex(OpClass(Upper("name"), name="gin_trgm_ops"), name="area_name_trgm")]

    def __str__(self):
        return f"{self.name}, {self.borough}"


class MediaAsset(BaseModel):
    class Kind(models.TextChoices):
        IMAGE = "image"
        VIDEO = "video"
        DOCUMENT = "document"  # private verification documents

    class Status(models.TextChoices):
        PENDING_UPLOAD = "pending_upload"
        PROCESSING = "processing"
        READY = "ready"
        REJECTED = "rejected"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="media")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    content_type = models.CharField(max_length=100)
    declared_bytes = models.PositiveBigIntegerField()
    storage_key = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING_UPLOAD)
    rejection_reason = models.CharField(max_length=80, blank=True)
    # {"w400": key, "w800": key, "w1600": key} for images; {"mp4": key, "poster": key} for video
    variants = models.JSONField(default=dict, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    duration_s = models.FloatField(null=True, blank=True)
    dominant_color = models.CharField(max_length=7, blank=True, help_text="#rrggbb placeholder while loading")
    # Development seed only: remote image used instead of stored variants.
    external_url = models.URLField(blank=True)

    def __str__(self):
        return f"{self.kind}:{self.storage_key}"


class Space(BaseModel):
    """A physical venue. Owned by a user (provider today, space host in Phase 4)."""

    class OwnerRole(models.TextChoices):
        PROVIDER = "provider"
        SPACE_HOST = "space_host"

    class Verification(models.TextChoices):
        UNVERIFIED = "unverified"
        VERIFIED = "verified"
        REJECTED = "rejected"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="spaces")
    owner_role = models.CharField(max_length=12, choices=OwnerRole.choices, default=OwnerRole.PROVIDER)
    name = models.CharField(max_length=120)
    about = models.TextField(blank=True, max_length=2000)
    address_line = EncryptedTextField(help_text="Exact address. Revealed only after booking.")
    address_reference = EncryptedTextField(null=True, blank=True, help_text="Floor, door, how to get in")
    neighborhood = models.CharField(max_length=120)
    city = models.CharField(max_length=80, default="Ciudad de México")
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL, related_name="spaces")
    point_exact = gis.PointField(geography=True, srid=4326)
    point_public = gis.PointField(geography=True, srid=4326)
    verification_status = models.CharField(
        max_length=12, choices=Verification.choices, default=Verification.UNVERIFIED
    )
    is_rentable = models.BooleanField(default=False, help_text="Phase 4: listed for rent to providers")
    media = models.ManyToManyField(MediaAsset, through="SpaceMedia", related_name="+", blank=True)

    def __str__(self):
        return f"{self.name} ({self.neighborhood})"


class SpaceMedia(models.Model):
    space = models.ForeignKey(Space, on_delete=models.CASCADE)
    media = models.ForeignKey(MediaAsset, on_delete=models.CASCADE)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["space", "media"], name="uniq_space_media")]


class CancellationPolicy(models.Model):
    """A named set of refund rules. New tiers are new rows: no schema change."""

    code = models.SlugField(unique=True)
    name_es = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80)
    description_es = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "cancellation policies"
        constraints = [
            models.UniqueConstraint(fields=["is_default"], condition=models.Q(is_default=True), name="one_default_policy")
        ]

    def __str__(self):
        return self.name_es

    @property
    def name(self) -> str:
        return self.name_en if (get_language() or "es").startswith("en") else self.name_es


class CancellationRule(models.Model):
    class AppliesTo(models.TextChoices):
        LEARNER_CANCEL = "learner_cancel"
        NO_SHOW = "no_show"

    policy = models.ForeignKey(CancellationPolicy, on_delete=models.CASCADE, related_name="rules")
    applies_to = models.CharField(max_length=16, choices=AppliesTo.choices, default=AppliesTo.LEARNER_CANCEL)
    min_hours_before = models.PositiveIntegerField(default=0, help_text="Inclusive")
    max_hours_before = models.PositiveIntegerField(null=True, blank=True, help_text="Exclusive. Empty = no upper bound")
    listed_refund_pct = models.PositiveSmallIntegerField(help_text="0-100, applied to the listed price")
    refund_fee = models.BooleanField(default=False, help_text="Also refund the service fee")

    class Meta:
        ordering = ["policy", "applies_to", "-min_hours_before"]
        constraints = [
            models.CheckConstraint(condition=models.Q(listed_refund_pct__lte=100), name="refund_pct_lte_100"),
            models.CheckConstraint(
                condition=models.Q(max_hours_before__isnull=True) | models.Q(max_hours_before__gt=models.F("min_hours_before")),
                name="rule_window_valid",
            ),
        ]

    def __str__(self):
        upper = "∞" if self.max_hours_before is None else f"{self.max_hours_before}h"
        return f"{self.policy.code}/{self.applies_to}: [{self.min_hours_before}h, {upper}) → {self.listed_refund_pct}%"


class Experience(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft"
        IN_REVIEW = "in_review"
        CHANGES_REQUESTED = "changes_requested"
        LIVE = "live"
        PAUSED = "paused"
        EXPIRED = "expired"
        REJECTED = "rejected"

    class Modality(models.TextChoices):
        IN_PERSON = "in_person"
        ONLINE = "online"

    class OfferingType(models.TextChoices):
        SINGLE = "single"
        COURSE = "course"
        DROPIN = "dropin"

    provider = models.ForeignKey(
        "accounts.ProviderProfile", on_delete=models.PROTECT, related_name="experiences"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    title = models.CharField(max_length=90, blank=True)
    what_you_learn = models.TextField(max_length=3000, blank=True)
    who_its_for = models.TextField(max_length=1500, blank=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT, related_name="experiences")
    instruction_language = models.CharField(max_length=5, default="es")
    modality = models.CharField(max_length=10, choices=Modality.choices, default=Modality.IN_PERSON)
    offering_type = models.CharField(max_length=10, choices=OfferingType.choices, default=OfferingType.SINGLE)
    listed_price_cents = models.PositiveBigIntegerField(default=0, help_text="Per seat. Whole course if course.")
    default_capacity = models.PositiveIntegerField(default=10)
    space = models.ForeignKey(Space, null=True, blank=True, on_delete=models.PROTECT, related_name="experiences")
    online_url = EncryptedTextField(null=True, blank=True)
    cancellation_policy = models.ForeignKey(CancellationPolicy, null=True, blank=True, on_delete=models.PROTECT)
    publish_until = models.DateTimeField(null=True, blank=True, help_text="Empty = indefinite")
    requires_approval_below = models.DecimalField(
        max_digits=3, decimal_places=2, null=True, blank=True,
        help_text="Learners with a conduct score below this need provider approval",
    )
    media = models.ManyToManyField(MediaAsset, through="ExperienceMedia", related_name="+", blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    # Denormalized for the feed (refreshed by catalog.services.refresh_denorm).
    point_public = gis.PointField(geography=True, srid=4326, null=True, blank=True)
    next_session_at = models.DateTimeField(null=True, blank=True)
    next_session_seats_left = models.PositiveIntegerField(null=True, blank=True)
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    rating_count = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            # point_public gets a GiST index automatically (spatial_index=True).
            models.Index(fields=["status", "next_session_at"], name="exp_status_next",
                         condition=models.Q(status="live")),
            models.Index(fields=["category", "status"], name="exp_category_status"),
            GinIndex(OpClass(Upper("title"), name="gin_trgm_ops"), name="exp_title_trgm"),
        ]

    def __str__(self):
        return self.title or f"Draft {self.pk}"

    @property
    def is_editable_in_place(self) -> bool:
        return self.status in {self.Status.DRAFT, self.Status.CHANGES_REQUESTED, self.Status.REJECTED}


class ExperienceMedia(models.Model):
    experience = models.ForeignKey(Experience, on_delete=models.CASCADE)
    media = models.ForeignKey(MediaAsset, on_delete=models.CASCADE)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position"]
        constraints = [models.UniqueConstraint(fields=["experience", "media"], name="uniq_experience_media")]


class ExperienceRevision(BaseModel):
    """A snapshot submitted for admin review.

    - First publication: snapshot of the draft; experience.status is in_review.
    - Edit of a live experience: material changes accumulate here (status draft) while the
      live version keeps selling; on approval the payload is applied.
    """

    class ReviewStatus(models.TextChoices):
        DRAFT = "draft"
        PENDING = "pending"
        APPROVED = "approved"
        CHANGES_REQUESTED = "changes_requested"
        REJECTED = "rejected"
        SUPERSEDED = "superseded"

    class Kind(models.TextChoices):
        INITIAL = "initial"
        EDIT = "edit"

    experience = models.ForeignKey(Experience, on_delete=models.CASCADE, related_name="revisions")
    number = models.PositiveIntegerField()
    kind = models.CharField(max_length=10, choices=Kind.choices)
    payload = models.JSONField(default=dict)
    review_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reason_code = models.CharField(max_length=40, blank=True)
    reviewer_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(fields=["experience", "number"], name="uniq_revision_number"),
            models.UniqueConstraint(
                fields=["experience"],
                condition=models.Q(review_status__in=["draft", "pending"]),
                name="one_open_revision",
            ),
        ]

    def __str__(self):
        return f"{self.experience} r{self.number} ({self.review_status})"


class Cohort(BaseModel):
    """A run of a multi-session course. Booked as one unit; takes a seat in every session."""

    experience = models.ForeignKey(Experience, on_delete=models.CASCADE, related_name="cohorts")
    label = models.CharField(max_length=80, blank=True)
    capacity = models.PositiveIntegerField()
    seats_booked = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(seats_booked__lte=models.F("capacity")), name="cohort_not_overbooked")]

    def __str__(self):
        return self.label or f"Cohort {self.pk}"


class Session(BaseModel):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled"
        CANCELLED = "cancelled"
        COMPLETED = "completed"

    experience = models.ForeignKey(Experience, on_delete=models.CASCADE, related_name="sessions")
    cohort = models.ForeignKey(Cohort, null=True, blank=True, on_delete=models.CASCADE, related_name="sessions")
    space = models.ForeignKey(Space, null=True, blank=True, on_delete=models.PROTECT, related_name="sessions")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    # Local (America/Mexico_City) copies used by the day/time filter. Set in save().
    local_dow = models.PositiveSmallIntegerField(help_text="ISO weekday, 1=Monday")
    local_start_time = models.TimeField()
    local_end_time = models.TimeField()
    capacity = models.PositiveIntegerField()
    seats_booked = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["experience", "starts_at"], name="session_exp_start"),
            models.Index(fields=["local_dow", "local_start_time"], name="session_dow_time"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="session_ends_after_start"),
            models.CheckConstraint(condition=models.Q(seats_booked__lte=models.F("capacity")), name="session_not_overbooked"),
        ]

    def __str__(self):
        return f"{self.experience} @ {timezone.localtime(self.starts_at):%Y-%m-%d %H:%M}"

    def fill_local_fields(self):
        start = timezone.localtime(self.starts_at, timezone.get_default_timezone())
        end = timezone.localtime(self.ends_at, timezone.get_default_timezone())
        self.local_dow = start.isoweekday()
        self.local_start_time = start.time().replace(microsecond=0)
        same_day = end.date() == start.date()
        self.local_end_time = end.time().replace(microsecond=0) if same_day else time(23, 59, 59)

    def save(self, *args, **kwargs):
        self.fill_local_fields()
        super().save(*args, **kwargs)

    @property
    def seats_left(self) -> int:
        return max(self.capacity - self.seats_booked, 0)
