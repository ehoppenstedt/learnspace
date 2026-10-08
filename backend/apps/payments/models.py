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


class PaymentCustomer(BaseModel):
    """Learner's customer record at the gateway (saved cards live there, never here)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payment_customers")
    gateway = models.CharField(max_length=20)
    external_id = models.CharField(max_length=255)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "gateway"], name="uniq_customer_per_gateway")]


class PaymentAccount(BaseModel):
    """Provider's connected account (KYC + payouts) at the gateway."""

    class KYC(models.TextChoices):
        NONE = "none"
        PENDING = "pending"
        VERIFIED = "verified"
        RESTRICTED = "restricted"

    provider = models.OneToOneField("accounts.ProviderProfile", on_delete=models.PROTECT, related_name="payment_account")
    gateway = models.CharField(max_length=20)
    external_id = models.CharField(max_length=255, unique=True)
    kyc_status = models.CharField(max_length=12, choices=KYC.choices, default=KYC.PENDING)
    charges_enabled = models.BooleanField(default=False)
    payouts_enabled = models.BooleanField(default=False)
    requirements_due = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"{self.gateway}:{self.external_id} ({self.kyc_status})"


RFC_PATTERN = r"^([A-ZÑ&]{3,4})(\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])([A-Z\d]{2})([A\d])$"


class ProviderTaxProfile(models.Model):
    class PersonType(models.TextChoices):
        FISICA = "fisica", "Persona física"
        MORAL = "moral", "Persona moral"

    provider = models.OneToOneField("accounts.ProviderProfile", on_delete=models.CASCADE, primary_key=True, related_name="tax_profile")
    person_type = models.CharField(max_length=6, choices=PersonType.choices, default=PersonType.FISICA)
    rfc = models.CharField(max_length=13)
    legal_name = models.CharField(max_length=200)
    tax_regime = models.CharField(max_length=10, blank=True, help_text="SAT régimen fiscal code, e.g. 626 RESICO")
    postal_code = models.CharField(max_length=5, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True, help_text="Set by admin after checking the constancia")
    updated_at = models.DateTimeField(auto_now=True)


class WithholdingConfig(BaseModel):
    """Platform withholding for individual providers (LISR 113-A / LIVA 18-J).

    RATES MUST BE SET BY THE TAX ADVISOR. Like FeeConfig, rows are immutable; a change is a
    new row with an effective date, and each Transfer stores the rates it used.
    """

    isr_bps = models.PositiveIntegerField(default=0, help_text="ISR withheld from personas físicas, basis points")
    iva_bps = models.PositiveIntegerField(default=0, help_text="IVA withheld, basis points of the IVA-inclusive amount")
    effective_from = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-effective_from"]


class Payment(BaseModel):
    class Status(models.TextChoices):
        REQUIRES_PAYMENT = "requires_payment"
        AUTHORIZED = "authorized"  # held on the card, awaiting provider approval
        SUCCEEDED = "succeeded"
        FAILED = "failed"
        CANCELED = "canceled"
        REFUNDED = "refunded"
        PARTIALLY_REFUNDED = "partially_refunded"
        DISPUTED = "disputed"

    booking = models.ForeignKey("booking.Booking", on_delete=models.PROTECT, related_name="payments")
    gateway = models.CharField(max_length=20)
    external_id = models.CharField(max_length=255, unique=True)
    charge_id = models.CharField(max_length=255, blank=True)
    amount_cents = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="MXN")
    capture_manual = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUIRES_PAYMENT)
    method = models.CharField(max_length=30, blank=True)
    refunded_cents = models.PositiveBigIntegerField(default=0)
    failure_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(refunded_cents__lte=models.F("amount_cents")), name="refund_lte_amount")]


class Refund(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending"
        SUCCEEDED = "succeeded"
        FAILED = "failed"

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    cancellation = models.ForeignKey("booking.Cancellation", null=True, blank=True, on_delete=models.PROTECT, related_name="refunds")
    listed_refund_cents = models.PositiveBigIntegerField()
    fee_refund_cents = models.PositiveBigIntegerField()
    surcharge_refund_cents = models.PositiveBigIntegerField(default=0)
    total_refund_cents = models.PositiveBigIntegerField()
    reason = models.CharField(max_length=40)
    external_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    idempotency_key = models.CharField(max_length=80, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")


class Transfer(BaseModel):
    """Provider's share of one booking, released after the class happens."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled"
        ON_HOLD = "on_hold"  # dispute or no-show claim under review
        SENT = "sent"
        CANCELED = "canceled"  # nothing owed (full refund)
        REVERSED = "reversed"

    booking = models.OneToOneField("booking.Booking", on_delete=models.PROTECT, related_name="transfer")
    provider = models.ForeignKey("accounts.ProviderProfile", on_delete=models.PROTECT, related_name="transfers")
    gross_cents = models.BigIntegerField(default=0, help_text="Listed price kept by the provider after refunds")
    isr_withheld_cents = models.BigIntegerField(default=0)
    iva_withheld_cents = models.BigIntegerField(default=0)
    net_cents = models.BigIntegerField(default=0)
    isr_bps = models.PositiveIntegerField(default=0)
    iva_bps = models.PositiveIntegerField(default=0)
    release_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    external_id = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    reversed_cents = models.BigIntegerField(default=0)
    hold_reason = models.CharField(max_length=80, blank=True)


class WebhookEvent(BaseModel):
    gateway = models.CharField(max_length=20)
    event_id = models.CharField(max_length=255)
    type = models.CharField(max_length=80)
    payload = models.JSONField()
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["gateway", "event_id"], name="uniq_webhook_event")]


class CreditEntry(BaseModel):
    """Append-only ledger of in-app credit (MXN centavos). Balance = sum(amount_cents).

    Credits are how App Store purchases are refunded (only Apple can refund those), and they can
    pay for any booking on any device.
    """

    class Kind(models.TextChoices):
        REFUND = "refund"  # positive: a cancellation refunded as credit
        SPEND = "spend"  # negative: used at checkout
        RESTORE = "restore"  # positive: checkout abandoned/failed, credit given back
        ADJUSTMENT = "adjustment"  # admin, either sign

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="credit_entries")
    amount_cents = models.BigIntegerField()
    kind = models.CharField(max_length=12, choices=Kind.choices)
    booking = models.ForeignKey("booking.Booking", null=True, blank=True, on_delete=models.PROTECT, related_name="credit_entries")
    refund = models.OneToOneField(Refund, null=True, blank=True, on_delete=models.PROTECT, related_name="credit_entry")
    idempotency_key = models.CharField(max_length=120, unique=True)
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        indexes = [models.Index(fields=["user", "created_at"])]
