"""Stripe adapter without network: signature verification and request parameters."""

import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest import mock

import pytest

from apps.payments.gateways.base import InvalidSignature


@pytest.fixture
def gateway(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    settings.STRIPE_PUBLISHABLE_KEY = "pk_test_x"
    settings.STRIPE_WEBHOOK_SECRETS = ["whsec_platform", "whsec_connect"]
    from apps.payments.gateways.stripe_gateway import StripeGateway

    return StripeGateway()


def _signed(payload: dict, secret: str):
    body = json.dumps(payload).encode()
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return body, {"Stripe-Signature": f"t={ts},v1={sig}"}


def _event(type_, obj):
    return {"id": "evt_1", "object": "event", "type": type_, "api_version": "2026-09-30.endive", "data": {"object": obj}}


def test_payment_succeeded_mapping(gateway):
    body, headers = _signed(_event("payment_intent.succeeded", {"id": "pi_1", "object": "payment_intent",
                                                                  "latest_charge": "ch_1", "payment_method_types": ["card"]}),
                            "whsec_platform")
    event = gateway.verify_and_parse_webhook(headers, body)
    assert (event.kind, event.object_id, event.data["charge_id"]) == ("payment_succeeded", "pi_1", "ch_1")


def test_connect_secret_also_accepted_and_account_mapping(gateway):
    body, headers = _signed(_event("account.updated", {"id": "acct_1", "object": "account", "charges_enabled": True,
                                                         "payouts_enabled": False, "requirements": {"currently_due": ["external_account"]}}),
                            "whsec_connect")
    event = gateway.verify_and_parse_webhook(headers, body)
    assert event.kind == "account_updated" and event.data["requirements_due"] == ["external_account"]


def test_bad_signature_rejected(gateway):
    body, headers = _signed(_event("payment_intent.succeeded", {"id": "pi_1"}), "whsec_wrong")
    with pytest.raises(InvalidSignature):
        gateway.verify_and_parse_webhook(headers, body)


def test_unknown_events_are_ignored(gateway):
    body, headers = _signed(_event("customer.created", {"id": "cus_1"}), "whsec_platform")
    assert gateway.verify_and_parse_webhook(headers, body).kind == "ignored"


def test_checkout_parameters(gateway):
    booking = SimpleNamespace(total_cents=55000, code="ABC123", pk="b1", experience=SimpleNamespace(title="Acuarela"))
    with mock.patch.object(gateway.client.v1.payment_intents, "create",
                           return_value=SimpleNamespace(id="pi_1", client_secret="pi_1_secret")) as create, \
         mock.patch.object(gateway.client.v1.ephemeral_keys, "create", return_value=SimpleNamespace(secret="ek_1")):
        checkout = gateway.create_checkout(booking=booking, amount_cents=55000, customer_id="cus_1", capture_manual=True, idempotency_key="checkout-b1")
    params = create.call_args.kwargs["params"]
    assert params["amount"] == 55000 and params["currency"] == "mxn"
    assert params["capture_method"] == "manual" and params["transfer_group"] == "ABC123"
    assert params["automatic_payment_methods"] == {"enabled": True}  # cards + Apple Pay + Google Pay
    assert create.call_args.kwargs["options"]["idempotency_key"] == "checkout-b1"
    assert checkout.client_secret == "pi_1_secret" and checkout.ephemeral_key == "ek_1"


def test_transfer_uses_source_charge_and_idempotency(gateway):
    with mock.patch.object(gateway.client.v1.transfers, "create", return_value=SimpleNamespace(id="tr_1")) as create:
        gateway.transfer(amount_cents=45500, destination="acct_1", source_charge="ch_1", group="ABC123", idempotency_key="transfer-1")
    params = create.call_args.kwargs["params"]
    assert params == {"amount": 45500, "currency": "mxn", "destination": "acct_1", "source_transaction": "ch_1",
                      "transfer_group": "ABC123"}


def test_connected_account_configuration(gateway):
    provider = SimpleNamespace(pk="p1", user=SimpleNamespace(email="p@example.com"))
    with mock.patch.object(gateway.client.v1.accounts, "create", return_value=SimpleNamespace(id="acct_1")) as create, \
         mock.patch.object(gateway.client.v1.account_links, "create", return_value=SimpleNamespace(url="https://connect")):
        account_id, url = gateway.onboard_provider(provider=provider, existing_account_id=None, return_url="r", refresh_url="f")
    params = create.call_args.kwargs["params"]
    assert params["country"] == "MX" and params["controller"]["fees"]["payer"] == "application"
    assert params["settings"]["payouts"]["schedule"]["interval"] == "weekly"
    assert (account_id, url) == ("acct_1", "https://connect")


def test_stripe_errors_become_gateway_errors(gateway):
    import stripe

    from apps.payments.gateways.base import GatewayError

    with mock.patch.object(gateway.client.v1.refunds, "create", side_effect=stripe.InvalidRequestError("nope", None)), \
         pytest.raises(GatewayError):
        gateway.refund(payment_external_id="pi_1", amount_cents=100, idempotency_key="k", reason="x")


def test_transfer_without_source_charge_uses_platform_balance(gateway):
    with mock.patch.object(gateway.client.v1.transfers, "create", return_value=SimpleNamespace(id="tr_2")) as create:
        gateway.transfer(amount_cents=45500, destination="acct_1", source_charge="", group="ABC123", idempotency_key="transfer-2")
    assert "source_transaction" not in create.call_args.kwargs["params"]
