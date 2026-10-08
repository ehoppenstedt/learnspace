"""Per-request platform rules (the app sends X-Client-Platform: ios | android | web).

App Store guideline 3.1.1 / 3.1.3(d): live online classes for a group, bought inside the iOS app,
must use In-App Purchase. One-to-one online classes (3.1.3(d)) and in-person classes (3.1.3(e))
may use any payment method.
"""

from django.conf import settings

CARD, APP_STORE = "card", "app_store"


def client_platform(request) -> str:
    return (request.headers.get("X-Client-Platform") or "").lower() if request is not None else ""


def is_ios(request) -> bool:
    return client_platform(request) == "ios"


def online_allowed(request) -> bool:
    return settings.FEATURE_ONLINE_EXPERIENCES


def is_group_online(experience, capacity: int | None = None) -> bool:
    capacity = experience.default_capacity if capacity is None else capacity
    return experience.modality == "online" and capacity > 1


def hide_group_online(request) -> bool:
    return is_ios(request) and settings.IOS_ONLINE_GROUP_PAYMENTS != APP_STORE


def visible_on_platform(request, experience) -> bool:
    if experience.modality != "online":
        return True
    return online_allowed(request) and not (hide_group_online(request) and is_group_online(experience))


def uses_app_store(request, experience, capacity: int | None = None, seats: int = 1) -> bool:
    """True when this purchase must go through Apple In-App Purchase."""
    if not is_ios(request) or experience.modality != "online":
        return False
    if seats == 1 and not is_group_online(experience, capacity):
        return False  # one-to-one: person-to-person service, Stripe allowed
    return True


def payment_channel(request, experience, capacity: int | None = None, seats: int = 1) -> str | None:
    """card | app_store, or None when this device can't buy it."""
    if experience.modality == "online" and not online_allowed(request):
        return None
    if not uses_app_store(request, experience, capacity, seats):
        return CARD
    return APP_STORE if settings.IOS_ONLINE_GROUP_PAYMENTS == APP_STORE else None
