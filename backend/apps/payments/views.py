import re

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.booking.models import Booking
from apps.core.exceptions import DomainError
from apps.core.permissions import IsProvider
from apps.payments import services
from apps.payments.gateways import get_gateway
from apps.payments.gateways.base import GatewayError, InvalidSignature
from apps.payments.models import RFC_PATTERN, Payment, PaymentAccount, PaymentCustomer, ProviderTaxProfile, Transfer


@csrf_exempt
def webhook(request, gateway):
    """Verify signature -> store once (unique event id) -> process in a job -> 200 fast."""
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        gw = get_gateway(gateway)
    except (ValueError, GatewayError):
        raise Http404
    if gw.name != settings.PAYMENT_GATEWAY:
        raise Http404
    try:
        event = gw.verify_and_parse_webhook(request.headers, request.body)
    except (InvalidSignature, ValueError):
        return HttpResponse(status=400)
    if event.kind == "ignored":
        return HttpResponse(status=200)
    with transaction.atomic():
        record, created = services.record_webhook(gw.name, event)
        if created:
            from apps.payments.tasks import process_webhook_task

            transaction.on_commit(lambda: process_webhook_task.defer(webhook_id=str(record.pk)))
    return HttpResponse(status=200)


class PaymentMethodsView(APIView):
    def get(self, request):
        record = PaymentCustomer.objects.filter(user=request.user, gateway=get_gateway().name).first()
        if record is None:
            return Response([])
        try:
            return Response(get_gateway().list_payment_methods(record.external_id))
        except GatewayError:
            raise DomainError("payments_unavailable", _("No pudimos consultar tus métodos de pago."), status.HTTP_502_BAD_GATEWAY)


