import pytest
from django.core.management import call_command

from apps.catalog.models import Experience
from apps.messaging.models import MessageThread
from apps.reviews.models import Review

pytestmark = pytest.mark.django_db


def test_seed_creates_consistent_reviews_and_test_scenario(settings):
    settings.DEBUG = True
    call_command("seed_cdmx", experiences=12, providers=4, stdout=open("/dev/null", "w"))
    rated = Experience.objects.filter(rating_count__gt=0)
    assert rated.exists()
    for e in rated:  # denormalized numbers come from real, revealed reviews
        assert e.rating_count == Review.objects.filter(experience=e, revealed_at__isnull=False).count()
    assert Experience.objects.filter(modality="online", status="live").exists()
    assert MessageThread.objects.filter(learner__email="learner@seed.learnspace.local").exists()
    call_command("seed_cdmx", experiences=12, providers=4, reset=True, stdout=open("/dev/null", "w"))
