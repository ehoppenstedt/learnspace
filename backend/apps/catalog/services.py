"""Catalog business logic: spaces, experiences, revisions, sessions, feed denormalization."""

from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db import transaction
from django.db.models import F, Min, Q
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status

from apps.catalog.models import (
    Area,
    CancellationPolicy,
    Category,
    Cohort,
    Experience,
    ExperienceMedia,
    ExperienceRevision,
    MediaAsset,
    Session,
    Space,
)
from apps.core.exceptions import DomainError
from apps.core.geo import public_point

MAX_SESSION_HOURS = 12
MAX_SESSIONS_PER_REQUEST = 120
MAX_SCHEDULE_DAYS_AHEAD = 365

# Changing any of these on a live experience requires admin review.
MATERIAL_FIELDS = (
    "title", "what_you_learn", "who_its_for", "category_id", "instruction_language", "modality",
    "offering_type", "listed_price_cents", "space_id", "online_url", "cancellation_policy_id", "media_ids",
)
DIRECT_FIELDS = ("default_capacity", "publish_until", "requires_approval_below")


# ---------------------------------------------------------------------------
# Spaces
# ---------------------------------------------------------------------------


def nearest_area(point: Point, max_km: float = 3.0) -> Area | None:
    return (
        Area.objects.filter(centroid__dwithin=(point, D(km=max_km)))
        .annotate(d=Distance("centroid", point))
        .order_by("d")
        .first()
    )


def save_space(space: Space, *, lat: float | None = None, lng: float | None = None) -> Space:
    if lat is not None and lng is not None:
        if not (14.0 <= lat <= 33.0 and -119.0 <= lng <= -86.0):
            raise DomainError("location_out_of_bounds", _("La ubicación debe estar en México."), status.HTTP_400_BAD_REQUEST)
        space.point_exact = Point(lng, lat, srid=4326)
        space.point_public = public_point(space.point_exact, salt=str(space.pk))
        space.area = nearest_area(space.point_exact)
        if space.area and not space.neighborhood:
            space.neighborhood = space.area.name
    with transaction.atomic():
        space.save()
        for experience in space.experiences.all():
            refresh_denorm(experience)
    return space


# ---------------------------------------------------------------------------
# Experience snapshot / payload
# ---------------------------------------------------------------------------


def media_ids(experience: Experience) -> list[str]:
    return [str(mid) for mid in ExperienceMedia.objects.filter(experience=experience).order_by("position").values_list("media_id", flat=True)]


def snapshot(experience: Experience) -> dict:
    def _str(value):
        return str(value) if value is not None else None

    return {
        "title": experience.title,
        "what_you_learn": experience.what_you_learn,
        "who_its_for": experience.who_its_for,
        "category_id": experience.category_id,
        "instruction_language": experience.instruction_language,
        "modality": experience.modality,
        "offering_type": experience.offering_type,
        "listed_price_cents": experience.listed_price_cents,
        "space_id": _str(experience.space_id),
        "online_url": experience.online_url,
        "cancellation_policy_id": experience.cancellation_policy_id,
        "media_ids": media_ids(experience),
    }


def _set_media(experience: Experience, ids: list[str]) -> None:
    ExperienceMedia.objects.filter(experience=experience).delete()
    ExperienceMedia.objects.bulk_create(
        [ExperienceMedia(experience=experience, media_id=mid, position=i) for i, mid in enumerate(ids)]
    )


def apply_payload(experience: Experience, payload: dict) -> None:
    for key in MATERIAL_FIELDS:
        if key == "media_ids" or key not in payload:
            continue
        setattr(experience, key, payload[key])
    experience.save()
    if "media_ids" in payload:
        _set_media(experience, payload["media_ids"])


