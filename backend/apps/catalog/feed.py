"""Discovery feed and map queries (PostGIS).

Performance notes (target p95 < 300 ms):
- Radius filter uses ST_DWithin on a geography column with a GiST index (Experience.point_public).
- next_session_at / seats are denormalized on Experience, so the list never aggregates sessions.
- Day/time filter is an EXISTS on Session(local_dow, local_start_time) with its own index.
- Total price (listed + fee) is computed in SQL with the same integer formula as pricing.py.
"""

from dataclasses import dataclass, field
from datetime import time

from django.conf import settings
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.measure import D
from django.db.models import Case, Exists, OuterRef, Prefetch, Q, Value, When
from django.utils import timezone

from apps.catalog.models import Area, Experience, ExperienceMedia, Session
from apps.payments.pricing import total_cents_expression

BANDS_M = (2000, 5000, 10000)


@dataclass
class FeedFilters:
    origin: Point | None = None
    radius_km: float = settings.FEED_DEFAULT_RADIUS_KM
    q: str = ""
    categories: list[str] = field(default_factory=list)
    price_min_cents: int | None = None
    price_max_cents: int | None = None
    days: list[int] = field(default_factory=list)
    time_from: time | None = None
    time_to: time | None = None
    modality: str | None = None
    language: str | None = None
    sort: str = "distance"
    interest_category_ids: list[int] = field(default_factory=list)
    allow_online: bool = False


def resolve_origin(lat: float | None, lng: float | None, area_slug: str | None) -> Point | None:
    if lat is not None and lng is not None:
        return Point(lng, lat, srid=4326)
    if area_slug:
        area = Area.objects.filter(slug=area_slug).only("centroid").first()
        if area:
            return area.centroid
    return None


def _card_prefetch():
    return Prefetch(
        "experiencemedia_set",
        queryset=ExperienceMedia.objects.select_related("media").order_by("position"),
        to_attr="ordered_media",
    )


def base_queryset(filters: FeedFilters, fee_bps: int):
    now = timezone.now()
    qs = (
        Experience.objects.filter(status=Experience.Status.LIVE, next_session_at__gt=now)
        .filter(Q(publish_until__isnull=True) | Q(publish_until__gt=now))
        .annotate(total_cents=total_cents_expression(fee_bps))
    )
    if not filters.allow_online:
        qs = qs.filter(modality=Experience.Modality.IN_PERSON)
    if filters.modality:
        qs = qs.filter(modality=filters.modality)
    if filters.categories:
        qs = qs.filter(category__slug__in=filters.categories)
    if filters.language:
        qs = qs.filter(instruction_language=filters.language)
    if filters.price_min_cents is not None:
        qs = qs.filter(total_cents__gte=filters.price_min_cents)
    if filters.price_max_cents is not None:
        qs = qs.filter(total_cents__lte=filters.price_max_cents)
    if filters.q:
        term = filters.q.strip()[:80]
        qs = qs.filter(
            Q(title__icontains=term) | Q(category__name_es__icontains=term) | Q(category__name_en__icontains=term)
        )
    if filters.days or filters.time_from or filters.time_to:
        sessions = Session.objects.filter(
            experience=OuterRef("pk"), status=Session.Status.SCHEDULED, starts_at__gt=now
        )
        if filters.days:
            sessions = sessions.filter(local_dow__in=filters.days)
        if filters.time_from:
            sessions = sessions.filter(local_start_time__gte=filters.time_from)
        if filters.time_to:
            # The session must fit inside the learner's window: "Tuesdays 19:00-21:00".
            sessions = sessions.filter(local_end_time__lte=filters.time_to)
        qs = qs.filter(Exists(sessions))
    return qs


def feed(filters: FeedFilters, fee_bps: int, offset: int = 0, limit: int = settings.FEED_PAGE_SIZE):
    """Two stages: (1) ordered ids from the experience table only (indexes, no joins),
    (2) hydrate just the page with its joins and media. Keeps cost flat as the catalog grows."""
    qs = base_queryset(filters, fee_bps)
    if filters.origin is not None:
        within = Q(point_public__dwithin=(filters.origin, D(km=filters.radius_km)))
        if filters.allow_online and filters.modality != Experience.Modality.IN_PERSON:
            within |= Q(modality=Experience.Modality.ONLINE)
        # Sphere (not spheroid) distance: <0.5% error at city scale, ~3x cheaper.
        qs = qs.filter(within).annotate(distance=Distance("point_public", filters.origin, spheroid=False))
        order = ["distance", "next_session_at"] if filters.sort == "distance" else ["next_session_at", "distance"]
        if filters.sort == "distance" and filters.interest_category_ids:
            # Personalization without hiding anything: within the same distance band
            # (<2 km, <5 km, <10 km, farther), the learner's interests come first.
            qs = qs.annotate(
                band=Case(*[When(point_public__dwithin=(filters.origin, D(m=m)), then=Value(i)) for i, m in enumerate(BANDS_M)],
                          default=Value(len(BANDS_M))),
                not_interest=Case(When(category_id__in=filters.interest_category_ids, then=Value(0)), default=Value(1)),
            )
            order = ["band", "not_interest", "distance", "next_session_at"]
        rows = list(qs.order_by(*order, "id").values_list("id", "distance")[offset: offset + limit + 1])
    else:
        rows = [(pk, None) for pk in qs.order_by("next_session_at", "id").values_list("id", flat=True)[offset: offset + limit + 1]]
    has_more = len(rows) > limit
    rows = rows[:limit]
    hydrated = {
        e.pk: e
        for e in Experience.objects.filter(pk__in=[pk for pk, _ in rows])
        .select_related("category", "provider", "space__area")
        .prefetch_related(_card_prefetch())
    }
    page = []
    for pk, distance in rows:
        experience = hydrated[pk]
        experience.distance = distance
        page.append(experience)
    next_offset = offset + limit if has_more and offset + limit <= settings.FEED_MAX_OFFSET else None
    return page, next_offset


def map_pins(filters: FeedFilters, fee_bps: int, bbox: tuple[float, float, float, float]):
    polygon = Polygon.from_bbox(bbox)
    polygon.srid = 4326
    qs = (
        base_queryset(filters, fee_bps)
        .filter(point_public__intersects=polygon)
        .order_by("next_session_at")
        .values("id", "title", "point_public", "total_cents", "category__icon")
    )
    return list(qs[: settings.MAP_MAX_PINS])
