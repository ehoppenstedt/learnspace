"""In-process gateway for tests and local development (PAYMENT_GATEWAY=fake).

Behaves like a processor that always succeeds unless told otherwise. Webhooks are signed
with HMAC so the real verification path is exercised. Never enabled in production
(settings refuse PAYMENT_GATEWAY=fake when DEBUG is off).
"""

import hashlib
import hmac
import json

from django.conf import settings

from apps.core.ids import uuid7
from apps.payments.gateways.base import AccountStatus, Checkout, GatewayEvent, InvalidSignature

SIGNATURE_HEADER = "X-Fake-Signature"


class FakeGateway:
    name = "fake"
    calls: list[tuple[str, dict]] = []
    accounts: dict[str, AccountStatus] = {}
    fail_next: set[str] = set()  # e.g. {"refund"} to simulate a processor error

    def _record(self, op: str, **kwargs):
        from apps.payments.gateways.base import GatewayError

        FakeGateway.calls.append((op, kwargs))
        if op in FakeGateway.fail_next:
            FakeGateway.fail_next.discard(op)
            raise GatewayError(f"fake {op} failure")

    def ensure_customer(self, user, existing_id):
        if existing_id:
            return existing_id
        self._record("ensure_customer", user=str(user.pk))
        return f"cus_fake_{uuid7().hex[:16]}"

    def create_checkout(self, *, booking, customer_id, capture_manual, idempotency_key):
        self._record("create_checkout", amount=booking.total_cents, capture_manual=capture_manual, key=idempotency_key)
        # Same idempotency key -> same payment, like a real processor.
        pid = f"pi_fake_{hashlib.sha256(idempotency_key.encode()).hexdigest()[:20]}"
        return Checkout(payment_id=pid, client_secret=f"{pid}_secret", customer_id=customer_id,
                        ephemeral_key="ek_fake", publishable_key="pk_fake")

    def capture(self, payment_external_id, idempotency_key):
        self._record("capture", payment=payment_external_id)

    def cancel_authorization(self, payment_external_id):
        self._record("cancel_authorization", payment=payment_external_id)

    def refund(self, *, payment_external_id, amount_cents, idempotency_key, reason):
        self._record("refund", payment=payment_external_id, amount=amount_cents, key=idempotency_key)
        return f"re_fake_{uuid7().hex[:16]}"

    def onboard_provider(self, *, provider, existing_account_id, return_url, refresh_url):
        self._record("onboard_provider", provider=str(provider.pk))
        account = existing_account_id or f"acct_fake_{uuid7().hex[:12]}"
        FakeGateway.accounts.setdefault(account, AccountStatus(False, False, ["individual.id_number", "external_account"]))
        return account, f"{settings.PUBLIC_BASE_URL}/dev/fake-onboarding/{account}"

    def get_account_status(self, account_id):
        return FakeGateway.accounts.get(account_id, AccountStatus(False, False, ["external_account"]))

    def transfer(self, *, amount_cents, destination, source_charge, group, idempotency_key):
        self._record("transfer", amount=amount_cents, destination=destination, group=group)
        return f"tr_fake_{uuid7().hex[:16]}"

    def reverse_transfer(self, *, transfer_external_id, amount_cents, idempotency_key):
        self._record("reverse_transfer", transfer=transfer_external_id, amount=amount_cents)
        return f"trr_fake_{uuid7().hex[:16]}"

    def list_payment_methods(self, customer_id):
        return [{"id": "pm_fake_visa", "brand": "visa", "last4": "4242", "exp_month": 12, "exp_year": 2030}]

    def detach_payment_method(self, customer_id, payment_method_id):
        self._record("detach", pm=payment_method_id)

    # -- webhooks -------------------------------------------------------------

    @staticmethod
    def sign(body: bytes) -> str:
        return hmac.new(settings.FAKE_GATEWAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    @classmethod
    def build_event(cls, kind: str, object_id: str, **data) -> bytes:
        return json.dumps({"id": f"evt_fake_{uuid7().hex}", "kind": kind, "object_id": object_id, "data": data}).encode()

    def verify_and_parse_webhook(self, headers, body):
        signature = headers.get(SIGNATURE_HEADER, "")
        if not hmac.compare_digest(signature, self.sign(body)):
            raise InvalidSignature("bad signature")
        payload = json.loads(body)
        if payload["kind"] == "account_updated":
            FakeGateway.accounts[payload["object_id"]] = AccountStatus(
                payload["data"].get("charges_enabled", True), payload["data"].get("payouts_enabled", True),
                payload["data"].get("requirements_due", []),
            )
        return GatewayEvent(id=payload["id"], kind=payload["kind"], object_id=payload["object_id"],
                            data=payload.get("data", {}), raw_type=payload["kind"])
