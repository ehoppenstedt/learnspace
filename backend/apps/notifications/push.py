"""Push delivery. Expo's push service fronts APNs and FCM with one HTTPS API."""

import json
import logging
import urllib.request

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)
EXPO_URL = "https://exp.host/--/api/v2/push/send"


class PushBackend:
    def send(self, tokens: list[str], title: str, body: str, data: dict) -> list[str]:
        """Returns tokens the service reported as no longer registered."""
        raise NotImplementedError


class ConsolePushBackend(PushBackend):
    def send(self, tokens, title, body, data):
        logger.info("push.console", extra={"tokens": len(tokens), "title": title, "body": body, "data": data})
        return []


class LocmemPushBackend(PushBackend):
    outbox: list[dict] = []

    def send(self, tokens, title, body, data):
        LocmemPushBackend.outbox.append({"tokens": tokens, "title": title, "body": body, "data": data})
        return []


class ExpoPushBackend(PushBackend):
    def send(self, tokens, title, body, data):
        dead = []
        for start in range(0, len(tokens), 100):
            batch = tokens[start:start + 100]
            messages = [{"to": t, "title": title, "body": body, "data": data, "sound": "default"} for t in batch]
            request = urllib.request.Request(EXPO_URL, data=json.dumps(messages).encode(), method="POST", headers={
                "Content-Type": "application/json", "Accept": "application/json",
                **({"Authorization": f"Bearer {settings.EXPO_PUSH_ACCESS_TOKEN}"} if settings.EXPO_PUSH_ACCESS_TOKEN else {}),
            })
            with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - fixed https URL
                tickets = json.loads(response.read()).get("data", [])
            for token, ticket in zip(batch, tickets, strict=False):
                if ticket.get("status") == "error" and (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
                    dead.append(token)
        return dead


def get_push_backend() -> PushBackend:
    return import_string(settings.PUSH_BACKEND)()
