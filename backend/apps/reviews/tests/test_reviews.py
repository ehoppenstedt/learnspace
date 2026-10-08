from datetime import timedelta

import pytest
import time_machine

from apps.accounts.models import LearnerProfile
from apps.booking import services as booking_services
from apps.catalog.models import Experience
from apps.notifications.models import Notification
from apps.reviews import services
from apps.reviews.models import ConductAppeal, ConductRating, Review
from conftest import auth, book, make_live_experience, make_user

pytestmark = pytest.mark.django_db

REVIEW = {"overall": 5, "learning": 4, "facilitator": 5, "facilities": 3, "public_text": "Muy buena clase",
          "private_feedback": "El aire acondicionado no servía"}
CONDUCT = {"respect": 5, "punctuality": 3}


@pytest.fixture
def experience(provider_user):
    return make_live_experience(provider_user)


@pytest.fixture
def booking(api, jobs, learner, experience):
    return book(api, jobs, learner, experience.sessions.get())


def after(booking, **delta):
    return time_machine.travel(booking.ends_at + timedelta(**delta), tick=False)


def test_window_closed_before_class_ends(api, learner, booking):
    with time_machine.travel(booking.ends_at - timedelta(minutes=1), tick=False):
        res = auth(api, learner).post(f"/api/v1/bookings/{booking.pk}/review", REVIEW, format="json")
    assert res.status_code == 409 and res.data["error"]["code"] == "review_not_open"


def test_window_closes_after_14_days(api, learner, booking):
    with after(booking, days=14):
        res = auth(api, learner).post(f"/api/v1/bookings/{booking.pk}/review", REVIEW, format="json")
    assert res.data["error"]["code"] == "review_closed"
    with after(booking, days=13, hours=23):
        assert auth(api, learner).post(f"/api/v1/bookings/{booking.pk}/review", REVIEW, format="json").status_code == 201


def test_double_blind_reveal_when_both_submit(api, learner, provider_user, booking, experience):
    with after(booking, hours=1):
        res = auth(api, learner).post(f"/api/v1/bookings/{booking.pk}/review", REVIEW, format="json")
        assert res.status_code == 201 and res.data["revealed"] is False
        # Hidden from the public and from the provider until the provider rates too.
        assert api.get(f"/api/v1/experiences/{experience.pk}/reviews").data["results"] == []
        assert auth(api, provider_user).get("/api/v1/provider/reviews").data == []
        res = api.post(f"/api/v1/provider/bookings/{booking.pk}/conduct-rating", CONDUCT, format="json")
        assert res.status_code == 201 and res.data["revealed"] is True
        public = api.get(f"/api/v1/experiences/{experience.pk}/reviews").data
    assert public["summary"]["count"] == 1 and public["summary"]["overall"] == "5.00"
    assert public["results"][0]["text"] == "Muy buena clase"
    assert "private_feedback" not in public["results"][0]
    experience.refresh_from_db()
    assert (experience.rating_avg, experience.rating_count) == (5, 1)
    assert LearnerProfile.objects.get(user=learner).conduct_score == 4  # (5 + 3) / 2
    own = auth(api, provider_user).get("/api/v1/provider/reviews").data
    assert own[0]["private_feedback"] == "El aire acondicionado no servía"
    kinds = set(Notification.objects.values_list("kind", flat=True))
    assert {"review_received", "conduct_received"} <= kinds


def test_one_sided_review_revealed_when_window_closes(api, learner, booking, experience):
    with after(booking, hours=1):
        auth(api, learner).post(f"/api/v1/bookings/{booking.pk}/review", REVIEW, format="json")
    with after(booking, days=13):
        assert services.reveal_closed_windows() == 0
    with after(booking, days=14, minutes=1):
        assert services.reveal_closed_windows() == 1
        assert services.reveal_closed_windows() == 0
    assert Review.objects.get(booking=booking).revealed_at is not None


