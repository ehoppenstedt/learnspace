from functools import lru_cache

from django.conf import settings

from apps.payments.gateways.base import PaymentProvider


@lru_cache(maxsize=2)
def _build(name: str) -> PaymentProvider:
    if name == "stripe":
        from apps.payments.gateways.stripe_gateway import StripeGateway

        return StripeGateway()
    if name == "fake":
        from apps.payments.gateways.fake import FakeGateway

        return FakeGateway()
    raise ValueError(f"Unknown PAYMENT_GATEWAY {name!r}")


def get_gateway(name: str | None = None) -> PaymentProvider:
    return _build(name or settings.PAYMENT_GATEWAY)
