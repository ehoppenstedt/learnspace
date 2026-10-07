import pytest

from conftest import auth

pytestmark = pytest.mark.django_db


@pytest.fixture
def provider(api, learner):
    auth(api, learner)
    api.post("/api/v1/provider/activate")
    return learner


@pytest.mark.parametrize(("person_type", "rfc", "ok"), [
    ("fisica", "LOPA900517AB1", True),
    ("fisica", "lopa900517ab1", True),     # normalized to upper case
    ("fisica", "LOPA901317AB1", False),    # month 13
    ("fisica", "LOP900517AB1", False),     # 12 chars is a company RFC
    ("moral", "ABC900517AB1", True),
    ("moral", "XAXX010101000", False),     # 13 chars for a company
])
def test_rfc_validation(api, provider, person_type, rfc, ok):
    res = api.put("/api/v1/provider/tax-profile", {"person_type": person_type, "rfc": rfc, "legal_name": "Nombre"})
    assert (res.status_code == 200) is ok, res.content
    if ok:
        assert res.data["rfc"] == rfc.upper()


def test_onboarding_status_lists_whats_missing(api, provider):
    status = api.get("/api/v1/provider/payments/onboarding").data
    assert status["ready_to_publish"] is False
    assert set(status["missing"]) == {"identity", "payment_account", "tax_profile"}


def test_earnings_endpoint(api, provider_user):
    api.force_authenticate(provider_user)
    data = api.get("/api/v1/provider/earnings").data
    assert data["totals"] == {"upcoming_cents": 0, "on_hold_cents": 0, "paid_cents": 0}


def test_payment_methods(api, jobs, learner, provider_user):
    from conftest import book, make_live_experience

    api.force_authenticate(learner)
    assert api.get("/api/v1/me/payment-methods").data == []
    book(api, jobs, learner, make_live_experience(provider_user).sessions.get())
    methods = api.get("/api/v1/me/payment-methods").data
    assert methods[0]["last4"] == "4242"
    assert api.delete(f"/api/v1/me/payment-methods/{methods[0]['id']}").status_code == 204


def test_test_mode_tools_work_on_staging_but_never_with_real_gateway_or_production(api, provider_user, settings):
    api.force_authenticate(provider_user)
    settings.DEBUG, settings.APP_ENV = False, "staging"  # user-testing server
    assert api.post("/api/v1/dev/onboarding/acct_x/complete").status_code == 200
    settings.APP_ENV = "production"
    assert api.post("/api/v1/dev/onboarding/acct_x/complete").status_code == 404
    settings.APP_ENV, settings.PAYMENTS_TEST_MODE = "staging", False  # real Stripe configured
    assert api.post("/api/v1/dev/onboarding/acct_x/complete").status_code == 404


def test_config_exposes_test_mode(api):
    assert api.get("/api/v1/config").data["features"]["payments_test_mode"] is True
