import pytest

from apps.messaging.models import Message, MessageThread
from apps.moderation.models import Report
from apps.notifications.models import Notification
from conftest import auth, book, make_live_experience, make_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def experience(provider_user):
    return make_live_experience(provider_user)


def open_thread(api, user, experience):
    res = auth(api, user).post("/api/v1/threads", {"experience_id": str(experience.pk)}, format="json")
    assert res.status_code == 201, res.content
    return res.data["id"]


def send(api, thread_id, body, **extra):
    return api.post(f"/api/v1/threads/{thread_id}/messages", {"body": body, **extra}, format="json")


def test_learner_asks_before_booking_and_provider_answers(api, learner, provider_user, experience):
    tid = open_thread(api, learner, experience)
    assert open_thread(api, learner, experience) == tid  # one thread per learner and experience
    assert send(api, tid, "¿Necesito llevar material?").status_code == 201
    assert Notification.objects.filter(user=provider_user, kind="new_message").exists()

    auth(api, provider_user)
    assert api.get("/api/v1/threads/unread").data["unread"] == 1
    threads = api.get("/api/v1/threads").data
    assert threads[0]["role"] == "provider" and threads[0]["counterpart"] == "Ana L." and threads[0]["unread"] is True
    msgs = api.get(f"/api/v1/threads/{tid}/messages").data["messages"]
    assert [m["body"] for m in msgs] == ["¿Necesito llevar material?"] and msgs[0]["mine"] is False
    assert api.get("/api/v1/threads/unread").data["unread"] == 0
    assert send(api, tid, "No, todo está incluido.").status_code == 201
    assert auth(api, learner).get("/api/v1/threads/unread").data["unread"] == 1


def test_contact_info_warns_then_sends_flagged_when_acknowledged(api, learner, experience):
    tid = open_thread(api, learner, experience)
    res = send(api, tid, "mejor mándame whats al 55 1234 5678")
    assert res.status_code == 409 and res.data["error"]["code"] == "contact_info_warning"
    assert set(res.data["error"]["fields"]["detected"]) >= {"phone", "social"}
    assert not Message.objects.exists()
    res = send(api, tid, "mejor mándame whats al 55 1234 5678", acknowledged_warning=True)
    assert res.status_code == 201 and res.data["flagged"] is True
    assert "phone" in Message.objects.get().detected  # shows up in the admin flag queue


def test_no_warning_once_booked(api, jobs, learner, experience):
    book(api, jobs, learner, experience.sessions.get())
    tid = open_thread(api, learner, experience)
    res = send(api, tid, "Te mando mi cel por si me pierdo: 55 1234 5678")
    assert res.status_code == 201 and res.data["flagged"] is False
    assert MessageThread.objects.get().booking_id is not None


def test_provider_cannot_cold_message(api, jobs, learner, provider_user, experience):
    auth(api, provider_user)
    other = make_user(email="z@example.com", phone="+525500009999")
    res = api.post("/api/v1/threads", {"booking_id": "00000000-0000-0000-0000-000000000000"}, format="json")
    assert res.status_code == 404
    booking = book(api, jobs, learner, experience.sessions.get())
    res = auth(api, provider_user).post("/api/v1/threads", {"booking_id": str(booking.pk)}, format="json")
    assert res.status_code == 201 and res.data["booked"] is True
    # Third parties can't read or post in the thread.
    auth(api, other)
    assert api.get(f"/api/v1/threads/{res.data['id']}/messages").status_code == 404
    assert send(api, res.data["id"], "hola").status_code == 404


def test_cannot_message_own_experience(api, provider_user, experience):
    res = auth(api, provider_user).post("/api/v1/threads", {"experience_id": str(experience.pk)}, format="json")
    assert res.data["error"]["code"] == "own_experience"


def test_suspended_user_cannot_send(api, learner, experience):
    tid = open_thread(api, learner, experience)
    learner.status = "suspended"
    learner.save()
    assert send(api, tid, "hola").status_code in (401, 403)


def test_hidden_messages_disappear(api, learner, experience):
    tid = open_thread(api, learner, experience)
    send(api, tid, "hola")
    Message.objects.update(hidden=True)
    assert api.get(f"/api/v1/threads/{tid}/messages").data["messages"] == []


def test_report_message_and_user(api, learner, provider_user, experience):
    tid = open_thread(api, learner, experience)
    send(api, tid, "hola")
    message = Message.objects.get()
    auth(api, provider_user)
    payload = {"target_type": "message", "target_id": str(message.pk), "reason_code": "harassment"}
    assert api.post("/api/v1/reports", payload, format="json").status_code == 201
    assert api.post("/api/v1/reports", payload, format="json").status_code == 200  # deduplicated
    res = api.post("/api/v1/reports", {"target_type": "user", "target_id": str(learner.pk), "reason_code": "spam"}, format="json")
    assert res.status_code == 201
    assert Report.objects.count() == 2


def test_cannot_report_what_you_cannot_see(api, learner, provider_user, experience):
    tid = open_thread(api, learner, experience)
    send(api, tid, "hola")
    stranger = make_user(email="s@example.com", phone="+525577778888")
    auth(api, stranger)
    msg = {"target_type": "message", "target_id": str(Message.objects.get().pk), "reason_code": "spam"}
    assert api.post("/api/v1/reports", msg, format="json").status_code == 404
    usr = {"target_type": "user", "target_id": str(learner.pk), "reason_code": "spam"}
    assert api.post("/api/v1/reports", usr, format="json").status_code == 404
    exp = {"target_type": "experience", "target_id": str(experience.pk), "reason_code": "misleading"}
    assert api.post("/api/v1/reports", exp, format="json").status_code == 201
