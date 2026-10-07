from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status

from apps.booking.models import Booking
from apps.catalog.models import Experience
from apps.core.exceptions import DomainError
from apps.messaging.detection import detect
from apps.messaging.models import Message, MessageThread

BOOKED = ["confirmed", "completed", "no_show", "pending_approval"]


def thread_for_learner(learner, experience_id) -> MessageThread:
    experience = Experience.objects.select_related("provider").filter(pk=experience_id, status__in=["live", "paused"]).first()
    if experience is None:
        raise DomainError("not_found", _("Experiencia no encontrada."), status.HTTP_404_NOT_FOUND)
    if experience.provider_id == learner.pk:
        raise DomainError("own_experience", _("No puedes escribirte a ti mismo."))
    thread, _created = MessageThread.objects.get_or_create(
        experience=experience, learner=learner, defaults={"provider": experience.provider})
    _link_booking(thread)
    return thread


def thread_for_booking(provider_user, booking_id) -> MessageThread:
    """Providers can't cold-message people; they can open a conversation with someone who booked."""
    booking = Booking.objects.select_related("experience").filter(
        pk=booking_id, experience__provider_id=provider_user.pk, status__in=BOOKED).first()
    if booking is None:
        raise DomainError("not_found", _("Reserva no encontrada."), status.HTTP_404_NOT_FOUND)
    thread, _created = MessageThread.objects.get_or_create(
        experience=booking.experience, learner=booking.learner, defaults={"provider": booking.experience.provider, "booking": booking})
    _link_booking(thread)
    return thread


def _link_booking(thread: MessageThread) -> None:
    booking = Booking.objects.filter(learner=thread.learner, experience=thread.experience, status__in=BOOKED).order_by("-created_at").first()
    if booking and thread.booking_id != booking.pk:
        thread.booking = booking
        thread.save(update_fields=["booking", "updated_at"])


def threads_for(user):
    return MessageThread.objects.filter(Q(learner=user) | Q(provider_id=user.pk)).select_related(
        "experience", "learner", "provider").order_by("-last_message_at", "-created_at")


def get_thread(user, thread_id) -> MessageThread:
    thread = threads_for(user).filter(pk=thread_id).first()
    if thread is None:
        raise DomainError("not_found", _("Conversación no encontrada."), status.HTTP_404_NOT_FOUND)
    return thread


def has_booking(thread: MessageThread) -> bool:
    return Booking.objects.filter(learner=thread.learner, experience=thread.experience, status__in=BOOKED).exists()


def send(user, thread: MessageThread, body: str, *, acknowledged: bool = False) -> Message:
    body = (body or "").strip()
    if not body:
        raise DomainError("empty", _("Escribe un mensaje."), status.HTTP_400_BAD_REQUEST)
    if user.status != "active":
        raise DomainError("account_inactive", _("Esta cuenta no está activa."), status.HTTP_403_FORBIDDEN)
    detected = [] if has_booking(thread) else detect(body)
    if detected and not acknowledged:
        # The client shows a warning and may resend with acknowledged=true.
        raise DomainError("contact_info_warning",
                          _("Compartir datos de contacto o pagos fuera de la app antes de reservar te deja sin protección "
                            "(reembolsos, política de cancelación, soporte)."),
                          fields={"detected": detected})
    with transaction.atomic():
        message = Message.objects.create(thread=thread, sender=user, body=body[:2000], detected=detected)
        now = timezone.now()
        thread.last_message_at = now
        if user.pk == thread.learner_id:
            thread.learner_read_at = now
        else:
            thread.provider_read_at = now
        thread.save(update_fields=["last_message_at", "learner_read_at", "provider_read_at", "updated_at"])
        _notify(thread, message)
    return message


def mark_read(user, thread: MessageThread) -> None:
    field = "learner_read_at" if user.pk == thread.learner_id else "provider_read_at"
    setattr(thread, field, timezone.now())
    thread.save(update_fields=[field, "updated_at"])


def is_unread(user, thread: MessageThread) -> bool:
    read = thread.learner_read_at if user.pk == thread.learner_id else thread.provider_read_at
    return bool(thread.last_message_at and (read is None or read < thread.last_message_at)
                and thread.messages.exclude(sender=user).filter(created_at__gt=read or thread.created_at).exists())


def _notify(thread, message) -> None:
    from apps.notifications.services import notify

    recipient = thread.provider.user if message.sender_id == thread.learner_id else thread.learner
    sender_name = thread.provider.display_name if message.sender_id != thread.learner_id else thread.learner.first_name
    notify(recipient, "new_message", {"sender": sender_name, "preview": message.body[:120], "thread_id": str(thread.pk),
                                      "title": thread.experience.title},
           dedupe=f"msg:{message.pk}", channels=("push",))