def validate_media_ids(user, ids: list[str]) -> list[str]:
    ids = [str(i) for i in ids]
    if len(ids) != len(set(ids)):
        raise DomainError("duplicate_media", _("Hay archivos repetidos."), status.HTTP_400_BAD_REQUEST)
    assets = {str(a.pk): a for a in MediaAsset.objects.filter(pk__in=ids, owner=user)}
    if len(assets) != len(ids):
        raise DomainError("media_not_found", _("Archivo no encontrado."), status.HTTP_404_NOT_FOUND)
    kinds = [assets[i].kind for i in ids]
    if any(k == MediaAsset.Kind.DOCUMENT for k in kinds):
        raise DomainError("invalid_media_kind", _("Tipo de archivo no permitido."), status.HTTP_400_BAD_REQUEST)
    if kinds.count(MediaAsset.Kind.IMAGE) > settings.MEDIA_MAX_IMAGES_PER_EXPERIENCE:
        raise DomainError("too_many_images", _("Máximo %(n)s fotos.") % {"n": settings.MEDIA_MAX_IMAGES_PER_EXPERIENCE}, status.HTTP_400_BAD_REQUEST)
    if kinds.count(MediaAsset.Kind.VIDEO) > settings.MEDIA_MAX_VIDEOS_PER_EXPERIENCE:
        raise DomainError("too_many_videos", _("Máximo %(n)s videos.") % {"n": settings.MEDIA_MAX_VIDEOS_PER_EXPERIENCE}, status.HTTP_400_BAD_REQUEST)
    if any(assets[i].status == MediaAsset.Status.REJECTED for i in ids):
        raise DomainError("media_rejected", _("Uno de los archivos fue rechazado."), status.HTTP_400_BAD_REQUEST)
    return ids


def _validate_refs(user, data: dict) -> None:
    if data.get("space_id"):
        if not Space.objects.filter(pk=data["space_id"], owner=user).exists():
            raise DomainError("space_not_found", _("Espacio no encontrado."), status.HTTP_404_NOT_FOUND)
    if data.get("modality") == Experience.Modality.ONLINE and not settings.FEATURE_ONLINE_EXPERIENCES:
        raise DomainError("online_disabled", _("Las experiencias en línea llegarán pronto."), status.HTTP_400_BAD_REQUEST)
    if data.get("category_id") and not Category.objects.filter(pk=data["category_id"], is_active=True).exists():
        raise DomainError("category_not_found", _("Categoría inválida."), status.HTTP_400_BAD_REQUEST)
    if data.get("cancellation_policy_id") and not CancellationPolicy.objects.filter(pk=data["cancellation_policy_id"], is_active=True).exists():
        raise DomainError("policy_not_found", _("Política inválida."), status.HTTP_400_BAD_REQUEST)


def create_experience(provider, data: dict) -> Experience:
    data = dict(data)
    ids = validate_media_ids(provider.user, data.pop("media_ids", []))
    _validate_refs(provider.user, data)
    if not data.get("cancellation_policy_id"):
        default = CancellationPolicy.objects.filter(is_default=True).first()
        data["cancellation_policy_id"] = default.pk if default else None
    with transaction.atomic():
        experience = Experience.objects.create(provider=provider, **data)
        _set_media(experience, ids)
    return experience


def update_experience(experience: Experience, user, data: dict) -> Experience:
    """Drafts change in place. Live/paused experiences keep selling; material changes go
    into an open revision that needs admin approval."""
    data = dict(data)
    if "media_ids" in data:
        data["media_ids"] = validate_media_ids(user, data["media_ids"])
    _validate_refs(user, data)
    if experience.status in (Experience.Status.IN_REVIEW,):
        raise DomainError("in_review", _("La experiencia está en revisión; espera la decisión."))
    if experience.status == Experience.Status.EXPIRED:
        raise DomainError("expired", _("La experiencia expiró. Extiende la fecha de publicación primero."))
    with transaction.atomic():
        experience = Experience.objects.select_for_update().get(pk=experience.pk)
        if experience.is_editable_in_place:
            apply_payload(experience, {k: v for k, v in data.items() if k in MATERIAL_FIELDS})
        else:
            material = {k: v for k, v in data.items() if k in MATERIAL_FIELDS}
            if material:
                revision = _open_revision(experience)
                payload = {**revision.payload, **_normalize(material)}
                revision.payload = payload
                revision.save(update_fields=["payload", "updated_at"])
        direct = {k: v for k, v in data.items() if k in DIRECT_FIELDS}
        if direct:
            for key, value in direct.items():
                setattr(experience, key, value)
            experience.save(update_fields=[*direct.keys(), "updated_at"])
    return experience


