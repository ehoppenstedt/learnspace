from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from apps.catalog import media as media_service
from apps.catalog.models import (
    Area,
    CancellationPolicy,
    Category,
    Cohort,
    Experience,
    ExperienceRevision,
    MediaAsset,
    Session,
    Space,
)
from apps.catalog.services import pending_changes
from apps.payments.pricing import price, store_price

APPROX_RADIUS_M = 500


def _media_list(experience, limit=None):
    items = getattr(experience, "ordered_media", None)
    if items is None:
        items = list(experience.experiencemedia_set.select_related("media").order_by("position"))
    out = []
    for em in items:
        data = media_service.public_media(em.media)
        if data:
            out.append(data)
        if limit and len(out) >= limit:
            break
    return out


def _latlng(point):
    return {"lat": point.y, "lng": point.x} if point else None


class CategorySerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "slug", "name", "icon"]


class AreaSerializer(serializers.ModelSerializer):
    centroid = serializers.SerializerMethodField()

    class Meta:
        model = Area
        fields = ["slug", "name", "borough", "city", "centroid"]

    def get_centroid(self, obj):
        return _latlng(obj.centroid)


class PolicySerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)
    description = serializers.SerializerMethodField()
    rules = serializers.SerializerMethodField()

    class Meta:
        model = CancellationPolicy
        fields = ["id", "code", "name", "description", "rules"]

    def get_description(self, obj):
        from django.utils.translation import get_language

        return obj.description_en if (get_language() or "es").startswith("en") else obj.description_es

    def get_rules(self, obj):
        return [
            {
                "applies_to": r.applies_to,
                "min_hours_before": r.min_hours_before,
                "max_hours_before": r.max_hours_before,
                "listed_refund_pct": r.listed_refund_pct,
                "refund_fee": r.refund_fee,
            }
            for r in obj.rules.all()
        ]


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


def display_price(experience, fee_bps: int, platform: str) -> dict:
    """Per-seat price as this device will charge it: group online classes on iOS carry the App Store price."""
    data = price(experience.listed_price_cents, fee_bps).as_dict()
    if platform == "ios" and experience.modality == "online" and experience.default_capacity > 1:
        store = store_price(data["listed_cents"], data["fee_cents"])
        if store:
            data.update(total_cents=store.total_cents, store_surcharge_cents=store.surcharge_cents, app_store=True)
    return data


class ExperienceCardSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    media = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    distance_m = serializers.SerializerMethodField()
    seats_left = serializers.IntegerField(source="next_session_seats_left", read_only=True)
    area = serializers.SerializerMethodField()
    provider_name = serializers.CharField(source="provider.display_name", read_only=True)

    class Meta:
        model = Experience
        fields = [
            "id", "title", "category", "media", "price", "distance_m", "next_session_at", "seats_left",
            "rating_avg", "rating_count", "area", "modality", "offering_type", "instruction_language", "provider_name",
        ]

    def get_media(self, obj):
        return _media_list(obj, limit=5)

    def get_price(self, obj):
        return display_price(obj, self.context["fee_bps"], self.context.get("platform", ""))

    def get_distance_m(self, obj):
        distance = getattr(obj, "distance", None)
        return round(distance.m) if distance is not None else None

    def get_area(self, obj):
        space = obj.space
        if not space:
            return None
        return space.area.name if space.area else space.neighborhood


class ProviderPublicSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="user_id")
    display_name = serializers.CharField()
    kind = serializers.CharField()
    about_me = serializers.CharField()
    about_school = serializers.CharField()
    is_verified = serializers.BooleanField()
    rating_avg = serializers.DecimalField(max_digits=3, decimal_places=2)
    rating_count = serializers.IntegerField()
    avatar = serializers.SerializerMethodField()
    member_since = serializers.DateTimeField(source="created_at")

    def get_avatar(self, obj):
        return media_service.public_media(obj.avatar) if obj.avatar else None


class SpacePublicSerializer(serializers.ModelSerializer):
    area = serializers.SerializerMethodField()
    approximate_location = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()

    class Meta:
        model = Space
        fields = ["id", "name", "about", "neighborhood", "city", "area", "approximate_location", "media"]

    def get_area(self, obj):
        return obj.area.name if obj.area else obj.neighborhood

    def get_approximate_location(self, obj):
        return {**_latlng(obj.point_public), "radius_m": APPROX_RADIUS_M}

    def get_media(self, obj):
        return [m for m in (media_service.public_media(sm.media) for sm in obj.spacemedia_set.select_related("media")) if m]


