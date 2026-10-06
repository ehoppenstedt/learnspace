from datetime import date, timedelta

import pytest
from django.db import ProgrammingError, connection
from django.utils import timezone

from apps.accounts.models import ProviderProfile, ProviderVerification
from apps.catalog import services
from apps.catalog.models import Category, Experience, ExperienceRevision
from apps.core.exceptions import DomainError
from apps.moderation import services as moderation
from apps.moderation.models import AdminAction
from conftest import auth, make_user, ready_image

pytestmark = pytest.mark.django_db


@pytest.fixture
def new_provider(api, learner):
    auth(api, learner)
    res = api.post("/api/v1/provider/activate")
    assert res.status_code == 201
    return learner


def _future(days=7, hour=18):
    day = timezone.localdate() + timedelta(days=days)
    start = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()).replace(hour=hour))
    return start, start + timedelta(hours=2)


def _create_draft(api, user):
    space = api.post("/api/v1/provider/spaces", {
        "name": "Estudio Luz", "about": "Luz natural", "address_line": "Colima 123, int 4",
        "lat": 19.4194, "lng": -99.1617,
    }).data
    media = [str(ready_image(user).pk) for _ in range(3)]
    res = api.post("/api/v1/provider/experiences", {
        "title": "Cerámica en torno", "what_you_learn": "Centrado, levantado de paredes y acabado de piezas en torno eléctrico.",
        "who_its_for": "Principiantes curiosos.", "category_id": Category.objects.get(slug="crafts").pk,
        "listed_price_cents": 65000, "space_id": space["id"], "media_ids": media,
    })
    assert res.status_code == 201, res.content
    return res.data


def test_space_gets_public_point_and_area(api, new_provider):
    res = api.post("/api/v1/provider/spaces", {"name": "S", "address_line": "Calle 1", "lat": 19.4194, "lng": -99.1617})
    assert res.status_code == 201
    assert res.data["location"]["area"] == "Roma Norte"
    assert res.data["location"]["public"] != res.data["location"]["exact"]
    assert api.post("/api/v1/provider/spaces", {"name": "S", "address_line": "x", "lat": 40.7, "lng": -74}).status_code == 400


def test_full_creation_review_and_publication(api, new_provider, admin_user, settings):
    draft = _create_draft(api, new_provider)
    assert draft["status"] == "draft"
    assert draft["price"]["total_cents"] == 71500

    # Submitting without dates fails with field errors.
    res = api.post(f"/api/v1/provider/experiences/{draft['id']}/submit")
    assert res.status_code == 400 and "sessions" in res.data["error"]["fields"]

    start, end = _future()
    res = api.post(f"/api/v1/provider/experiences/{draft['id']}/sessions",
                   {"sessions": [{"starts_at": start.isoformat(), "ends_at": end.isoformat()}], "capacity": 8}, format="json")
    assert res.status_code == 201
    res = api.post(f"/api/v1/provider/experiences/{draft['id']}/submit")
    assert res.status_code == 200 and res.data["status"] == "in_review"

    # Editing while in review is blocked.
    assert api.patch(f"/api/v1/provider/experiences/{draft['id']}", {"title": "Otra cosa distinta"}).status_code == 409

    revision = ExperienceRevision.objects.get(experience_id=draft["id"], review_status="pending")
    # Unverified provider: approval blocked.
    with pytest.raises(DomainError) as exc:
        moderation.approve(admin_user, revision)
    assert exc.value.code == "provider_not_verified"

    # Provider uploads ID; admin approves it.
    doc_media = ready_image(new_provider)
    doc_media.kind = "document"
    doc_media.save()
    res = api.post("/api/v1/provider/verification-docs", {"doc_type": "government_id", "media_id": str(doc_media.pk)})
    assert res.status_code == 201
    doc = ProviderVerification.objects.get(pk=res.data["id"])
    moderation.decide_verification(admin_user, doc, approve_doc=True)
    assert ProviderProfile.objects.get(pk=new_provider.pk).is_verified

    # Still blocked: no payout account (KYC) and no RFC yet.
    with pytest.raises(DomainError) as exc:
        moderation.approve(admin_user, revision)
    assert exc.value.code == "provider_payments_incomplete"
    assert set(exc.value.fields["missing"]) == {"payment_account", "tax_profile"}

    assert api.put("/api/v1/provider/tax-profile", {"person_type": "fisica", "rfc": "lopa900517ab1",
                                                    "legal_name": "Ana López Pérez"}).status_code == 200
    url = api.post("/api/v1/provider/payments/onboarding").data["url"]
    account_id = url.rstrip("/").split("/")[-1]
    settings.DEBUG = True
    assert api.post(f"/api/v1/dev/onboarding/{account_id}/complete").status_code == 200
    status_res = api.get("/api/v1/provider/payments/onboarding").data
    assert status_res["ready_to_publish"] is True, status_res
    assert status_res["payment_account"]["kyc_status"] == "verified"

    moderation.approve(admin_user, revision, note="Se ve muy bien")
    experience = Experience.objects.get(pk=draft["id"])
    assert experience.status == "live" and experience.published_at
    assert experience.next_session_at == start
    assert AdminAction.objects.filter(target_id=str(experience.pk), action="experience.approve").exists()

    # It is now in the public feed.
    api.force_authenticate(None)
    titles = [r["title"] for r in api.get("/api/v1/experiences", {"lat": 19.42, "lng": -99.16}).data["results"]]
    assert "Cerámica en torno" in titles


