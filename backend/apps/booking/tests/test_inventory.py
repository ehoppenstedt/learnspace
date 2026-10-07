import threading
from datetime import timedelta

import pytest
import time_machine
from django.db import connection
from django.utils import timezone

from apps.booking import services
from apps.booking.models import SeatHold
from apps.catalog.models import Experience, Session
from apps.core.exceptions import DomainError
from conftest import make_live_experience, make_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def session(provider_user):
    experience = make_live_experience(provider_user)
    s = experience.sessions.get()
    Session.objects.filter(pk=s.pk).update(capacity=3)
    s.refresh_from_db()
    return s


def learners(n):
    return [make_user(email=f"l{i}@example.com", phone=f"+52551000{i:04d}") for i in range(n)]


def test_hold_reduces_availability_and_blocks_oversell(session):
    a, b = learners(2)
    services.create_hold(a, session_id=session.pk, seats=2)
    assert services.available_seats(session) == 1
    with pytest.raises(DomainError) as exc:
        services.create_hold(b, session_id=session.pk, seats=2)
    assert exc.value.code == "seat_unavailable" and exc.value.fields["available"] == 1
    services.create_hold(b, session_id=session.pk, seats=1)
    assert services.available_seats(session) == 0


def test_expired_holds_free_seats(session):
    a, b = learners(2)
    services.create_hold(a, session_id=session.pk, seats=3)
    with time_machine.travel(timezone.now() + timedelta(minutes=10, seconds=1)):
        services.create_hold(b, session_id=session.pk, seats=3)
    assert SeatHold.objects.get(user=a).status == "expired"


def test_new_hold_replaces_own_previous_hold(session):
    (a,) = learners(1)
    services.create_hold(a, session_id=session.pk, seats=3)
    services.create_hold(a, session_id=session.pk, seats=2)  # would fail if the first still counted
    assert SeatHold.objects.filter(user=a, status="active").count() == 1


@pytest.mark.parametrize("seats", [0, 7])
def test_seat_limits(session, seats):
    (a,) = learners(1)
    with pytest.raises(DomainError):
        services.create_hold(a, session_id=session.pk, seats=seats)


def test_cannot_book_own_paused_or_started(session, provider_user):
    (a,) = learners(1)
    with pytest.raises(DomainError) as exc:
        services.create_hold(provider_user, session_id=session.pk, seats=1)
    assert exc.value.code == "own_experience"
    Experience.objects.filter(pk=session.experience_id).update(status="paused")
    with pytest.raises(DomainError) as exc:
        services.create_hold(a, session_id=session.pk, seats=1)
    assert exc.value.code == "not_bookable"
    Experience.objects.filter(pk=session.experience_id).update(status="live")
    with time_machine.travel(session.starts_at + timedelta(minutes=1)), pytest.raises(DomainError) as exc:
        services.create_hold(a, session_id=session.pk, seats=1)
    assert exc.value.code == "already_started"


def test_incomplete_profile_cannot_hold(session):
    user = make_user(email="x@example.com", phone="+525588887777", complete=False)
    with pytest.raises(DomainError) as exc:
        services.create_hold(user, session_id=session.pk, seats=1)
    assert exc.value.code == "profile_incomplete"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_concurrent_holds_never_oversell(provider_user):
    """10 learners race for 3 seats from separate DB connections: exactly 3 win."""
    experience = make_live_experience(provider_user)
    session = experience.sessions.get()
    Session.objects.filter(pk=session.pk).update(capacity=3)
    people = learners(10)
    barrier = threading.Barrier(len(people))
    results = []

    def attempt(user):
        try:
            barrier.wait()
            services.create_hold(user, session_id=session.pk, seats=1)
            results.append("ok")
        except DomainError as exc:
            results.append(exc.code)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt, args=(u,)) for u in people]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 3
    assert results.count("seat_unavailable") == 7
    assert SeatHold.objects.filter(session=session, status="active").count() == 3


def test_course_hold_is_per_cohort(provider_user):
    from apps.catalog import services as catalog
    from conftest import make_space

    space = make_space(provider_user)
    experience = catalog.create_experience(provider_user.provider_profile, {"title": "Curso", "offering_type": "course",
                                                                           "space_id": str(space.pk)})
    start = timezone.now() + timedelta(days=3)
    cohort = catalog.create_cohort(experience, label="Nov", capacity=2,
                                   windows=[(start + timedelta(days=7 * i), start + timedelta(days=7 * i, hours=2)) for i in range(3)])
    Experience.objects.filter(pk=experience.pk).update(status="live")
    a, b = learners(2)
    with pytest.raises(DomainError):
        services.create_hold(a, session_id=cohort.sessions.first().pk, seats=1)  # sessions of a course aren't sold alone
    services.create_hold(a, cohort_id=cohort.pk, seats=2)
    with pytest.raises(DomainError):
        services.create_hold(b, cohort_id=cohort.pk, seats=1)
