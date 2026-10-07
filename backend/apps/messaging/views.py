from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.messaging import services
from apps.messaging.models import MessageThread


def _thread(user, t: MessageThread) -> dict:
    is_learner = user.pk == t.learner_id
    last = t.messages.filter(hidden=False).order_by("-created_at").first()
    cover = t.experience.experiencemedia_set.select_related("media").first()
    from apps.catalog.media import public_media

    return {
        "id": str(t.pk),
        "experience": {"id": str(t.experience_id), "title": t.experience.title,
                       "cover": public_media(cover.media) if cover else None},
        "role": "learner" if is_learner else "provider",
        "counterpart": t.provider.display_name if is_learner else f"{t.learner.first_name} {t.learner.last_name[:1]}.",
        "counterpart_id": str(t.provider_id if is_learner else t.learner_id),
        "booking_id": str(t.booking_id) if t.booking_id else None,
        "booked": t.booking_id is not None,
        "last_message": {"body": last.body, "at": last.created_at, "mine": last.sender_id == user.pk} if last else None,
        "unread": services.is_unread(user, t),
    }


def _message(user, m) -> dict:
    return {"id": str(m.pk), "body": m.body, "at": m.created_at, "mine": m.sender_id == user.pk, "flagged": bool(m.detected)}


class ThreadsView(APIView):
    def get(self, request):
        return Response([_thread(request.user, t) for t in services.threads_for(request.user)[:100]])

    def post(self, request):
        if booking_id := request.data.get("booking_id"):
            thread = services.thread_for_booking(request.user, booking_id)
        else:
            thread = services.thread_for_learner(request.user, request.data.get("experience_id"))
        return Response(_thread(request.user, thread), status=status.HTTP_201_CREATED)


class ThreadMessagesView(APIView):
    def get(self, request, pk):
        thread = services.get_thread(request.user, pk)
        qs = thread.messages.filter(hidden=False)
        after = parse_datetime(request.query_params.get("after", "") or "")
        if after:
            qs = qs.filter(created_at__gt=after)
        services.mark_read(request.user, thread)
        return Response({"thread": _thread(request.user, thread), "messages": [_message(request.user, m) for m in qs.order_by("created_at")[:500]]})

    def post(self, request, pk):
        thread = services.get_thread(request.user, pk)
        message = services.send(request.user, thread, str(request.data.get("body", "")),
                                acknowledged=bool(request.data.get("acknowledged_warning")))
        return Response(_message(request.user, message), status=status.HTTP_201_CREATED)


class UnreadCountView(APIView):
    def get(self, request):
        return Response({"unread": sum(services.is_unread(request.user, t) for t in services.threads_for(request.user)[:200])})