def _normalize(values: dict) -> dict:
    return {k: (str(v) if k == "space_id" and v is not None else v) for k, v in values.items()}


def _next_revision_number(experience: Experience) -> int:
    last = experience.revisions.order_by("-number").values_list("number", flat=True).first()
    return (last or 0) + 1


def _open_revision(experience: Experience) -> ExperienceRevision:
    """Returns the editable (draft) revision, creating it from the live snapshot, or from
    the last 'changes requested' payload so the provider doesn't lose their edits."""
    open_rev = experience.revisions.filter(review_status__in=["draft", "pending"]).first()
    if open_rev:
        if open_rev.review_status == ExperienceRevision.ReviewStatus.PENDING:
            raise DomainError("revision_in_review", _("Ya hay cambios en revisión; espera la decisión."))
        return open_rev
    base = snapshot(experience)
    last = experience.revisions.order_by("-number").first()
    if last and last.kind == ExperienceRevision.Kind.EDIT and last.review_status == ExperienceRevision.ReviewStatus.CHANGES_REQUESTED:
        base = {**base, **last.payload}
    return ExperienceRevision.objects.create(
        experience=experience, number=_next_revision_number(experience), kind=ExperienceRevision.Kind.EDIT, payload=base
    )


def pending_changes(experience: Experience) -> dict | None:
    rev = experience.revisions.filter(review_status__in=["draft", "pending"]).first()
    if rev is None:
        return None
    live = snapshot(experience)
    changed = {k: v for k, v in rev.payload.items() if live.get(k) != v}
    return {"revision": rev.number, "review_status": rev.review_status, "changed_fields": sorted(changed)}


