"""Stripe Connect adapter: separate charges and transfers.

- The platform charges the learner the total (listed + fee) and pays Stripe's fee.
- After the class, the provider's share is transferred to their connected account
  (source_transaction = the charge, so it never depends on platform balance timing).
- Connected accounts use controller properties (Stripe-hosted onboarding/KYC, Express-like
  dashboard, platform pays fees and is liable for losses), weekly payouts to their CLABE.
"""

import stripe
from django.conf import settings

from apps.payments.gateways.base import AccountStatus, Checkout, GatewayError, GatewayEvent, InvalidSignature

EVENT_KINDS = {
    "payment_intent.succeeded": "payment_succeeded",
    "payment_intent.amount_capturable_updated": "payment_authorized",
    "payment_intent.payment_failed": "payment_failed",
    "payment_intent.canceled": "payment_canceled",
    "refund.updated": "refund_updated",
    "refund.failed": "refund_failed",
    "account.updated": "account_updated",
    "charge.dispute.created": "dispute_created",
}


class StripeGateway:
    name = "stripe"

    def __init__(self):
        if not settings.STRIPE_SECRET_KEY:
            raise GatewayError("STRIPE_SECRET_KEY is not configured")
        self.client = stripe.StripeClient(settings.STRIPE_SECRET_KEY, max_network_retries=2)

    def _call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except stripe.StripeError as exc:
            raise GatewayError(f"{type(exc).__name__}: {exc.user_message or exc}") from exc

    def ensure_customer(self, user, existing_id):
        if existing_id:
            return existing_id
        customer = self._call(self.client.v1.customers.create, params={
            "email": user.email or None, "name": user.full_name or None, "phone": user.phone_e164 or None,
            "metadata": {"user_id": str(user.pk)},
        }, options={"idempotency_key": f"customer-{user.pk}"})
        return customer.id

    def create_checkout(self, *, booking, customer_id, capture_manual, idempotency_key):
        intent = self._call(self.client.v1.payment_intents.create, params={
            "amount": booking.total_cents,
            "currency": "mxn",
            "customer": customer_id,
            "automatic_payment_methods": {"enabled": True},  # cards, Apple Pay, Google Pay
            "capture_method": "manual" if capture_manual else "automatic",
            "setup_future_usage": "on_session",  # learner can reuse the card
            "transfer_group": booking.code,
            "description": f"{booking.experience.title[:60]} · {booking.code}",
            "statement_descriptor_suffix": settings.BRAND_NAME[:10].upper(),
            "metadata": {"booking_id": str(booking.pk), "booking_code": booking.code},
        }, options={"idempotency_key": idempotency_key})
        key = self._call(self.client.v1.ephemeral_keys.create, params={"customer": customer_id},
                         options={"stripe_version": settings.STRIPE_EPHEMERAL_KEY_API_VERSION})
        return Checkout(payment_id=intent.id, client_secret=intent.client_secret, customer_id=customer_id,
                        ephemeral_key=key.secret, publishable_key=settings.STRIPE_PUBLISHABLE_KEY)

    def capture(self, payment_external_id, idempotency_key):
        self._call(self.client.v1.payment_intents.capture, payment_external_id, options={"idempotency_key": idempotency_key})

    def cancel_authorization(self, payment_external_id):
        self._call(self.client.v1.payment_intents.cancel, payment_external_id)

    def refund(self, *, payment_external_id, amount_cents, idempotency_key, reason):
        refund = self._call(self.client.v1.refunds.create, params={
            "payment_intent": payment_external_id, "amount": amount_cents, "reason": "requested_by_customer",
            "metadata": {"reason": reason},
        }, options={"idempotency_key": idempotency_key})
        return refund.id

    def onboard_provider(self, *, provider, existing_account_id, return_url, refresh_url):
        account_id = existing_account_id
        if not account_id:
            account = self._call(self.client.v1.accounts.create, params={
                "country": "MX",
                "email": provider.user.email,
                "controller": {
                    "fees": {"payer": "application"},
                    "losses": {"payments": "application"},
                    "requirement_collection": "stripe",
                    "stripe_dashboard": {"type": "express"},
                },
                "capabilities": {"transfers": {"requested": True}},
                "business_profile": {"product_description": "Clases y talleres presenciales", "mcc": "8299"},
                "settings": {"payouts": {"schedule": {"interval": "weekly", "weekly_anchor": "friday"}}},
                "metadata": {"provider_id": str(provider.pk)},
            }, options={"idempotency_key": f"account-{provider.pk}"})
            account_id = account.id
        link = self._call(self.client.v1.account_links.create, params={
            "account": account_id, "type": "account_onboarding", "return_url": return_url, "refresh_url": refresh_url,
        })
        return account_id, link.url

    def get_account_status(self, account_id):
        account = self._call(self.client.v1.accounts.retrieve, account_id).to_dict()
        due = list((account.get("requirements") or {}).get("currently_due") or [])
        return AccountStatus(bool(account.get("charges_enabled")), bool(account.get("payouts_enabled")), due)

    def transfer(self, *, amount_cents, destination, source_charge, group, idempotency_key):
        transfer = self._call(self.client.v1.transfers.create, params={
            "amount": amount_cents, "currency": "mxn", "destination": destination,
            "source_transaction": source_charge, "transfer_group": group,
        }, options={"idempotency_key": idempotency_key})
        return transfer.id

    def reverse_transfer(self, *, transfer_external_id, amount_cents, idempotency_key):
        reversal = self._call(self.client.v1.transfers.reversals.create, transfer_external_id,
                              params={"amount": amount_cents}, options={"idempotency_key": idempotency_key})
        return reversal.id

    def list_payment_methods(self, customer_id):
        methods = self._call(self.client.v1.payment_methods.list, params={"customer": customer_id, "type": "card"})
        return [
            {"id": m.id, "brand": m.card.brand, "last4": m.card.last4, "exp_month": m.card.exp_month, "exp_year": m.card.exp_year}
            for m in methods.data
        ]

    def detach_payment_method(self, customer_id, payment_method_id):
        method = self._call(self.client.v1.payment_methods.retrieve, payment_method_id)
        if method.customer != customer_id:
            raise GatewayError("payment method does not belong to customer")
        self._call(self.client.v1.payment_methods.detach, payment_method_id)

    def verify_and_parse_webhook(self, headers, body):
        signature = headers.get("Stripe-Signature")
        event = None
        for secret in settings.STRIPE_WEBHOOK_SECRETS:  # platform endpoint + Connect endpoint
            try:
                event = stripe.Webhook.construct_event(body, signature, secret)
                break
            except (stripe.SignatureVerificationError, ValueError):
                continue
        if event is None:
            raise InvalidSignature("no configured secret matches")
        event = event.to_dict()  # stripe-python v8+ objects are not dicts
        obj = event["data"]["object"]
        kind = EVENT_KINDS.get(event["type"], "ignored")
        data: dict = {}
        object_id = obj.get("id", "")
        if kind.startswith("payment_"):
            data = {
                "charge_id": obj.get("latest_charge") or "",
                "method": (obj.get("payment_method_types") or [""])[0],
                "reason": ((obj.get("last_payment_error") or {}).get("message") or "")[:200],
            }
        elif kind.startswith("refund_"):
            data = {"status": obj.get("status"), "payment_intent": obj.get("payment_intent")}
        elif kind == "account_updated":
            data = {
                "charges_enabled": obj.get("charges_enabled", False),
                "payouts_enabled": obj.get("payouts_enabled", False),
                "requirements_due": list((obj.get("requirements") or {}).get("currently_due") or []),
            }
        elif kind == "dispute_created":
            object_id = obj.get("payment_intent") or ""
            data = {"dispute_id": obj.get("id"), "amount": obj.get("amount"), "reason": obj.get("reason")}
        return GatewayEvent(id=event["id"], kind=kind, object_id=object_id, data=data, raw_type=event["type"])