class SessionPublicSerializer(serializers.ModelSerializer):
    seats_left = serializers.IntegerField(read_only=True)

    class Meta:
        model = Session
        fields = ["id", "starts_at", "ends_at", "seats_left", "cohort_id"]


class CohortPublicSerializer(serializers.ModelSerializer):
    sessions = serializers.SerializerMethodField()
    seats_left = serializers.SerializerMethodField()

    class Meta:
        model = Cohort
        fields = ["id", "label", "seats_left", "sessions"]

    def get_sessions(self, obj):
        return [{"starts_at": s.starts_at, "ends_at": s.ends_at} for s in obj.sessions.filter(status=Session.Status.SCHEDULED)]

    def get_seats_left(self, obj):
        return max(obj.capacity - obj.seats_booked, 0)


class ExperienceDetailSerializer(ExperienceCardSerializer):
    provider = serializers.SerializerMethodField()
    space = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    cancellation_policy = PolicySerializer(read_only=True)
    upcoming = serializers.SerializerMethodField()

    class Meta(ExperienceCardSerializer.Meta):
        fields = ExperienceCardSerializer.Meta.fields + [
            "what_you_learn", "who_its_for", "provider", "space", "location", "cancellation_policy", "upcoming",
        ]

    def get_media(self, obj):
        return _media_list(obj)

    def get_provider(self, obj):
        return ProviderPublicSerializer(obj.provider).data

    def get_space(self, obj):
        return SpacePublicSerializer(obj.space).data if obj.space else None

    def get_location(self, obj):
        if obj.modality == Experience.Modality.ONLINE:
            url = obj.online_url if self.context.get("reveal_exact") else None
            return {"online": True, "approximate": url is None, "url": url}
        if not obj.space:
            return None
        if self.context.get("reveal_exact"):
            return {"approximate": False, **_latlng(obj.space.point_exact), "address_line": obj.space.address_line,
                    "address_reference": obj.space.address_reference}
        return {"approximate": True, **_latlng(obj.space.point_public), "radius_m": APPROX_RADIUS_M}

    def get_upcoming(self, obj):
        now = timezone.now()
        if obj.offering_type == Experience.OfferingType.COURSE:
            cohorts = [
                c for c in obj.cohorts.prefetch_related("sessions").all()
                if (first := c.sessions.filter(status=Session.Status.SCHEDULED).order_by("starts_at").first()) and first.starts_at > now
            ]
            return {"cohorts": CohortPublicSerializer(cohorts[:6], many=True).data}
        sessions = obj.sessions.filter(status=Session.Status.SCHEDULED, starts_at__gt=now).order_by("starts_at")[:12]
        return {"sessions": SessionPublicSerializer(sessions, many=True).data}


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class SpaceWriteSerializer(serializers.ModelSerializer):
    lat = serializers.FloatField(write_only=True, required=False)
    lng = serializers.FloatField(write_only=True, required=False)
    location = serializers.SerializerMethodField()
    address_line = serializers.CharField(max_length=300)
    address_reference = serializers.CharField(max_length=300, required=False, allow_blank=True, allow_null=True)
    media_ids = serializers.ListField(child=serializers.UUIDField(), required=False, write_only=True, max_length=10)
    media = serializers.SerializerMethodField()

    class Meta:
        model = Space
        fields = ["id", "name", "about", "address_line", "address_reference", "neighborhood", "city",
                  "lat", "lng", "location", "verification_status", "media_ids", "media"]
        read_only_fields = ["id", "verification_status"]
        extra_kwargs = {"neighborhood": {"required": False, "allow_blank": True}}

    def validate(self, attrs):
        if self.instance is None and ("lat" not in attrs or "lng" not in attrs):
            raise serializers.ValidationError({"lat": "Pin the location on the map."})
        return attrs

    def get_location(self, obj):
        return {"exact": _latlng(obj.point_exact), "public": _latlng(obj.point_public),
                "area": obj.area.name if obj.area else None}

    def get_media(self, obj):
        return [m for m in (media_service.public_media(sm.media) for sm in obj.spacemedia_set.select_related("media")) if m]


class ExperienceWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=90, required=False, allow_blank=True)
    what_you_learn = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    who_its_for = serializers.CharField(max_length=1500, required=False, allow_blank=True)
    category_id = serializers.IntegerField(required=False, allow_null=True)
    instruction_language = serializers.ChoiceField(choices=["es", "en"], required=False)
    modality = serializers.ChoiceField(choices=Experience.Modality.choices, required=False)
    offering_type = serializers.ChoiceField(choices=Experience.OfferingType.choices, required=False)
    listed_price_cents = serializers.IntegerField(min_value=0, max_value=10_000_000, required=False)
    default_capacity = serializers.IntegerField(min_value=1, max_value=500, required=False)
    space_id = serializers.UUIDField(required=False, allow_null=True)
    online_url = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    cancellation_policy_id = serializers.IntegerField(required=False, allow_null=True)
    publish_until = serializers.DateTimeField(required=False, allow_null=True)
    requires_approval_below = serializers.DecimalField(max_digits=3, decimal_places=2, min_value=1, max_value=5,
                                                       required=False, allow_null=True)
    media_ids = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=13)

    def validate_publish_until(self, value):
        if value and value <= timezone.now():
            raise serializers.ValidationError("Must be in the future.")
        return value

    def validate(self, attrs):
        if "media_ids" in attrs:
            attrs["media_ids"] = [str(m) for m in attrs["media_ids"]]
        if attrs.get("space_id") is not None:
            attrs["space_id"] = str(attrs["space_id"])
        return attrs

    def validate_offering_type(self, value):
        experience = self.context.get("experience")
        if experience and experience.offering_type != value and experience.sessions.exists():
            raise serializers.ValidationError("Delete existing dates before changing the offering type.")
        return value


class RevisionSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExperienceRevision
        fields = ["number", "kind", "review_status", "reason_code", "reviewer_note", "submitted_at", "decided_at"]


class ProviderExperienceSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    media = serializers.SerializerMethodField()
    media_ids = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    pending_changes = serializers.SerializerMethodField()
    last_decision = serializers.SerializerMethodField()
    sessions_upcoming = serializers.SerializerMethodField()

    class Meta:
        model = Experience
        fields = [
            "id", "status", "title", "what_you_learn", "who_its_for", "category", "category_id",
            "instruction_language", "modality", "offering_type", "listed_price_cents", "price", "default_capacity",
            "space_id", "online_url", "cancellation_policy_id", "publish_until", "requires_approval_below",
            "media", "media_ids", "next_session_at", "pending_changes", "last_decision", "sessions_upcoming",
            "created_at", "updated_at",
        ]

    def get_media(self, obj):
        out = []
        for em in obj.experiencemedia_set.select_related("media").order_by("position"):
            data = media_service.public_media(em.media) or {"id": str(em.media_id), "kind": em.media.kind,
                                                           "status": em.media.status}
            out.append(data)
        return out

    def get_media_ids(self, obj):
        return [str(m) for m in obj.experiencemedia_set.order_by("position").values_list("media_id", flat=True)]

    def get_price(self, obj):
        data = price(obj.listed_price_cents, self.context["fee_bps"]).as_dict()
        if obj.modality == "online" and obj.default_capacity > 1:  # what iPhone learners will pay (wizard preview)
            store = store_price(data["listed_cents"], data["fee_cents"])
            data["ios_total_cents"] = store.total_cents if store else None
        return data

    def get_pending_changes(self, obj):
        return pending_changes(obj)

    def get_last_decision(self, obj):
        rev = obj.revisions.filter(decided_at__isnull=False).order_by("-decided_at").first()
        return RevisionSummarySerializer(rev).data if rev else None

    def get_sessions_upcoming(self, obj):
        return obj.sessions.filter(status=Session.Status.SCHEDULED, starts_at__gt=timezone.now()).count()


class SessionSerializer(serializers.ModelSerializer):
    seats_left = serializers.IntegerField(read_only=True)

    class Meta:
        model = Session
        fields = ["id", "cohort_id", "starts_at", "ends_at", "capacity", "seats_booked", "seats_left", "status"]
        read_only_fields = ["id", "cohort_id", "starts_at", "ends_at", "seats_booked", "status"]


class WindowSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()


class RecurrenceSerializer(serializers.Serializer):
    days = serializers.ListField(child=serializers.IntegerField(min_value=1, max_value=7), min_length=1, max_length=7)
    start_time = serializers.TimeField()
    duration_minutes = serializers.IntegerField(min_value=15, max_value=720)
    from_date = serializers.DateField()
    until_date = serializers.DateField()


class ScheduleSerializer(serializers.Serializer):
    """Either explicit windows or a weekly recurrence."""

    sessions = WindowSerializer(many=True, required=False)
    recurrence = RecurrenceSerializer(required=False)
    capacity = serializers.IntegerField(min_value=1, max_value=500, required=False)
    label = serializers.CharField(max_length=80, required=False, allow_blank=True)

    def validate(self, attrs):
        if bool(attrs.get("sessions")) == bool(attrs.get("recurrence")):
            raise serializers.ValidationError("Provide either 'sessions' or 'recurrence'.")
        return attrs


class MediaUploadSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=MediaAsset.Kind.choices)
    content_type = serializers.CharField(max_length=100)
    bytes = serializers.IntegerField(min_value=1)


class MediaStatusSerializer(serializers.ModelSerializer):
    preview = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = ["id", "kind", "status", "rejection_reason", "preview"]

    def get_preview(self, obj):
        return media_service.public_media(obj) if obj.kind != MediaAsset.Kind.DOCUMENT else None


class FeedQuerySerializer(serializers.Serializer):
    lat = serializers.FloatField(required=False, min_value=-90, max_value=90)
    lng = serializers.FloatField(required=False, min_value=-180, max_value=180)
    area = serializers.SlugField(required=False)
    radius_km = serializers.FloatField(required=False, min_value=0.5, max_value=settings.FEED_MAX_RADIUS_KM,
                                       default=settings.FEED_DEFAULT_RADIUS_KM)
    q = serializers.CharField(required=False, allow_blank=True, max_length=80, default="")
    category = serializers.CharField(required=False, default="", allow_blank=True)
    price_min = serializers.IntegerField(required=False, min_value=0)
    price_max = serializers.IntegerField(required=False, min_value=0)
    dow = serializers.CharField(required=False, default="", allow_blank=True)
    time_from = serializers.TimeField(required=False)
    time_to = serializers.TimeField(required=False)
    modality = serializers.ChoiceField(choices=Experience.Modality.choices, required=False)
    language = serializers.CharField(required=False, max_length=5)
    sort = serializers.ChoiceField(choices=["distance", "soonest"], default="distance")
    offset = serializers.IntegerField(required=False, min_value=0, max_value=settings.FEED_MAX_OFFSET, default=0)
    bbox = serializers.CharField(required=False)

    def validate_category(self, value):
        return [c.strip() for c in value.split(",") if c.strip()][:20]

    def validate_dow(self, value):
        try:
            days = sorted({int(d) for d in value.split(",") if d.strip()})
        except ValueError as exc:
            raise serializers.ValidationError("Use ISO weekdays 1-7, comma separated.") from exc
        if any(d < 1 or d > 7 for d in days):
            raise serializers.ValidationError("Use ISO weekdays 1-7, comma separated.")
        return days

    def validate_bbox(self, value):
        try:
            parts = tuple(float(p) for p in value.split(","))
        except ValueError as exc:
            raise serializers.ValidationError("bbox = minLng,minLat,maxLng,maxLat") from exc
        if len(parts) != 4 or parts[0] >= parts[2] or parts[1] >= parts[3]:
            raise serializers.ValidationError("bbox = minLng,minLat,maxLng,maxLat")
        if parts[2] - parts[0] > 2 or parts[3] - parts[1] > 2:
            raise serializers.ValidationError("bbox too large; zoom in.")
        return parts

    def validate(self, attrs):
        if ("lat" in attrs) != ("lng" in attrs):
            raise serializers.ValidationError("Provide both lat and lng.")
        if attrs.get("time_from") and attrs.get("time_to") and attrs["time_from"] >= attrs["time_to"]:
            raise serializers.ValidationError({"time_to": "Must be after time_from."})
        return attrs
