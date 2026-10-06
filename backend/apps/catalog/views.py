from django.conf import settings
from django.contrib.postgres.search import TrigramSimilarity
from django.core import signing
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import ProviderProfile
from apps.catalog import feed as feed_service
from apps.catalog import media as media_service
from apps.catalog import services
from apps.catalog.models import (
    Area,
    CancellationPolicy,
    Category,
    Experience,
    MediaAsset,
    Session,
    Space,
    SpaceMedia,
)
from apps.catalog.serializers import (
    AreaSerializer,
    CategorySerializer,
    ExperienceCardSerializer,
    ExperienceDetailSerializer,
    ExperienceWriteSerializer,
    FeedQuerySerializer,
    MediaStatusSerializer,
    MediaUploadSerializer,
    PolicySerializer,
    ProviderExperienceSerializer,
    ProviderPublicSerializer,
    ScheduleSerializer,
    SessionSerializer,
    SpacePublicSerializer,
    SpaceWriteSerializer,
)
from apps.catalog.storage import LocalStorage, get_storage
from apps.core.exceptions import DomainError
from apps.core.permissions import IsProvider
from apps.payments.pricing import current_fee_bps


class PublicView(APIView):
    permission_classes = [AllowAny]


# ---------------------------------------------------------------------------
# Public discovery
# ---------------------------------------------------------------------------


class ConfigView(PublicView):
    def get(self, request):
        return Response({
            "brand": settings.BRAND_NAME,
            "currency": "MXN",
            "fee_bps": current_fee_bps(),
            "languages": [code for code, _name in settings.LANGUAGES],
            "categories": CategorySerializer(Category.objects.filter(is_active=True), many=True).data,
            "cancellation_policies": PolicySerializer(
                CancellationPolicy.objects.filter(is_active=True).prefetch_related("rules"), many=True
            ).data,
            "features": {"online_experiences": settings.FEATURE_ONLINE_EXPERIENCES},
            "feed": {"default_radius_km": settings.FEED_DEFAULT_RADIUS_KM, "max_radius_km": settings.FEED_MAX_RADIUS_KM},
            "media": {
                "max_images": settings.MEDIA_MAX_IMAGES_PER_EXPERIENCE,
                "max_videos": settings.MEDIA_MAX_VIDEOS_PER_EXPERIENCE,
                "max_image_bytes": settings.MEDIA_MAX_IMAGE_BYTES,
                "max_video_bytes": settings.MEDIA_MAX_VIDEO_BYTES,
                "max_video_seconds": settings.MEDIA_MAX_VIDEO_SECONDS,
            },
            "legal": {"entity": settings.LEGAL_ENTITY_NAME, "rfc": settings.LEGAL_RFC,
                      "privacy_notice_version": settings.PRIVACY_NOTICE_VERSION},
        })


class AreasView(PublicView):
    def get(self, request):
        q = (request.query_params.get("q") or "").strip()[:60]
        qs = Area.objects.all()
        if q:
            qs = qs.annotate(sim=TrigramSimilarity("name", q)).filter(sim__gt=0.15).order_by("-sim")
        return Response(AreaSerializer(qs[:20], many=True).data)


def _filters_from(params: dict) -> feed_service.FeedFilters:
    return feed_service.FeedFilters(
        origin=feed_service.resolve_origin(params.get("lat"), params.get("lng"), params.get("area")),
        radius_km=params["radius_km"],
        q=params["q"],
        categories=params["category"],
        price_min_cents=params.get("price_min"),
        price_max_cents=params.get("price_max"),
        days=params["dow"],
        time_from=params.get("time_from"),
        time_to=params.get("time_to"),
        modality=params.get("modality"),
        language=params.get("language"),
        sort=params["sort"],
    )


class FeedView(PublicView):
    def get(self, request):
        query = FeedQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        fee_bps = current_fee_bps()
        items, next_offset = feed_service.feed(_filters_from(params), fee_bps, offset=params["offset"])
        return Response({
            "results": ExperienceCardSerializer(items, many=True, context={"fee_bps": fee_bps}).data,
            "next_offset": next_offset,
        })


class MapView(PublicView):
    def get(self, request):
        query = FeedQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        if "bbox" not in params:
            raise DomainError("bbox_required", "bbox is required", status.HTTP_400_BAD_REQUEST)
        pins = feed_service.map_pins(_filters_from(params), current_fee_bps(), params["bbox"])
        return Response({"results": [
            {"id": p["id"], "title": p["title"], "lat": p["point_public"].y, "lng": p["point_public"].x,
             "total_cents": p["total_cents"], "icon": p["category__icon"]}
            for p in pins
        ]})


def can_see_exact_location(user, experience: Experience) -> bool:
    """Exact address is for the owner now; Phase 2 adds learners with a confirmed booking."""
    return bool(user and user.is_authenticated and experience.provider_id == user.pk)


