from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Experience
from apps.core.geo import haversine_m
from conftest import make_live_experience, make_space, point

pytestmark = pytest.mark.django_db

ROMA = (19.4194, -99.1617)
COYOACAN = (19.3500, -99.1620)   # ~7.7 km south of Roma
SANTA_FE = (19.3600, -99.2600)   # ~12 km west


@pytest.fixture
def three(provider_user):
    roma = make_live_experience(provider_user, title="Acuarela en la Roma", space=make_space(provider_user, *ROMA, name="Roma"),
                                starts_in=timedelta(days=5))
    coyo = make_live_experience(provider_user, title="Guitarra en Coyoacán", category_slug="music", price_cents=30000,
                                space=make_space(provider_user, *COYOACAN, name="Coyo"), starts_in=timedelta(days=1), hour=10)
    sfe = make_live_experience(provider_user, title="Python en Santa Fe", category_slug="technology", price_cents=90000,
                               language="en", space=make_space(provider_user, *SANTA_FE, name="SF"), starts_in=timedelta(days=2))
    return roma, coyo, sfe


def _titles(res):
    return [r["title"] for r in res.data["results"]]


def test_guest_can_browse_and_results_sorted_by_distance(api, three):
    res = api.get("/api/v1/experiences", {"lat": ROMA[0], "lng": ROMA[1], "radius_km": 20})
    assert res.status_code == 200
    assert _titles(res) == ["Acuarela en la Roma", "Guitarra en Coyoacán", "Python en Santa Fe"]
    distances = [r["distance_m"] for r in res.data["results"]]
    assert distances == sorted(distances)


def test_radius_filter(api, three):
    res = api.get("/api/v1/experiences", {"lat": ROMA[0], "lng": ROMA[1], "radius_km": 10})
    assert _titles(res) == ["Acuarela en la Roma", "Guitarra en Coyoacán"]


def test_sort_soonest(api, three):
    res = api.get("/api/v1/experiences", {"lat": ROMA[0], "lng": ROMA[1], "radius_km": 20, "sort": "soonest"})
    assert _titles(res)[0] == "Guitarra en Coyoacán"


def test_manual_area_fallback(api, three):
    res = api.get("/api/v1/experiences", {"area": "coyoacan-centro", "radius_km": 3})
    assert _titles(res) == ["Guitarra en Coyoacán"]


def test_no_location_sorts_by_next_date(api, three):
    res = api.get("/api/v1/experiences")
    assert _titles(res)[0] == "Guitarra en Coyoacán"
    assert res.data["results"][0]["distance_m"] is None


def test_category_language_filters(api, three):
    base = {"lat": ROMA[0], "lng": ROMA[1], "radius_km": 30}
    assert _titles(api.get("/api/v1/experiences", {**base, "category": "music,technology"})) == [
        "Guitarra en Coyoacán", "Python en Santa Fe"]
    assert _titles(api.get("/api/v1/experiences", {**base, "language": "en"})) == ["Python en Santa Fe"]


def test_price_filter_uses_total_including_fee(api, three):
    # Coyoacán: listed 300.00 -> total 330.00 at 10%.
    base = {"lat": ROMA[0], "lng": ROMA[1], "radius_km": 30}
    assert "Guitarra en Coyoacán" in _titles(api.get("/api/v1/experiences", {**base, "price_max": 33000}))
    assert "Guitarra en Coyoacán" not in _titles(api.get("/api/v1/experiences", {**base, "price_max": 32999}))


def test_card_shows_total_price(api, three):
    res = api.get("/api/v1/experiences", {"q": "Guitarra"})
    assert res.data["results"][0]["price"] == {"listed_cents": 30000, "fee_cents": 3000, "total_cents": 33000, "currency": "MXN"}


def test_day_and_time_window_filter(api, three):
    roma, coyo, _ = three
    roma_dow = timezone.localtime(roma.next_session_at).isoweekday()
    # Roma runs 19:00-21:00: fits 18:00-22:00, not 19:00-20:30.
    res = api.get("/api/v1/experiences", {"dow": str(roma_dow), "time_from": "18:00", "time_to": "22:00"})
    assert "Acuarela en la Roma" in _titles(res)
    res = api.get("/api/v1/experiences", {"dow": str(roma_dow), "time_from": "19:00", "time_to": "20:30"})
    assert "Acuarela en la Roma" not in _titles(res)
    other_day = roma_dow % 7 + 1
    res = api.get("/api/v1/experiences", {"dow": str(other_day), "time_from": "18:00", "time_to": "22:00"})
    assert "Acuarela en la Roma" not in _titles(res)