def test_facilities_required_in_person_and_ignored_online(api, learner, booking, experience):
    data = {k: v for k, v in REVIEW.items() if k != "facilities"}
    with after(booking, hours=1):
        res = auth(api, learner).post(f"/api/v1/bookings/{booking.pk}/review", data, format="json")
        assert res.data["error"]["code"] == "facilities_required"
        Experience.objects.filter(pk=experience.pk).update(modality="online", online_url="https://meet.example.com/x")
        res = api.post(f"/api/v1/bookings/{booking.pk}/review", REVIEW, format="json")
    assert res.status_code == 201 and res.data["facilities"] is None


def test_one_review_per_booking_and_only_own_bookings(api, learner, booking):
    stranger = make_user(email="x@example.com", phone="+525511112222")
    with after(booking, hours=1):
        assert auth(api, stranger).post(f"/api/v1/bookings/{booking.pk}/review", REVIEW, format="json").status_code == 404
        assert auth(api, learner).post(f"/api/v1/bookings/{booking.pk}/review", REVIEW, format="json").status_code == 201
        res = api.post(f"/api/v1/bookings/{booking.pk}/review", REVIEW, format="json")
    assert res.data["error"]["code"] == "already_reviewed"


def test_no_show_can_neither_review_nor_be_rated(api, learner, provider_user, booking):
    booking.status = "no_show"
    booking.save()
    with after(booking, hours=1):
        res = auth(api, learner).post(f"/api/v1/bookings/{booking.pk}/review", REVIEW, format="json")
        assert res.data["error"]["code"] == "not_reviewable"
        res = auth(api, provider_user).post(f"/api/v1/provider/bookings/{booking.pk}/conduct-rating", CONDUCT, format="json")
        assert res.data["error"]["code"] == "not_rateable"
        assert api.get("/api/v1/me/reviews/pending").data["conduct_ratings"] == []


def test_marking_absent_after_rating_stops_it_counting(api, learner, provider_user, booking):
    with after(booking, hours=1):
        auth(api, provider_user).post(f"/api/v1/provider/bookings/{booking.pk}/conduct-rating", {"respect": 1, "punctuality": 1}, format="json")
        auth(api, learner).post(f"/api/v1/bookings/{booking.pk}/review", REVIEW, format="json")  # reveals both
        assert LearnerProfile.objects.get(user=learner).conduct_score == 1
        session_id = booking.session_id
        mark = {"marks": [{"booking_id": str(booking.pk), "attendance": "absent"}]}
        assert auth(api, provider_user).post(f"/api/v1/provider/sessions/{session_id}/attendance", mark, format="json").status_code == 200
        assert ConductRating.objects.get().excluded is True
        assert LearnerProfile.objects.get(user=learner).conduct_score is None
        mark["marks"][0]["attendance"] = "present"  # correction
        api.post(f"/api/v1/provider/sessions/{session_id}/attendance", mark, format="json")
    assert LearnerProfile.objects.get(user=learner).conduct_score == 1


def test_provider_cannot_rate_other_providers_bookings(api, booking):
    other = make_user(email="otro@example.com", phone="+525533334444")
    from apps.accounts.models import ProviderProfile

    ProviderProfile.objects.create(user=other, display_name="Otro", verification_status="verified")
    with after(booking, hours=1):
        res = auth(api, other).post(f"/api/v1/provider/bookings/{booking.pk}/conduct-rating", CONDUCT, format="json")
    assert res.status_code == 404


def test_pending_lists_owed_reviews(api, learner, provider_user, booking):
    with after(booking, hours=1):
        assert len(auth(api, learner).get("/api/v1/me/reviews/pending").data["reviews"]) == 1
        assert len(auth(api, provider_user).get("/api/v1/me/reviews/pending").data["conduct_ratings"]) == 1
        auth(api, learner).post(f"/api/v1/bookings/{booking.pk}/review", REVIEW, format="json")
        assert api.get("/api/v1/me/reviews/pending").data["reviews"] == []
        detail = api.get(f"/api/v1/bookings/{booking.pk}").data
    assert detail["review_pending"] is False


