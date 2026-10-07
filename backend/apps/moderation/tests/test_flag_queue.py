import pytest

from apps.accounts.models import User
from apps.messaging import services as messaging
from apps.messaging.models import Message
from apps.moderation.models import AdminAction, Report
from conftest import make_live_experience

pytestmark = pytest.mark.django_db


@pytest.fixture
def message(learner, provider_user):
    experience = make_live_experience(provider_user)
    thread = messaging.thread_for_learner(learner, experience.pk)
    return messaging.send(learner, thread, "hola, ¿hay estacionamiento?")


def _action(client, model, action, ids):
    return client.post(f"/admin/{model}/", {"action": action, "_selected_action": [str(i) for i in ids]})


def test_hide_reported_message(client, admin_user, provider_user, message):
    report = Report.objects.create(reporter=provider_user, target_type="message", target_id=str(message.pk), reason_code="harassment")
    client.force_login(admin_user)
    assert client.get("/admin/moderation/report/").status_code == 200
    assert client.get(f"/admin/moderation/report/{report.pk}/change/").status_code == 200
    _action(client, "moderation/report", "hide_content", [report.pk])
    report.refresh_from_db()
    assert report.status == "actioned" and Message.objects.get().hidden is True
    assert AdminAction.objects.filter(action="report.actioned").exists()


def test_suspend_reported_user_and_view_thread_is_audited(client, admin_user, provider_user, learner, message):
    report = Report.objects.create(reporter=provider_user, target_type="user", target_id=str(learner.pk), reason_code="spam")
    client.force_login(admin_user)
    _action(client, "moderation/report", "suspend_user", [report.pk])
    assert User.objects.get(pk=learner.pk).status == "suspended"
    assert client.get(f"/admin/messaging/messagethread/{message.thread_id}/change/").status_code == 200
    assert AdminAction.objects.filter(action="thread.view").exists()


def test_review_and_appeal_admin_pages_render(client, admin_user):
    client.force_login(admin_user)
    for url in ("reviews/review", "reviews/conductappeal", "reviews/conductrating", "messaging/message"):
        assert client.get(f"/admin/{url}/").status_code == 200, url