def test_search_text(api, three):
    assert _titles(api.get("/api/v1/experiences", {"q": "python"})) == ["Python en Santa Fe"]
    assert "Guitarra en Coyoacán" in _titles(api.get("/api/v1/experiences", {"q": "música"}))


def test_hidden_states(api, three):
    roma, coyo, sfe = three
    Experience.objects.filter(pk=roma.pk).update(status="paused")
    Experience.objects.filter(pk=coyo.pk).update(publish_until=timezone.now() - timedelta(minutes=1))
    Experience.objects.filter(pk=sfe.pk).update(next_session_at=None)
    assert _titles(api.get("/api/v1/experiences")) == []


def test_full_sessions_drop_out(api, three):
    roma, *_ = three
    roma.sessions.update(seats_booked=10)
    from apps.catalog.services import refresh_denorm

    refresh_denorm(roma)
    assert "Acuarela en la Roma" not in _titles(api.get("/api/v1/experiences"))


def test_exact_address_never_exposed_publicly(api, three):
    roma, *_ = three
    exact = roma.space.point_exact
    res = api.get("/api/v1/experiences", {"lat": exact.y, "lng": exact.x})
    body = str(res.data)
    assert "Colima 123" not in body
    detail = api.get(f"/api/v1/experiences/{roma.pk}")
    assert detail.status_code == 200
    loc = detail.data["location"]
    assert loc["approximate"] is True and "address_line" not in loc
    assert haversine_m(point(loc["lat"], loc["lng"]), exact) > 140
    # Distance shown is computed from the public point, not the exact one.
    assert res.data["results"][0]["distance_m"] > 100


def test_owner_sees_exact_address(api, three, provider_user):
    roma, *_ = three
    api.force_authenticate(provider_user)
    loc = api.get(f"/api/v1/experiences/{roma.pk}").data["location"]
    assert loc["approximate"] is False
    assert loc["address_line"].startswith("Colima 123")


def test_detail_hidden_unless_live(api, three, learner):
    roma, *_ = three
    Experience.objects.filter(pk=roma.pk).update(status="draft")
    api.force_authenticate(learner)
    assert api.get(f"/api/v1/experiences/{roma.pk}").status_code == 404


def test_detail_payload(api, three):
    roma, *_ = three
    data = api.get(f"/api/v1/experiences/{roma.pk}").data
    assert data["cancellation_policy"]["code"] == "standard"
    assert len(data["cancellation_policy"]["rules"]) == 3
    assert data["provider"]["display_name"] == "Taller Luz"
    assert len(data["upcoming"]["sessions"]) == 1
    assert data["media"][0]["urls"]["w800"].endswith("/800/600")


def test_map_bbox(api, three):
    res = api.get("/api/v1/experiences/map", {"bbox": "-99.20,19.39,-99.12,19.45"})
    assert res.status_code == 200
    assert [p["title"] for p in res.data["results"]] == ["Acuarela en la Roma"]
    assert api.get("/api/v1/experiences/map", {"bbox": "-101,17,-97,21"}).status_code == 400


def test_validation_errors(api):
    assert api.get("/api/v1/experiences", {"lat": 19.4}).status_code == 400
    assert api.get("/api/v1/experiences", {"dow": "8"}).status_code == 400
    assert api.get("/api/v1/experiences", {"time_from": "20:00", "time_to": "19:00"}).status_code == 400
    assert api.get("/api/v1/experiences", {"radius_km": 500}).status_code == 400


def test_pagination(api, provider_user):
    space = make_space(provider_user)
    for i in range(23):
        make_live_experience(provider_user, title=f"Clase número {i:02d}", space=space)
    first = api.get("/api/v1/experiences")
    assert len(first.data["results"]) == 20 and first.data["next_offset"] == 20
    second = api.get("/api/v1/experiences", {"offset": 20})
    assert len(second.data["results"]) == 3 and second.data["next_offset"] is None


def test_config_and_areas(api):
    config = api.get("/api/v1/config").data
    assert config["fee_bps"] == 1000
    assert len(config["categories"]) == 15
    assert config["features"]["online_experiences"] is True
    assert api.get("/api/v1/config", HTTP_X_CLIENT_PLATFORM="ios").data["features"]["online_group_on_ios"] is True
    assert api.get("/api/v1/geo/areas", {"q": "coyoacan"}).data[0]["slug"] == "coyoacan-centro"


def test_english_category_names(api):
    res = api.get("/api/v1/config", HTTP_ACCEPT_LANGUAGE="en")
    assert any(c["name"] == "Cooking" for c in res.data["categories"])
