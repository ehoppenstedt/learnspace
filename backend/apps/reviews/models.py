from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel

STARS = [MinValueValidator(1), MaxValueValidator(5)]


class Review(BaseModel):
    """Learner -> experience. Double-blind: hidden until both sides submit or the window closes."""

    class Moderation(models.TextChoices):
        VISIBLE = "visible"
        HIDDEN = "hidden"  # removed by admin after a report

    booking = models.OneToOneField("booking.Booking", on_delete=models.CASCADE, related_name="review")
    experience = models.ForeignKey("catalog.Experience", on_delete=models.CASCADE, related_name="reviews")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_written")
    overall = models.PositiveSmallIntegerField(validators=STARS)
    learning = models.PositiveSmallIntegerField(validators=STARS)
    facilitator = models.PositiveSmallIntegerField(validators=STARS)
    facilities = models.PositiveSmallIntegerField(validators=STARS, null=True, blank=True, help_text="In-person only")
    public_text = models.TextField(max_length=2000, blank=True)
    private_feedback = models.TextField(max_length=2000, blank=True, help_text="Visible only to the provider")
    revealed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    moderation = models.CharField(max_length=8, choices=Moderation.choices, default=Moderation.VISIBLE)

    class Meta:
        indexes = [models.Index(fields=["experience", "revealed_at"])]


class ConductRating(BaseModel):
    """Provider -> learner. Same double-blind rules."""

    booking = models.OneToOneField("booking.Booking", on_delete=models.CASCADE, related_name="conduct_rating")
    learner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conduct_ratings")
    provider = models.ForeignKey("accounts.ProviderProfile", on_delete=models.CASCADE, related_name="conduct_ratings_given")
    respect = models.PositiveSmallIntegerField(validators=STARS)
    punctuality = models.PositiveSmallIntegerField(validators=STARS)
    admin_note = models.TextField(max_length=2000, blank=True, help_text="Visible only to admins")
    revealed_at = models.DateTimeField(null=True, blank=True)
    excluded = models.BooleanField(default=False, help_text="Overturned on appeal: not counted in the score")

    @property
    def score(self) -> float:
        return (self.respect + self.punctuality) / 2


class ConductAppeal(BaseModel):
    class Status(models.TextChoices):
        OPEN = "open"
        UPHELD = "upheld"  # rating stays
        OVERTURNED = "overturned"  # rating excluded from the score

    rating = models.ForeignKey(ConductRating, on_delete=models.CASCADE, related_name="appeals")
    learner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    statement = models.TextField(max_length=2000)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["rating"], condition=models.Q(status="open"), name="one_open_appeal")]
