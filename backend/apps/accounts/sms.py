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


class TwilioSMSBackend(SMSBackend):
    """Twilio Messaging REST API over plain HTTPS (no SDK)."""

    def send(self, to_e164: str, body: str) -> None:
        import base64
        import urllib.parse
        import urllib.request

        sid, token = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
        if not (sid and token and settings.TWILIO_FROM_NUMBER):
            raise RuntimeError("Twilio is not configured")
        data = urllib.parse.urlencode({"To": to_e164, "From": settings.TWILIO_FROM_NUMBER, "Body": body}).encode()
        request = urllib.request.Request(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data=data, method="POST",
            headers={"Authorization": "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode()},
        )
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - fixed https URL
            if response.status >= 300:
                raise RuntimeError(f"Twilio returned {response.status}")
