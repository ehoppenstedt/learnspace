from datetime import date, timedelta

import pytest
from django.contrib.gis.geos import Point
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import LearnerProfile, ProviderProfile, User
from apps.accounts.sms import LocmemSMSBackend
from apps.catalog import services as catalog
from apps.catalog.models import CancellationPolicy, Category, Experience, MediaAsset, Space

ROMA_NORTE = (19.4194, -99.1617)


@pytest.fixture(autouse=True)
def _test_settings(settings, tmp_path):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    settings.SMS_BACKEND = "apps.accounts.sms.LocmemSMSBackend"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.MEDIA_STORAGE = "local"
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.PUBLIC_BASE_URL = "http://testserver"
    from apps.catalog.storage import get_storage

    get_storage.cache_clear()
    LocmemSMSBackend.outbox = []
    from django.core.cache import cache

    cache.clear()
    yield
    get_storage.cache_clear()


@pytest.fixture(autouse=True)
def jobs():
    """Background jobs go to an in-memory queue; tests run them explicitly with run_jobs()."""
    from procrastinate import testing
    from procrastinate.contrib.django import app

    connector = testing.InMemoryConnector()
    with app.replace_connector(connector):
        yield connector


@pytest.fixture(autouse=True)
def _commit_hooks_run_immediately(monkeypatch):
    """Tests run inside a transaction that never commits; behave as if it committed."""
    from django.db import transaction

    monkeypatch.setattr(transaction, "on_commit", lambda func, using=None, robust=False: func())


def run_jobs(connector, rounds=5) -> list[str]:
    """Execute queued jobs in-process (jobs may enqueue more jobs)."""
    from procrastinate.contrib.django import app

    ran = []
    for _ in range(rounds):
        todo = [j for j in connector.jobs.values() if j["status"] == "todo"]
        if not todo:
            break
        for job in todo:
            job["status"] = "succeeded"
            app.tasks[job["task_name"]](**job["args"])
            ran.append(job["task_name"])
    return ran


@pytest.fixture(autouse=True)
def _fake_gateway(settings):
    from apps.notifications.push import LocmemPushBackend
    from apps.payments.gateways.fake import FakeGateway

    settings.PAYMENT_GATEWAY = "fake"
    settings.PUSH_BACKEND = "apps.notifications.push.LocmemPushBackend"
    FakeGateway.calls, FakeGateway.accounts, FakeGateway.fail_next = [], {}, set()
    LocmemPushBackend.outbox = []
    yield


@pytest.fixture
def api():
    return APIClient()


def make_user(*, email="ana@example.com", phone="+525512345678", complete=True, **extra) -> User:
    user = User.objects.create_user(email=email, phone_e164=phone, phone_verified=True, email_verified=True, **extra)
    if complete:
        user.first_name, user.last_name = "Ana", "López"
        user.date_of_birth = date(1990, 5, 17)
        user.save()
    LearnerProfile.objects.create(user=user)
    return user


@pytest.fixture
def learner(db):
    return make_user()


@pytest.fixture
def provider_user(db):
    user = make_user(email="maestra@example.com", phone="+525598765432")
    make_payout_ready(ProviderProfile.objects.create(user=user, display_name="Taller Luz", verification_status="verified"))
    return user


def make_payout_ready(provider):
    from apps.payments.models import PaymentAccount, ProviderTaxProfile

    PaymentAccount.objects.create(provider=provider, gateway="fake", external_id=f"acct_fake_{provider.pk.hex[:10]}",
                                  kyc_status="verified", charges_enabled=True, payouts_enabled=True)
    ProviderTaxProfile.objects.create(provider=provider, rfc="LOPA900517AB1", legal_name="Ana López")
    return provider


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(email="admin@example.com", password="correct-horse-battery-staple")


def auth(client: APIClient, user: User) -> APIClient:
    client.force_authenticate(user)
    return client


def ready_image(owner, color="#aa5500") -> MediaAsset:
    asset = MediaAsset(owner=owner, kind="image", content_type="image/jpeg", declared_bytes=1000,
                       status="ready", external_url="https://picsum.photos/seed/x/1200/900", dominant_color=color)
    asset.storage_key = f"image/{owner.pk}/{asset.id}/original"
    asset.save()
    return asset


def make_space(owner, lat=ROMA_NORTE[0], lng=ROMA_NORTE[1], name="Estudio Roma") -> Space:
    space = Space(owner=owner, name=name, address_line="Colima 123, Roma Norte", neighborhood="")
    return catalog.save_space(space, lat=lat, lng=lng)


def make_live_experience(provider_user, *, space=None, title="Acuarela para principiantes", price_cents=50000,
                         category_slug="art", starts_in=timedelta(days=3), hour=19, duration_min=120,
                         language="es") -> Experience:
    space = space or make_space(provider_user)
    experience = catalog.create_experience(provider_user.provider_profile, {
        "title": title,
        "what_you_learn": "Técnicas básicas de acuarela: aguadas, capas, mezcla de color y composición.",
        "who_its_for": "Adultos sin experiencia previa.",
        "category_id": Category.objects.get(slug=category_slug).pk,
        "instruction_language": language,
        "listed_price_cents": price_cents,
        "space_id": str(space.pk),
        "media_ids": [str(ready_image(provider_user).pk) for _ in range(3)],
    })
    start_day = timezone.localdate() + starts_in
    start = timezone.make_aware(timezone.datetime.combine(start_day, timezone.datetime.min.time()).replace(hour=hour))
    catalog.create_sessions(experience, [(start, start + timedelta(minutes=duration_min))])
    experience.status = Experience.Status.LIVE
    experience.save()
    catalog.refresh_denorm(experience)
    return experience


@pytest.fixture
def standard_policy(db):
    return CancellationPolicy.objects.get(code="standard")


def point(lat, lng):
    return Point(lng, lat, srid=4326)


# ---------------------------------------------------------------- booking helpers


def post_fake_event(client, kind: str, object_id: str, **data):
    from apps.payments.gateways.fake import SIGNATURE_HEADER, FakeGateway

    body = FakeGateway.build_event(kind, object_id, **data)
    return client.generic("POST", "/api/v1/webhooks/payments/fake", body, content_type="application/json",
                          **{f"HTTP_{SIGNATURE_HEADER.upper().replace('-', '_')}": FakeGateway.sign(body)})


def hold_and_checkout(api, learner, session=None, cohort=None, seats=1):
    api.force_authenticate(learner)
    payload = {"seats": seats, **({"session_id": str(session.pk)} if session else {"cohort_id": str(cohort.pk)})}
    hold = api.post("/api/v1/holds", payload, format="json")
    assert hold.status_code == 201, hold.content
    res = api.post("/api/v1/bookings", {"hold_id": hold.data["hold_id"]}, format="json")
    assert res.status_code == 201, res.content
    from apps.booking.models import Booking

    return Booking.objects.get(pk=res.data["booking"]["id"])


def pay(api, jobs, booking, kind="payment_succeeded"):
    payment = booking.payments.exclude(gateway="credit").get()
    res = post_fake_event(api, kind, payment.external_id, charge_id=f"ch_{payment.pk.hex[:8]}", method="card")
    assert res.status_code == 200
    run_jobs(jobs)
    booking.refresh_from_db()
    return booking


def book(api, jobs, learner, session, seats=1):
    return pay(api, jobs, hold_and_checkout(api, learner, session=session, seats=seats))