def test_live_material_edit_goes_through_review_without_unpublishing(api, provider_user, admin_user):
    from conftest import make_live_experience

    experience = make_live_experience(provider_user)
    auth(api, provider_user)
    res = api.patch(f"/api/v1/provider/experiences/{experience.pk}",
                    {"title": "Acuarela botánica intensiva", "default_capacity": 12})
    assert res.status_code == 200
    experience.refresh_from_db()
    assert experience.title == "Acuarela para principiantes"     # live copy unchanged
    assert experience.default_capacity == 12                   # non-material applied directly
    assert res.data["pending_changes"]["changed_fields"] == ["title"]
    assert res.data["status"] == "live"

    res = api.post(f"/api/v1/provider/experiences/{experience.pk}/submit")
    assert res.status_code == 200
    revision = experience.revisions.get(review_status="pending")
    assert api.patch(f"/api/v1/provider/experiences/{experience.pk}", {"title": "Otro título más"}).status_code == 409

    moderation.request_changes(admin_user, revision, "misleading", "El título promete más de lo que se enseña.")
    experience.refresh_from_db()
    assert experience.status == "live"
    # Next edit starts from the proposed payload, so the provider doesn't lose work.
    api.patch(f"/api/v1/provider/experiences/{experience.pk}", {"listed_price_cents": 55000})
    rev = experience.revisions.get(review_status="draft")
    assert rev.payload["title"] == "Acuarela botánica intensiva" and rev.payload["listed_price_cents"] == 55000
    api.post(f"/api/v1/provider/experiences/{experience.pk}/submit")
    moderation.approve(admin_user, experience.revisions.get(review_status="pending"))
    experience.refresh_from_db()
    assert (experience.title, experience.listed_price_cents) == ("Acuarela botánica intensiva", 55000)


def test_reject_initial_submission(api, new_provider, admin_user):
    draft = _create_draft(api, new_provider)
    start, end = _future()
    services.create_sessions(Experience.objects.get(pk=draft["id"]), [(start, end)])
    api.post(f"/api/v1/provider/experiences/{draft['id']}/submit")
    revision = ExperienceRevision.objects.get(experience_id=draft["id"], review_status="pending")
    with pytest.raises(DomainError):
        moderation.reject(admin_user, revision, "prohibited", "")  # note required
    moderation.reject(admin_user, revision, "prohibited", "Actividad no permitida.")
    assert Experience.objects.get(pk=draft["id"]).status == "rejected"


def test_pause_resume_and_delete_rules(api, provider_user):
    from conftest import make_live_experience

    experience = make_live_experience(provider_user)
    auth(api, provider_user)
    assert api.post(f"/api/v1/provider/experiences/{experience.pk}/pause").data["status"] == "paused"
    assert api.post(f"/api/v1/provider/experiences/{experience.pk}/resume").data["status"] == "live"
    assert api.delete(f"/api/v1/provider/experiences/{experience.pk}").status_code == 409