class ExperienceDetailView(PublicView):
    def get(self, request, pk):
        experience = get_object_or_404(
            Experience.objects.select_related("category", "provider__avatar", "space__area", "cancellation_policy")
            .prefetch_related("cancellation_policy__rules"),
            pk=pk,
        )
        is_owner = request.user.is_authenticated and experience.provider_id == request.user.pk
        if experience.status not in (Experience.Status.LIVE,) and not is_owner:
            raise Http404
        context = {"fee_bps": current_fee_bps(), "reveal_exact": can_see_exact_location(request.user, experience)}
        return Response(ExperienceDetailSerializer(experience, context=context).data)


class ProviderPublicView(PublicView):
    def get(self, request, pk):
        provider = get_object_or_404(ProviderProfile.objects.select_related("avatar"), pk=pk)
        fee_bps = current_fee_bps()
        live = (
            Experience.objects.filter(provider=provider, status=Experience.Status.LIVE, next_session_at__isnull=False)
            .select_related("category", "space__area", "provider")
            .order_by("next_session_at")[:20]
        )
        return Response({
            "provider": ProviderPublicSerializer(provider).data,
            "experiences": ExperienceCardSerializer(live, many=True, context={"fee_bps": fee_bps}).data,
        })


class SpacePublicView(PublicView):
    def get(self, request, pk):
        space = get_object_or_404(Space.objects.select_related("area"), pk=pk)
        live = (
            Experience.objects.filter(status=Experience.Status.LIVE, next_session_at__isnull=False)
            .filter(sessions__space=space).distinct()
            .select_related("category", "space__area", "provider")
            .order_by("next_session_at")[:20]
        )
        if not live and not (request.user.is_authenticated and space.owner_id == request.user.pk):
            raise Http404
        return Response({
            "space": SpacePublicSerializer(space).data,
            "experiences": ExperienceCardSerializer(live, many=True, context={"fee_bps": current_fee_bps()}).data,
        })


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


class MediaUploadView(APIView):
    def post(self, request):
        data = MediaUploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        asset, upload = media_service.create_upload(
            request.user, kind=data.validated_data["kind"], content_type=data.validated_data["content_type"],
            size=data.validated_data["bytes"],
        )
        return Response({"id": asset.id, "upload": upload}, status=status.HTTP_201_CREATED)


class MediaCompleteView(APIView):
    def post(self, request, pk):
        asset = media_service.complete_upload(request.user, pk)
        return Response(MediaStatusSerializer(asset).data)


class MediaStatusView(APIView):
    def get(self, request, pk):
        asset = get_object_or_404(MediaAsset, pk=pk, owner=request.user)
        return Response(MediaStatusSerializer(asset).data)


@csrf_exempt
def local_media(request, action):
    """Development stand-in for presigned S3 URLs. Disabled when MEDIA_STORAGE=s3."""
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise Http404
    token = request.GET.get("t", "")
    try:
        if action == "put" and request.method == "PUT":
            data = LocalStorage.unsign(token, "put", settings.MEDIA_UPLOAD_URL_TTL)
            body = request.body if len(request.body) <= data["max"] else None
            if body is None:
                return HttpResponse(status=413)
            storage.write(data["k"], body, data["ct"])
            return HttpResponse(status=200)
        if action == "get" and request.method == "GET":
            data = LocalStorage.unsign(token, "get", settings.MEDIA_READ_URL_TTL)
            path = storage.local_path(data["k"])
            if not path or not path.exists():
                raise Http404
            return FileResponse(path.open("rb"))
    except signing.BadSignature:
        return HttpResponse(status=403)
    return HttpResponse(status=405)


# ---------------------------------------------------------------------------
# Provider: spaces
# ---------------------------------------------------------------------------


class ProviderView(APIView):
    permission_classes = [IsAuthenticated, IsProvider]

    def provider(self) -> ProviderProfile:
        return self.request.user.provider_profile


def _set_space_media(space: Space, user, ids) -> None:
    ids = [str(i) for i in ids]
    owned = set(str(i) for i in MediaAsset.objects.filter(pk__in=ids, owner=user, kind=MediaAsset.Kind.IMAGE).values_list("pk", flat=True))
    if owned != set(ids):
        raise DomainError("media_not_found", _("Archivo no encontrado."), status.HTTP_404_NOT_FOUND)
    SpaceMedia.objects.filter(space=space).delete()
    SpaceMedia.objects.bulk_create([SpaceMedia(space=space, media_id=mid, position=i) for i, mid in enumerate(ids)])


class ProviderSpacesView(ProviderView):
    def get(self, request):
        spaces = Space.objects.filter(owner=request.user).select_related("area").order_by("-created_at")
        return Response(SpaceWriteSerializer(spaces, many=True).data)

    def post(self, request):
        serializer = SpaceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        lat, lng, media_ids = data.pop("lat"), data.pop("lng"), data.pop("media_ids", [])
        with transaction.atomic():
            space = Space(owner=request.user, **data)
            services.save_space(space, lat=lat, lng=lng)
            _set_space_media(space, request.user, media_ids)
        return Response(SpaceWriteSerializer(space).data, status=status.HTTP_201_CREATED)