def discard_open_revision(experience: Experience) -> None:
    deleted, _ = experience.revisions.filter(review_status=ExperienceRevision.ReviewStatus.DRAFT).delete()
    if not deleted:
        raise DomainError("no_draft_changes", _("No hay cambios por descartar."), status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------


def submission_errors(experience: Experience, payload: dict) -> dict:
    errors = {}
    if len((payload.get("title") or "").strip()) < 8:
        errors["title"] = _("El título debe tener al menos 8 caracteres.")
    if len((payload.get("what_you_learn") or "").strip()) < 40:
        errors["what_you_learn"] = _("Describe lo que se aprende (mínimo 40 caracteres).")
    if len((payload.get("who_its_for") or "").strip()) < 15:
        errors["who_its_for"] = _("Describe para quién es (mínimo 15 caracteres).")
    if not payload.get("category_id"):
        errors["category_id"] = _("Elige una categoría.")
    if (payload.get("listed_price_cents") or 0) < 5000:
        errors["listed_price_cents"] = _("El precio mínimo es $50 MXN.")
    if not payload.get("cancellation_policy_id"):
        errors["cancellation_policy_id"] = _("Elige una política de cancelación.")
    if payload.get("modality") == Experience.Modality.IN_PERSON and not payload.get("space_id"):
        errors["space_id"] = _("Agrega la ubicación.")
    if payload.get("modality") == Experience.Modality.ONLINE and not payload.get("online_url"):
        errors["online_url"] = _("Agrega el enlace de la sesión en línea.")
    images = MediaAsset.objects.filter(pk__in=payload.get("media_ids") or [], kind=MediaAsset.Kind.IMAGE).count()
    if images < 3:
        errors["media_ids"] = _("Agrega al menos 3 fotos. Las fotos son lo que más atrae a los alumnos.")
    if not _has_future_bookable_session(experience):
        errors["sessions"] = _("Agrega al menos una fecha futura.")
    return errors


def _has_future_bookable_session(experience: Experience) -> bool:
    return experience.sessions.filter(status=Session.Status.SCHEDULED, starts_at__gt=timezone.now()).exists()


def submit(experience: Experience) -> ExperienceRevision:
    with transaction.atomic():
        experience = Experience.objects.select_for_update().get(pk=experience.pk)
        now = timezone.now()
        if experience.is_editable_in_place:
            payload = snapshot(experience)
            errors = submission_errors(experience, payload)
            if errors:
                raise DomainError("incomplete", _("Faltan datos para enviar a revisión."), status.HTTP_400_BAD_REQUEST, fields=errors)
            experience.revisions.filter(review_status=ExperienceRevision.ReviewStatus.DRAFT).delete()
            revision = ExperienceRevision.objects.create(
                experience=experience, number=_next_revision_number(experience), kind=ExperienceRevision.Kind.INITIAL,
                payload=payload, review_status=ExperienceRevision.ReviewStatus.PENDING, submitted_at=now,
            )
            experience.status = Experience.Status.IN_REVIEW
            experience.submitted_at = now
            experience.save(update_fields=["status", "submitted_at", "updated_at"])
            return revision
        if experience.status in (Experience.Status.LIVE, Experience.Status.PAUSED):
            revision = experience.revisions.filter(review_status=ExperienceRevision.ReviewStatus.DRAFT).first()
            if revision is None:
                raise DomainError("no_changes", _("No hay cambios por enviar."), status.HTTP_400_BAD_REQUEST)
            errors = submission_errors(experience, revision.payload)
            if errors:
                raise DomainError("incomplete", _("Faltan datos para enviar a revisión."), status.HTTP_400_BAD_REQUEST, fields=errors)
            revision.review_status = ExperienceRevision.ReviewStatus.PENDING
            revision.submitted_at = now
            revision.save(update_fields=["review_status", "submitted_at", "updated_at"])
            return revision
    raise DomainError("invalid_status", _("No se puede enviar en este estado."))


def set_paused(experience: Experience, paused: bool) -> Experience:
    expected = Experience.Status.LIVE if paused else Experience.Status.PAUSED
    if experience.status != expected:
        raise DomainError("invalid_status", _("No se puede cambiar el estado ahora."))
    experience.status = Experience.Status.PAUSED if paused else Experience.Status.LIVE
    experience.save(update_fields=["status", "updated_at"])
    return experience


def expire_experiences() -> int:
    return Experience.objects.filter(
        status__in=[Experience.Status.LIVE, Experience.Status.PAUSED], publish_until__lt=timezone.now()
    ).update(status=Experience.Status.EXPIRED)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def _validate_window(starts_at: datetime, ends_at: datetime) -> None:
    now = timezone.now()
    if starts_at <= now:
        raise DomainError("session_in_past", _("La fecha debe ser futura."), status.HTTP_400_BAD_REQUEST)
    if starts_at > now + timedelta(days=MAX_SCHEDULE_DAYS_AHEAD):
        raise DomainError("session_too_far", _("Solo puedes programar hasta un año adelante."), status.HTTP_400_BAD_REQUEST)
    if ends_at <= starts_at or ends_at - starts_at > timedelta(hours=MAX_SESSION_HOURS):
        raise DomainError("invalid_duration", _("La duración debe ser entre 1 minuto y 12 horas."), status.HTTP_400_BAD_REQUEST)


def expand_weekly(*, days: list[int], start_time, duration_minutes: int, from_date, until_date) -> list[tuple[datetime, datetime]]:
    """Weekly recurrence in local time (America/Mexico_City), DST-safe via make_aware per date."""
    if until_date < from_date:
        raise DomainError("invalid_range", _("Rango de fechas inválido."), status.HTTP_400_BAD_REQUEST)
    tz = timezone.get_default_timezone()
    out, day = [], from_date
    while day <= until_date:
        if day.isoweekday() in days:
            start = timezone.make_aware(datetime.combine(day, start_time), tz)
            out.append((start, start + timedelta(minutes=duration_minutes)))
        day += timedelta(days=1)
    return out


def create_sessions(experience: Experience, windows: list[tuple[datetime, datetime]], capacity: int | None = None) -> list[Session]:
    if experience.offering_type == Experience.OfferingType.COURSE:
        raise DomainError("use_cohorts", _("Los cursos se programan por grupos (cohortes)."), status.HTTP_400_BAD_REQUEST)
    if not windows or len(windows) > MAX_SESSIONS_PER_REQUEST:
        raise DomainError("invalid_session_count", _("Número de fechas inválido."), status.HTTP_400_BAD_REQUEST)
    for start, end in windows:
        _validate_window(start, end)
    capacity = capacity or experience.default_capacity
    with transaction.atomic():
        sessions = [
            Session(experience=experience, space=experience.space, starts_at=s, ends_at=e, capacity=capacity)
            for s, e in windows
        ]
        for session in sessions:
            session.fill_local_fields()
        Session.objects.bulk_create(sessions)
        refresh_denorm(experience)
    return sessions


def create_cohort(experience: Experience, *, label: str, capacity: int | None, windows: list[tuple[datetime, datetime]]) -> Cohort:
    if experience.offering_type != Experience.OfferingType.COURSE:
        raise DomainError("not_a_course", _("Solo los cursos usan cohortes."), status.HTTP_400_BAD_REQUEST)
    if len(windows) < 2 or len(windows) > 60:
        raise DomainError("invalid_session_count", _("Un curso necesita entre 2 y 60 sesiones."), status.HTTP_400_BAD_REQUEST)
    for start, end in windows:
        _validate_window(start, end)
    capacity = capacity or experience.default_capacity
    with transaction.atomic():
        cohort = Cohort.objects.create(experience=experience, label=label, capacity=capacity)
        sessions = [
            Session(experience=experience, cohort=cohort, space=experience.space, starts_at=s, ends_at=e, capacity=capacity)
            for s, e in sorted(windows)
        ]
        for session in sessions:
            session.fill_local_fields()
        Session.objects.bulk_create(sessions)
        refresh_denorm(experience)
    return cohort


def delete_session(session: Session) -> None:
    if session.seats_booked:
        raise DomainError("session_has_bookings", _("Esta fecha tiene reservas; cancélala en su lugar."))
    experience = session.experience
    with transaction.atomic():
        if session.cohort_id:
            cohort = session.cohort
            if cohort.seats_booked:
                raise DomainError("session_has_bookings", _("Este curso tiene reservas."))
            session.delete()
            if not cohort.sessions.exists():
                cohort.delete()
        else:
            session.delete()
        refresh_denorm(experience)


# ---------------------------------------------------------------------------
# Feed denormalization
# ---------------------------------------------------------------------------


def refresh_denorm(experience: Experience) -> None:
    now = timezone.now()
    if experience.offering_type == Experience.OfferingType.COURSE:
        cohort = (
            Cohort.objects.filter(experience=experience)
            .annotate(first_start=Min("sessions__starts_at", filter=Q(sessions__status=Session.Status.SCHEDULED)))
            .filter(first_start__gt=now, seats_booked__lt=F("capacity"))
            .order_by("first_start")
            .first()
        )
        next_at = cohort.first_start if cohort else None
        seats_left = (cohort.capacity - cohort.seats_booked) if cohort else None
    else:
        session = (
            experience.sessions.filter(status=Session.Status.SCHEDULED, starts_at__gt=now, seats_booked__lt=F("capacity"))
            .order_by("starts_at")
            .first()
        )
        next_at = session.starts_at if session else None
        seats_left = session.seats_left if session else None
    point = None
    if experience.modality == Experience.Modality.IN_PERSON and experience.space_id:
        point = Space.objects.values_list("point_public", flat=True).get(pk=experience.space_id)
    Experience.objects.filter(pk=experience.pk).update(
        next_session_at=next_at, next_session_seats_left=seats_left, point_public=point
    )
    experience.next_session_at, experience.next_session_seats_left, experience.point_public = next_at, seats_left, point


def refresh_all_denorm() -> int:
    count = 0
    for experience in Experience.objects.filter(status__in=[Experience.Status.LIVE, Experience.Status.PAUSED]).iterator():
        refresh_denorm(experience)
        count += 1
    return count

