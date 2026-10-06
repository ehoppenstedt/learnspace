"""The swap point between the marketplace and a payment processor.

Business logic (booking, cancellations, transfers) only talks to this interface. Adding
Mercado Pago or Conekta later means writing one adapter, not touching booking code.
"""

from dataclasses import dataclass, field
from typing import Protocol


class GatewayError(Exception):
    """Processor rejected the call or is unreachable. Message is safe to log, not to show."""


class InvalidSignature(Exception):
    pass


@dataclass(frozen=True)
class Checkout:
    """What the mobile payment sheet needs."""

    payment_id: str
    client_secret: str
    customer_id: str
    ephemeral_key: str | None
    publishable_key: str


@dataclass(frozen=True)
class AccountStatus:
    charges_enabled: bool
    payouts_enabled: bool
    requirements_due: list[str] = field(default_factory=list)

    @property
    def kyc_status(self) -> str:
        if self.payouts_enabled and not self.requirements_due:
            return "verified"
        return "restricted" if self.requirements_due and self.charges_enabled else "pending"


@dataclass(frozen=True)
class GatewayEvent:
    """Normalized webhook event.

    kind: payment_succeeded | payment_authorized | payment_failed | payment_canceled |
          refund_succeeded | refund_failed | account_updated | dispute_created | ignored
    """

    id: str
    kind: str
    object_id: str
    data: dict
    raw_type: str


class PaymentProvider(Protocol):
    name: str

    def ensure_customer(self, user, existing_id: str | None) -> str: ...

    def create_checkout(self, *, booking, customer_id: str, capture_manual: bool, idempotency_key: str) -> Checkout: ...

    def capture(self, payment_external_id: str, idempotency_key: str) -> None: ...

    def cancel_authorization(self, payment_external_id: str) -> None: ...

    def refund(self, *, payment_external_id: str, amount_cents: int, idempotency_key: str, reason: str) -> str: ...

    def onboard_provider(self, *, provider, existing_account_id: str | None, return_url: str, refresh_url: str) -> tuple[str, str]: ...

    def get_account_status(self, account_id: str) -> AccountStatus: ...

    def transfer(self, *, amount_cents: int, destination: str, source_charge: str, group: str, idempotency_key: str) -> str: ...

    def reverse_transfer(self, *, transfer_external_id: str, amount_cents: int, idempotency_key: str) -> str: ...

    def list_payment_methods(self, customer_id: str) -> list[dict]: ...

    def detach_payment_method(self, customer_id: str, payment_method_id: str) -> None: ...

    def verify_and_parse_webhook(self, headers, body: bytes) -> GatewayEvent: ...