class ProviderSpaceDetailView(ProviderView):
    def get_object(self, pk):
        return get_object_or_404(Space, pk=pk, owner=self.request.user)

    def get(self, request, pk):
        return Response(SpaceWriteSerializer(self.get_object(pk)).data)

    def patch(self, request, pk):
        space = self.get_object(pk)
        serializer = SpaceWriteSerializer(space, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        lat, lng, media_ids = data.pop("lat", None), data.pop("lng", None), data.pop("media_ids", None)
        if (lat is None) != (lng is None):
            raise DomainError("invalid_location", _("Envía latitud y longitud."), status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            for key, value in data.items():
                setattr(space, key, value)
            services.save_space(space, lat=lat, lng=lng)
            if media_ids is not None:
                _set_space_media(space, request.user, media_ids)
        return Response(SpaceWriteSerializer(space).data)


# ---------------------------------------------------------------------------
# Provider: experiences
# ---------------------------------------------------------------------------


class ProviderExperiencesView(ProviderView):
    def get(self, request):
        qs = Experience.objects.filter(provider=self.provider()).select_related("category").order_by("-updated_at")
        if status_filter := request.query_params.get("status"):
            qs = qs.filter(status__in=status_filter.split(","))
        return Response(ProviderExperienceSerializer(qs, many=True, context={"fee_bps": current_fee_bps()}).data)

    def post(self, request):
        serializer = ExperienceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        experience = services.create_experience(self.provider(), serializer.validated_data)
        return Response(
            ProviderExperienceSerializer(experience, context={"fee_bps": current_fee_bps()}).data,
            status=status.HTTP_201_CREATED,
        )


class ProviderExperienceDetailView(ProviderView):
    def get_object(self, pk) -> Experience:
        return get_object_or_404(Experience, pk=pk, provider=self.provider())

    def get(self, request, pk):
        return Response(ProviderExperienceSerializer(self.get_object(pk), context={"fee_bps": current_fee_bps()}).data)

    def patch(self, request, pk):
        experience = self.get_object(pk)
        serializer = ExperienceWriteSerializer(data=request.data, partial=True, context={"experience": experience})
        serializer.is_valid(raise_exception=True)
        experience = services.update_experience(experience, request.user, serializer.validated_data)
        experience.refresh_from_db()
        services.refresh_denorm(experience)
        return Response(ProviderExperienceSerializer(experience, context={"fee_bps": current_fee_bps()}).data)

    def delete(self, request, pk):
        experience = self.get_object(pk)
        if experience.status != Experience.Status.DRAFT:
            raise DomainError("not_draft", _("Solo se pueden borrar borradores. Pausa la experiencia en su lugar."))
        experience.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProviderExperienceActionView(ProviderView):
    def post(self, request, pk, action):
        experience = get_object_or_404(Experience, pk=pk, provider=self.provider())
        if action == "submit":
            services.submit(experience)
        elif action == "pause":
            services.set_paused(experience, True)
        elif action == "resume":
            services.set_paused(experience, False)
        elif action == "discard-changes":
            services.discard_open_revision(experience)
        else:
            raise Http404
        experience.refresh_from_db()
        return Response(ProviderExperienceSerializer(experience, context={"fee_bps": current_fee_bps()}).data)


def _windows(data) -> list:
    if data.get("recurrence"):
        return services.expand_weekly(**data["recurrence"])
    return [(w["starts_at"], w["ends_at"]) for w in data["sessions"]]


class ProviderSessionsView(ProviderView):
    def get(self, request, pk):
        experience = get_object_or_404(Experience, pk=pk, provider=self.provider())
        sessions = experience.sessions.order_by("starts_at")
        if request.query_params.get("scope") != "all":
            sessions = sessions.filter(starts_at__gt=timezone.now())
        return Response(SessionSerializer(sessions, many=True).data)

    def post(self, request, pk):
        experience = get_object_or_404(Experience, pk=pk, provider=self.provider())
        serializer = ScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        windows = _windows(data)
        if experience.offering_type == Experience.OfferingType.COURSE:
            cohort = services.create_cohort(experience, label=data.get("label", ""), capacity=data.get("capacity"), windows=windows)
            created = cohort.sessions.all()
        else:
            created = services.create_sessions(experience, windows, capacity=data.get("capacity"))
        return Response(SessionSerializer(created, many=True).data, status=status.HTTP_201_CREATED)


class ProviderSessionDetailView(ProviderView):
    def get_object(self, pk) -> Session:
        return get_object_or_404(Session.objects.select_related("experience", "cohort"), pk=pk, experience__provider=self.provider())

    def patch(self, request, pk):
        session = self.get_object(pk)
        capacity = request.data.get("capacity")
        if not isinstance(capacity, int) or capacity < max(session.seats_booked, 1) or capacity > 500:
            raise DomainError("invalid_capacity", _("Capacidad inválida."), status.HTTP_400_BAD_REQUEST)
        session.capacity = capacity
        session.save(update_fields=["capacity", "updated_at"])
        services.refresh_denorm(session.experience)
        return Response(SessionSerializer(session).data)

    def delete(self, request, pk):
        services.delete_session(self.get_object(pk))
        return Response(status=status.HTTP_204_NO_CONTENT)
