from django.utils import timezone
from rest_framework import serializers

from apps.booking.models import Booking, BookingSession
from apps.catalog import media as media_service


class HoldCreateSerializer(serializers.Serializer):
    session_id = serializers.UUIDField(required=False)
    cohort_id = serializers.UUIDField(required=False)
    seats = serializers.IntegerField(min_value=1)


class BookingCreateSerializer(serializers.Serializer):
    hold_id = serializers.UUIDField()


class CancelSerializer(serializers.Serializer):
    quote_token = serializers.CharField()


class AttendanceItem(serializers.Serializer):
    booking_id = serializers.UUIDField()
    attendance = serializers.ChoiceField(choices=["present", "absent"])


class AttendanceSerializer(serializers.Serializer):
    marks = AttendanceItem(many=True)


def _score(profile):
    return str(profile.conduct_score) if profile and profile.conduct_score is not None else None


def _money(cents):
    return {"cents": cents, "currency": "MXN"}


CONFIRMED_LIKE = (Booking.Status.CONFIRMED, Booking.Status.COMPLETED, Booking.Status.NO_SHOW)


class BookingSerializer(serializers.ModelSerializer):
    """The learner's view of their own booking. Exact address only once confirmed."""

    experience = serializers.SerializerMethodField()
    sessions = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    provider = serializers.SerializerMethodField()
    policy = serializers.SerializerMethodField()
    refunded_cents = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    review_pending = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id", "code", "status", "seats", "starts_at", "ends_at", "experience", "sessions", "price", "location",
            "provider", "policy", "refunded_cents", "can_cancel", "approval_deadline", "confirmed_at", "review_pending",
            "created_at",
        ]

    def get_experience(self, obj):
        e = obj.experience
        cover = next((m for m in (media_service.public_media(em.media) for em in e.experiencemedia_set.select_related("media")[:1]) if m), None)
        return {"id": str(e.pk), "title": e.title, "cover": cover, "category": e.category.name if e.category else None,
                "offering_type": e.offering_type}

    def get_sessions(self, obj):
        return [
            {"id": str(bs.session_id), "starts_at": bs.session.starts_at, "ends_at": bs.session.ends_at,
             "status": bs.session.status, "attendance": bs.attendance}
            for bs in obj.booking_sessions.select_related("session").order_by("session__starts_at")
        ]

    def get_price(self, obj):
        return {"listed_cents": obj.listed_cents, "fee_cents": obj.fee_cents, "total_cents": obj.total_cents,
                "fee_bps": obj.fee_bps_snapshot, "currency": "MXN"}

    def get_location(self, obj):
        space = obj.experience.space
        if not space:
            return None
        if obj.status in CONFIRMED_LIKE:
            return {"approximate": False, "lat": space.point_exact.y, "lng": space.point_exact.x, "address_line": space.address_line,
                    "address_reference": space.address_reference, "neighborhood": space.neighborhood, "space_name": space.name}
        return {"approximate": True, "lat": space.point_public.y, "lng": space.point_public.x, "neighborhood": space.neighborhood}

    def get_provider(self, obj):
        p = obj.experience.provider
        return {"id": str(p.pk), "display_name": p.display_name}

    def get_policy(self, obj):
        return obj.policy_snapshot

    def get_refunded_cents(self, obj):
        return sum(r.total_refund_cents for p in obj.payments.all() for r in p.refunds.all())

    def get_can_cancel(self, obj):
        return obj.status in (Booking.Status.CONFIRMED, Booking.Status.PENDING_APPROVAL) and obj.starts_at > timezone.now()

    def get_review_pending(self, obj):
        return obj.status == Booking.Status.COMPLETED and bool(obj.review_window_closes_at and obj.review_window_closes_at > timezone.now())


class RosterSerializer(serializers.ModelSerializer):
    """What a provider sees about a booked learner. Accessibility needs only with consent."""

    booking_id = serializers.UUIDField(source="booking.id")
    code = serializers.CharField(source="booking.code")
    status = serializers.CharField(source="booking.status")
    seats = serializers.IntegerField(source="booking.seats")
    learner = serializers.SerializerMethodField()

    class Meta:
        model = BookingSession
        fields = ["booking_id", "code", "status", "seats", "attendance", "learner"]

    def get_learner(self, obj):
        from apps.accounts.models import ConsentRecord
        from apps.accounts.services import has_consent

        user = obj.booking.learner
        profile = getattr(user, "learner_profile", None)
        needs = None
        if profile and profile.accessibility_needs and has_consent(user, ConsentRecord.Purpose.ACCESSIBILITY):
            needs = profile.accessibility_needs
        return {"first_name": user.first_name, "last_initial": (user.last_name or " ")[0],
                "conduct_score": _score(profile),
                "conduct_count": profile.conduct_count if profile else 0,
                "fluent_languages": profile.fluent_languages if profile else [],
                "accessibility_needs": needs}


class ProviderBookingSerializer(serializers.ModelSerializer):
    learner = serializers.SerializerMethodField()
    experience_title = serializers.CharField(source="experience.title")

    class Meta:
        model = Booking
        fields = ["id", "code", "status", "seats", "starts_at", "experience_title", "listed_cents", "approval_deadline", "learner"]

    def get_learner(self, obj):
        profile = getattr(obj.learner, "learner_profile", None)
        return {"first_name": obj.learner.first_name, "conduct_score": _score(profile),
                "conduct_count": profile.conduct_count if profile else 0}