def test_complete_finished_opens_window_and_prompts(booking):
    with after(booking, minutes=5):
        assert booking_services.complete_finished() == 1
    booking.refresh_from_db()
    assert booking.status == "completed"
    assert booking.review_window_closes_at == booking.ends_at + timedelta(days=14)
    assert {"review_prompt", "rate_learner_prompt"} <= set(Notification.objects.values_list("kind", flat=True))


def test_hidden_review_leaves_public_list_and_average(api, learner, provider_user, admin_user, booking, experience):
    with after(booking, hours=1):
        auth(api, learner).post(f"/api/v1/bookings/{booking.pk}/review", REVIEW, format="json")
        auth(api, provider_user).post(f"/api/v1/provider/bookings/{booking.pk}/conduct-rating", CONDUCT, format="json")
    services.set_review_visibility(admin_user, Review.objects.get(), visible=False, note="insultos")
    experience.refresh_from_db()
    assert (experience.rating_avg, experience.rating_count) == (None, 0)
    assert api.get(f"/api/v1/experiences/{experience.pk}/reviews").data["results"] == []


def _rated(api, learner, provider_user, booking, respect=1, punctuality=1):
    with after(booking, hours=1):
        auth(api, provider_user).post(f"/api/v1/provider/bookings/{booking.pk}/conduct-rating",
                                      {"respect": respect, "punctuality": punctuality}, format="json")
    with after(booking, days=15):
        services.reveal_closed_windows()
    return ConductRating.objects.get(booking=booking)


def test_conduct_appeal_overturned_excludes_rating(api, learner, provider_user, admin_user, booking):
    rating = _rated(api, learner, provider_user, booking)
    assert LearnerProfile.objects.get(user=learner).conduct_score == 1
    mine = auth(api, learner).get("/api/v1/me/conduct").data
    assert mine["score"] == "1.00" and mine["ratings"][0]["appeal"] is None
    assert api.post(f"/api/v1/me/conduct/{rating.pk}/appeal", {"statement": "corto"}).data["error"]["code"] == "statement_too_short"
    statement = "Llegué a tiempo; tengo el mensaje de confirmación de la recepción."
    assert api.post(f"/api/v1/me/conduct/{rating.pk}/appeal", {"statement": statement}).status_code == 201
    assert api.post(f"/api/v1/me/conduct/{rating.pk}/appeal", {"statement": statement}).data["error"]["code"] == "already_appealed"
    services.decide_appeal(admin_user, ConductAppeal.objects.get(), overturn=True, note="evidencia válida")
    profile = LearnerProfile.objects.get(user=learner)
    assert (profile.conduct_score, profile.conduct_count) == (None, 0)
    mine = api.get("/api/v1/me/conduct").data
    assert mine["ratings"][0]["excluded"] is True and mine["ratings"][0]["appeal"]["status"] == "overturned"
    from apps.moderation.models import AdminAction

    assert AdminAction.objects.filter(action="conduct.appeal_overturned").exists()


def test_conduct_appeal_upheld_keeps_score(api, learner, provider_user, admin_user, booking):
    rating = _rated(api, learner, provider_user, booking, respect=2, punctuality=3)
    services.appeal(learner, rating.pk, "No estoy de acuerdo con la calificación recibida.")
    services.decide_appeal(admin_user, ConductAppeal.objects.get(), overturn=False, note="sin evidencia")
    assert LearnerProfile.objects.get(user=learner).conduct_score == pytest.approx(2.5)


def test_unrevealed_rating_cannot_be_appealed(api, learner, provider_user, booking):
    with after(booking, hours=1):
        auth(api, provider_user).post(f"/api/v1/provider/bookings/{booking.pk}/conduct-rating", CONDUCT, format="json")
    rating = ConductRating.objects.get()
    res = auth(api, learner).post(f"/api/v1/me/conduct/{rating.pk}/appeal", {"statement": "x" * 30})
    assert res.status_code == 404
