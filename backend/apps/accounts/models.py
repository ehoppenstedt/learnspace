from datetime import date

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from apps.core.fields import EncryptedTextField
from apps.core.ids import uuid7
from apps.core.models import BaseModel


def age_on(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def local_today() -> date:
    return timezone.localdate()  # America/Mexico_City


class UserManager(BaseUserManager):
    def create_user(self, email=None, password=None, **extra):
        email = self.normalize_email(email).lower() if email else None
        user = self.model(email=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra):
        extra.update(is_staff=True, is_superuser=True, email_verified=True)
        return self.create_user(email=email, password=password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    class Status(models.TextChoices):
        ACTIVE = "active"
        SUSPENDED = "suspended"
        DELETED = "deleted"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    email = models.EmailField(null=True, blank=True, unique=True)  # stored lowercase
    email_verified = models.BooleanField(default=False)
    phone_e164 = models.CharField(max_length=20, null=True, blank=True)
    phone_verified = models.BooleanField(default=False)
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    ui_language = models.CharField(max_length=5, default="es", choices=settings.LANGUAGES)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    deleted_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["phone_e164"], name="uniq_user_phone"),
        ]

    def __str__(self):
        return self.email or self.phone_e164 or str(self.pk)

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_adult(self) -> bool:
        return bool(self.date_of_birth) and age_on(self.date_of_birth, local_today()) >= settings.MIN_AGE_YEARS

    @property
    def profile_complete(self) -> bool:
        return bool(
            self.first_name and self.last_name and self.email and self.phone_verified and self.is_adult
        )

    @property
    def is_provider(self) -> bool:
        return hasattr(self, "provider_profile")


class LearnerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name="learner_profile")
    bio = models.TextField(blank=True, max_length=500)
    fluent_languages = ArrayField(models.CharField(max_length=5), default=list, blank=True)
    # Sensitive personal data (LFPDPPP): encrypted, collected only with express consent,
    # shared only with the provider of a confirmed booking.
    accessibility_needs = EncryptedTextField(null=True, blank=True)
    feed_filters = models.JSONField(default=dict, blank=True)
    conduct_score = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    conduct_count = models.PositiveIntegerField(default=0)
    notification_prefs = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"LearnerProfile({self.user_id})"


class ProviderProfile(models.Model):
    class Kind(models.TextChoices):
        INDIVIDUAL = "individual"
        SCHOOL = "school"
        STUDIO = "studio"

    class Verification(models.TextChoices):
        UNVERIFIED = "unverified"
        PENDING = "pending"
        VERIFIED = "verified"
        REJECTED = "rejected"

    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name="provider_profile")
    display_name = models.CharField(max_length=120)
    about_me = models.TextField(blank=True, max_length=2000)
    about_school = models.TextField(blank=True, max_length=2000)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.INDIVIDUAL)
    avatar = models.ForeignKey("catalog.MediaAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    verification_status = models.CharField(
        max_length=12, choices=Verification.choices, default=Verification.UNVERIFIED
    )
    penalty_points = models.PositiveIntegerField(default=0)
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    rating_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.display_name

    @property
    def is_verified(self) -> bool:
        return self.verification_status == self.Verification.VERIFIED


class ProviderVerification(BaseModel):
    """A document submitted by a provider for admin review (government ID, proof of address)."""

    class DocType(models.TextChoices):
        GOVERNMENT_ID = "government_id"
        PROOF_OF_ADDRESS = "proof_of_address"
        SPACE_PHOTOS = "space_photos"

    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"

    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name="verifications")
    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    media = models.ForeignKey("catalog.MediaAsset", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reason_code = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.get_doc_type_display()} — {self.provider}"


class AuthIdentity(BaseModel):
    class Provider(models.TextChoices):
        APPLE = "apple"
        GOOGLE = "google"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="identities")
    provider = models.CharField(max_length=10, choices=Provider.choices)
    subject = models.CharField(max_length=255)
    email = models.EmailField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "subject"], name="uniq_identity")]


class OTPChallenge(BaseModel):
    class Channel(models.TextChoices):
        SMS = "sms"
        EMAIL = "email"

    class Purpose(models.TextChoices):
        LOGIN = "login"
        VERIFY_PHONE = "verify_phone"

    channel = models.CharField(max_length=5, choices=Channel.choices)
    purpose = models.CharField(max_length=15, choices=Purpose.choices, default=Purpose.LOGIN)
    destination = models.CharField(max_length=254, db_index=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["destination", "created_at"])]


class ConsentRecord(BaseModel):
    class Purpose(models.TextChoices):
        PRIVACY_NOTICE = "privacy_notice"
        FLUENT_LANGUAGES = "fluent_languages"
        ACCESSIBILITY = "sensitive_accessibility"
        MARKETING = "marketing"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="consents")
    purpose = models.CharField(max_length=30, choices=Purpose.choices)
    notice_version = models.CharField(max_length=40)
    granted_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "purpose"])]


class Interest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="interests")
    category = models.ForeignKey("catalog.Category", on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "category"], name="uniq_interest")]


class AdminTOTPDevice(BaseModel):
    """Second factor for staff logins to the admin (RFC 6238 TOTP, 30 s, 6 digits)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="totp_device")
    secret = EncryptedTextField()
    confirmed = models.BooleanField(default=False)
    last_used_step = models.BigIntegerField(default=0, help_text="Prevents replaying a code within its window")