class PaymentMethodDetailView(APIView):
    def delete(self, request, pm_id):
        record = get_object_or_404(PaymentCustomer, user=request.user, gateway=get_gateway().name)
        try:
            get_gateway().detach_payment_method(record.external_id, pm_id)
        except GatewayError:
            raise DomainError("not_found", _("Método de pago no encontrado."), status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Provider: onboarding, tax profile, earnings
# ---------------------------------------------------------------------------


class ProviderView(APIView):
    permission_classes = [IsAuthenticated, IsProvider]

    def provider(self):
        from apps.accounts.models import ProviderProfile

        return ProviderProfile.objects.get(pk=self.request.user.pk)  # fresh: status changes out of band


def _onboarding_status(provider) -> dict:
    account = PaymentAccount.objects.filter(provider=provider).first()
    ready, missing = services.provider_ready_for_payouts(provider)
    tax = ProviderTaxProfile.objects.filter(provider=provider).first()
    return {
        "ready_to_publish": ready,
        "missing": missing,
        "identity_status": provider.verification_status,
        "payment_account": {"kyc_status": account.kyc_status, "payouts_enabled": account.payouts_enabled,
                            "requirements_due": account.requirements_due} if account else None,
        "tax_profile": {"person_type": tax.person_type, "rfc": tax.rfc, "legal_name": tax.legal_name,
                        "validated": bool(tax.validated_at)} if tax else None,
    }


class OnboardingView(ProviderView):
    def get(self, request):
        provider = self.provider()
        account = PaymentAccount.objects.filter(provider=provider).first()
        if account and not account.payouts_enabled and request.query_params.get("refresh"):
            try:
                services.sync_account(account.external_id)
            except GatewayError:
                pass
        return Response(_onboarding_status(provider))

    def post(self, request):
        return Response({"url": services.start_onboarding(self.provider())})


class TaxProfileSerializer(serializers.ModelSerializer):
    rfc = serializers.CharField(max_length=13)

    class Meta:
        model = ProviderTaxProfile
        fields = ["person_type", "rfc", "legal_name", "tax_regime", "postal_code"]

    def validate_rfc(self, value):
        value = value.upper().strip()
        if not re.fullmatch(RFC_PATTERN, value):
            raise serializers.ValidationError(_("RFC inválido."))
        expected = 12 if self.initial_data.get("person_type") == "moral" else 13
        if len(value) != expected:
            raise serializers.ValidationError(_("El RFC debe tener %(n)s caracteres.") % {"n": expected})
        return value

    def validate_postal_code(self, value):
        if value and not re.fullmatch(r"\d{5}", value):
            raise serializers.ValidationError(_("Código postal inválido."))
        return value


class TaxProfileView(ProviderView):
    def get(self, request):
        tax = ProviderTaxProfile.objects.filter(provider=self.provider()).first()
        return Response(TaxProfileSerializer(tax).data if tax else None)

    def put(self, request):
        provider = self.provider()
        instance = ProviderTaxProfile.objects.filter(provider=provider).first()
        serializer = TaxProfileSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        changed = instance is None or instance.rfc != serializer.validated_data["rfc"]
        tax = serializer.save(provider=provider, **({"validated_at": None} if changed else {}))
        return Response(TaxProfileSerializer(tax).data)


class EarningsView(ProviderView):
    def get(self, request):
        provider = self.provider()
        transfers = Transfer.objects.filter(provider=provider).select_related("booking__experience").order_by("-release_at")
        totals = {s: transfers.filter(status=s).aggregate(n=Sum("net_cents"))["n"] or 0
                  for s in ("scheduled", "on_hold", "sent")}
        from apps.payments.models import WithholdingConfig

        return Response({
            "withholding_configured": WithholdingConfig.objects.filter(isr_bps__gt=0).exists(),
            "test_mode": settings.PAYMENTS_TEST_MODE,
            "totals": {"upcoming_cents": totals["scheduled"], "on_hold_cents": totals["on_hold"], "paid_cents": totals["sent"]},
            "transfers": [
                {"id": str(t.pk), "booking_code": t.booking.code, "experience": t.booking.experience.title,
                 "gross_cents": t.gross_cents, "isr_withheld_cents": t.isr_withheld_cents, "iva_withheld_cents": t.iva_withheld_cents,
                 "net_cents": t.net_cents, "status": t.status, "release_at": t.release_at, "sent_at": t.sent_at,
                 "hold_reason": t.hold_reason}
                for t in transfers[:200]
            ],
        })


# ---------------------------------------------------------------------------
# Development only: drive the fake gateway like a processor would.
# ---------------------------------------------------------------------------


def _dev_only():
    """Test-mode tools (simulated payment, simulated KYC). Never available with a real gateway."""
    if not settings.PAYMENTS_TEST_MODE or settings.APP_ENV == "production":
        raise Http404


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def dev_simulate_payment(request, booking_id):
    """outcome: succeeded | authorized | failed. Posts a signed webhook through the real endpoint path."""
    _dev_only()
    from apps.payments.gateways.fake import FakeGateway

    booking = get_object_or_404(Booking, pk=booking_id, learner=request.user)
    payment = get_object_or_404(Payment, booking=booking, gateway="fake")
    outcome = request.data.get("outcome", "authorized" if payment.capture_manual else "succeeded")
    kind = {"succeeded": "payment_succeeded", "authorized": "payment_authorized", "failed": "payment_failed"}[outcome]
    body = FakeGateway.build_event(kind, payment.external_id, charge_id=f"ch_fake_{payment.pk.hex[:12]}", method="card")
    _deliver_fake(body)
    return Response({"delivered": kind})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def dev_complete_onboarding(request, account_id):
    _dev_only()
    from apps.payments.gateways.fake import FakeGateway

    _deliver_fake(FakeGateway.build_event("account_updated", account_id, charges_enabled=True, payouts_enabled=True, requirements_due=[]))
    return Response({"delivered": "account_updated"})


def _deliver_fake(body: bytes):
    from django.test import RequestFactory

    from apps.payments.gateways.fake import SIGNATURE_HEADER, FakeGateway
    from apps.payments.models import WebhookEvent
    from apps.payments.services import process_webhook

    request = RequestFactory().post("/", data=body, content_type="application/json",
                                    headers={SIGNATURE_HEADER: FakeGateway.sign(body)})
    webhook(request, "fake")
    # Local dev may run without a worker: process inline so the app reflects it immediately.
    for record in WebhookEvent.objects.filter(processed_at__isnull=True, gateway="fake"):
        process_webhook(record.pk)


# ---------------------------------------------------------------------------
# Receipts and statements (dummy backend today, PAC later). Signed links so they open
# in a browser or share sheet without the app's token.
# ---------------------------------------------------------------------------

RECEIPT_SALT = "receipt"


class BookingReceiptLinkView(APIView):
    def get(self, request, pk):
        from django.core import signing

        booking = get_object_or_404(Booking, pk=pk, learner=request.user)
        token = signing.dumps({"k": "booking", "id": str(booking.pk)}, salt=RECEIPT_SALT)
        return Response({"url": request.build_absolute_uri(f"/api/v1/receipts/{token}")})


class StatementLinkView(ProviderView):
    def get(self, request):
        from django.core import signing
        from django.utils import timezone

        month = request.query_params.get("month") or timezone.localdate().strftime("%Y-%m")
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            raise DomainError("invalid_month", _("Mes inválido."), status.HTTP_400_BAD_REQUEST)
        token = signing.dumps({"k": "statement", "id": str(self.provider().pk), "m": month}, salt=RECEIPT_SALT)
        return Response({"url": request.build_absolute_uri(f"/api/v1/receipts/{token}"), "month": month})


def receipt_document(request, token):
    from datetime import date

    from django.core import signing

    from apps.accounts.models import ProviderProfile
    from apps.payments.receipts import get_receipt_backend

    try:
        data = signing.loads(token, salt=RECEIPT_SALT, max_age=60 * 60 * 24 * 7)
    except signing.BadSignature:
        raise Http404
    backend = get_receipt_backend()
    if data["k"] == "booking":
        content_type, body = backend.booking_receipt(get_object_or_404(Booking, pk=data["id"]))
    else:
        year, month = (int(x) for x in data["m"].split("-"))
        content_type, body = backend.provider_statement(get_object_or_404(ProviderProfile, pk=data["id"]), date(year, month, 1))
    response = HttpResponse(body, content_type=content_type)
    response["X-Robots-Tag"] = "noindex"
    return response


# ---------------------------------------------------------------------------
# App Store In-App Purchase and credits
# ---------------------------------------------------------------------------


class StoreTransactionView(APIView):
    """The iOS app sends the StoreKit 2 signed transaction right after the purchase."""

    def post(self, request, pk):
        from apps.payments import appstore

        if settings.APP_STORE_GATEWAY != "apple":
            raise DomainError("store_test_mode", _("La App Store está en modo de prueba."), status.HTTP_409_CONFLICT)
        token = str(request.data.get("signed_transaction", ""))
        try:
            txn = appstore.verify_transaction(token)
        except appstore.InvalidStoreSignature:
            raise DomainError("store_transaction_invalid", _("No pudimos validar la compra con Apple."), status.HTTP_400_BAD_REQUEST)
        appstore.complete_purchase(request.user, pk, txn)
        booking = get_object_or_404(Booking, pk=pk, learner=request.user)
        return Response({"booking_id": str(booking.pk), "status": booking.status})


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def app_store_notification(request):
    """App Store Server Notifications V2 (configure this URL in App Store Connect)."""
    from apps.payments import appstore

    try:
        kind = appstore.handle_notification(str(request.data.get("signedPayload", "")))
    except (appstore.InvalidStoreSignature, KeyError):
        return Response({"error": "invalid"}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"received": kind})


