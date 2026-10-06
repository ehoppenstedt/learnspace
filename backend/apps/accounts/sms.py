"""SMS delivery behind a tiny interface so the vendor (Twilio, Bird, SNS) is a config change."""

import logging

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class SMSBackend:
    def send(self, to_e164: str, body: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class ConsoleSMSBackend(SMSBackend):
    """Development only: writes the message to the log."""

    def send(self, to_e164: str, body: str) -> None:
        logger.warning("sms.console", extra={"to": to_e164, "body": body})


class LocmemSMSBackend(SMSBackend):
    """Tests: keeps messages in memory."""

    outbox: list[tuple[str, str]] = []

    def send(self, to_e164: str, body: str) -> None:
        LocmemSMSBackend.outbox.append((to_e164, body))


def get_sms_backend() -> SMSBackend:
    return import_string(settings.SMS_BACKEND)()
