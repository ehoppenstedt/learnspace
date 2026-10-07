"""Per-request platform rules (the app sends X-Client-Platform: ios | android | web)."""

from django.conf import settings


def client_platform(request) -> str:
    return (request.headers.get("X-Client-Platform") or "").lower()


def online_allowed(request) -> bool:
    if not settings.FEATURE_ONLINE_EXPERIENCES:
        return False
    return client_platform(request) != "ios" or settings.ONLINE_EXPERIENCES_ON_IOS