def test_cannot_touch_other_providers_experience(api, provider_user):
    from conftest import make_live_experience

    experience = make_live_experience(provider_user)
    other = make_user(email="otro@example.com", phone="+525533334444")
    ProviderProfile.objects.create(user=other, display_name="Otro")
    auth(api, other)
    assert api.patch(f"/api/v1/provider/experiences/{experience.pk}", {"title": "Hackeado por alguien"}).status_code == 404
    space = experience.space
    res = api.post("/api/v1/provider/experiences", {"title": "x", "space_id": str(space.pk)})
    assert res.status_code == 404


def test_media_limits_and_ownership(api, provider_user):
    auth(api, provider_user)
    stranger = make_user(email="z@example.com", phone="+525577778888")
    foreign = ready_image(stranger)
    assert api.post("/api/v1/provider/experiences", {"media_ids": [str(foreign.pk)]}, format="json").status_code == 404
    many = [str(ready_image(provider_user).pk) for _ in range(11)]
    res = api.post("/api/v1/provider/experiences", {"media_ids": many}, format="json")
    assert res.status_code == 400 and res.data["error"]["code"] == "too_many_images"


def test_online_disabled_in_phase_1(api, provider_user):
    auth(api, provider_user)
    res = api.post("/api/v1/provider/experiences", {"modality": "online"})
    assert res.status_code == 400 and res.data["error"]["code"] == "online_disabled"


class TestScheduling:
    def test_weekly_recurrence(self):
        start = date(2026, 11, 2)  # Monday
        windows = services.expand_weekly(days=[2, 4], start_time=timezone.datetime(2000, 1, 1, 19, 0).time(),
                                         duration_minutes=90, from_date=start, until_date=start + timedelta(days=27))
        assert len(windows) == 8
        local = [timezone.localtime(s) for s, _ in windows]
        assert {d.isoweekday() for d in local} == {2, 4}
        assert all(d.hour == 19 for d in local)

    def test_session_validation(self, provider_user):
        from conftest import make_live_experience

        experience = make_live_experience(provider_user)
        past = timezone.now() - timedelta(hours=1)
        with pytest.raises(DomainError):
            services.create_sessions(experience, [(past, past + timedelta(hours=1))])
        start, _ = _future()
        with pytest.raises(DomainError):
            services.create_sessions(experience, [(start, start + timedelta(hours=13))])

    def test_course_cohort(self, api, provider_user):
        auth(api, provider_user)
        from conftest import make_space

        space = make_space(provider_user)
        res = api.post("/api/v1/provider/experiences", {"offering_type": "course", "space_id": str(space.pk),
                                                         "title": "Curso de fotografía"})
        exp_id = res.data["id"]
        start = timezone.localdate() + timedelta(days=3)
        res = api.post(f"/api/v1/provider/experiences/{exp_id}/sessions", {
            "label": "Noviembre", "capacity": 6,
            "recurrence": {"days": [start.isoweekday()], "start_time": "18:00", "duration_minutes": 120,
                           "from_date": start.isoformat(), "until_date": (start + timedelta(days=21)).isoformat()},
        }, format="json")
        assert res.status_code == 201, res.content
        assert len(res.data) == 4 and len({s["cohort_id"] for s in res.data}) == 1
        experience = Experience.objects.get(pk=exp_id)
        assert experience.next_session_seats_left == 6
        # Single-session API rejected for courses.
        with pytest.raises(DomainError):
            services.create_sessions(experience, [_future()])

    def test_local_fields_for_day_time_filter(self, provider_user):
        from conftest import make_live_experience

        experience = make_live_experience(provider_user, hour=19, duration_min=90)
        session = experience.sessions.get()
        assert session.local_start_time.hour == 19 and session.local_end_time.strftime("%H:%M") == "20:30"


def test_admin_action_log_is_append_only(admin_user):
    action = AdminAction.objects.create(admin=admin_user, action="test", target_type="x", target_id="1")
    with pytest.raises(ProgrammingError, match="append-only"), connection.cursor() as cur:
        cur.execute("UPDATE moderation_adminaction SET note = 'tampered' WHERE id = %s", [action.pk])


def test_admin_action_cannot_be_deleted(admin_user):
    from django.db import transaction

    action = AdminAction.objects.create(admin=admin_user, action="test", target_type="x", target_id="1")
    with pytest.raises(ProgrammingError, match="append-only"), transaction.atomic():
        AdminAction.objects.filter(pk=action.pk).delete()