class CreditsView(APIView):
    def get(self, request):
        from apps.payments import credits
        from apps.payments.models import CreditEntry

        entries = CreditEntry.objects.filter(user=request.user).select_related("booking__experience").order_by("-created_at")[:50]
        return Response({
            "balance_cents": credits.balance(request.user),
            "entries": [{"id": str(e.pk), "amount_cents": e.amount_cents, "kind": e.kind, "date": e.created_at,
                         "experience": e.booking.experience.title if e.booking_id else None} for e in entries],
        })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def dev_simulate_store_purchase(request, booking_id):
    """Test mode: what the App Store sheet does, without Apple. outcome: succeeded | cancelled."""
    from apps.payments import appstore
    from apps.payments.pricing import product_id_for

    if settings.APP_STORE_GATEWAY != "fake" or settings.APP_ENV == "production":
        raise Http404
    payment = get_object_or_404(Payment, booking_id=booking_id, booking__learner=request.user, gateway="app_store")
    if request.data.get("outcome", "succeeded") == "cancelled":
        return Response({"status": "cancelled"})
    txn = appstore.StoreTransaction(
        transaction_id=f"test-{payment.pk.hex[:16]}", original_transaction_id=f"test-{payment.pk.hex[:16]}",
        product_id=product_id_for(payment.amount_cents // 100), app_account_token=str(booking_id),
        bundle_id=settings.APPLE_BUNDLE_ID, environment="Sandbox", price_milli=payment.amount_cents * 10, currency="MXN")
    appstore.complete_purchase(request.user, booking_id, txn)
    return Response({"status": "succeeded"})
