from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class SeatHold(BaseModel):
    """Seats reserved for 10 minutes while the learner pays. Counted against inventory."""

    class Status(models.TextChoices):
        ACTIVE = "active"
        CONVERTED = "converted"
        EXPIRED = "expired"
        RELEASED = "released"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seat_holds")
    experience = models.ForeignKey("catalog.Experience", on_delete=models.CASCADE, related_name="+")
    session = models.ForeignKey("catalog.Session", null=True, blank=True, on_delete=models.CASCADE, related_name="holds")
    cohort = models.ForeignKey("catalog.Cohort", null=True, blank=True, on_delete=models.CASCADE, related_name="holds")
    seats = models.PositiveSmallIntegerField()
    expires_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    channel = models.CharField(max_length=10, default="card", help_text="card | app_store (decided by device and experience)")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(session__isnull=False, cohort__isnull=True) | models.Q(session__isnull=True, cohort__isnull=False)),
                name="hold_one_target",
            ),
        ]
        indexes = [models.Index(fields=["session", "status", "expires_at"]), models.Index(fields=["cohort", "status", "expires_at"])]

    @property
    def is_live(self) -> bool:
        return self.status == self.Status.ACTIVE and self.expires_at > timezone.now()


class Booking(BaseModel):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment"
        PENDING_APPROVAL = "pending_approval"
        CONFIRMED = "confirmed"
        DECLINED = "declined"
        PAYMENT_FAILED = "payment_failed"
        CANCELLED = "cancelled"
        COMPLETED = "completed"
        NO_SHOW = "no_show"

    code = models.CharField(max_length=10, unique=True)
    learner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings")
    experience = models.ForeignKey("catalog.Experience", on_delete=models.PROTECT, related_name="bookings")
    session = models.ForeignKey("catalog.Session", null=True, blank=True, on_delete=models.PROTECT, related_name="bookings")
    cohort = models.ForeignKey("catalog.Cohort", null=True, blank=True, on_delete=models.PROTECT, related_name="bookings")
    hold = models.OneToOneField(SeatHold, null=True, blank=True, on_delete=models.SET_NULL, related_name="booking")
    seats = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT, db_index=True)
    # Money and rules frozen at purchase time.
    listed_cents = models.PositiveBigIntegerField()
    fee_cents = models.PositiveBigIntegerField()
    total_cents = models.PositiveBigIntegerField()
    channel = models.CharField(max_length=10, default="card", help_text="card: Stripe (or credits); app_store: Apple in-app purchase")
    store_surcharge_cents = models.PositiveBigIntegerField(
        default=0, help_text="Extra charged on the App Store price to cover Apple's commission and VAT. Not refundable on learner cancellation.")
    fee_bps_snapshot = models.PositiveIntegerField()
    policy_snapshot = models.JSONField()
    starts_at = models.DateTimeField(db_index=True, help_text="First session start (copied for queries and reminders)")
    ends_at = models.DateTimeField(help_text="Last session end")
    seats_counted = models.BooleanField(default=False, help_text="True while this booking occupies inventory")
    approval_deadline = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    review_window_closes_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total_cents=models.F("listed_cents") + models.F("fee_cents") + models.F("store_surcharge_cents")),
                name="booking_total_consistent"),
        ]
        indexes = [models.Index(fields=["learner", "starts_at"])]

    def __str__(self):
        return f"{self.code} · {self.experience} · {self.status}"

    @property
    def target(self):
        return self.session or self.cohort


class BookingSession(models.Model):
    class Attendance(models.TextChoices):
        UNKNOWN = "unknown"
        PRESENT = "present"
        ABSENT = "absent"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="booking_sessions")
    session = models.ForeignKey("catalog.Session", on_delete=models.PROTECT, related_name="booking_sessions")
    attendance = models.CharField(max_length=8, choices=Attendance.choices, default=Attendance.UNKNOWN)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    marked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["booking", "session"], name="uniq_booking_session")]


class Cancellation(BaseModel):
    """Immutable record of every cancellation: who, when, which rule, how much."""

    class Actor(models.TextChoices):
        LEARNER = "learner"
        PROVIDER = "provider"
        ADMIN = "admin"
        SYSTEM = "system"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="cancellations")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor_role = models.CharField(max_length=10, choices=Actor.choices)
    cancelled_at = models.DateTimeField(default=timezone.now)
    hours_before_start = models.DecimalField(max_digits=10, decimal_places=2)
    rule_snapshot = models.JSONField(default=dict, help_text="The policy rule that produced the refund")
    listed_refund_cents = models.PositiveBigIntegerField()
    fee_refund_cents = models.PositiveBigIntegerField()
    refund_cents = models.PositiveBigIntegerField()
    reason_code = models.CharField(max_length=40, blank=True)
    note = models.TextField(blank=True)
