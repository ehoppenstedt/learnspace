from django.conf import settings
from django.core import signing
from django.db.models import Prefetch
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.booking import services
from apps.booking.models import Booking, BookingSession
from apps.booking.serializers import (
    AttendanceSerializer,
    BookingCreateSerializer,
    BookingSerializer,
    CancelSerializer,
    HoldCreateSerializer,
    ProviderBookingSerializer,
    RosterSerializer,
)
from apps.catalog.models import Session
from apps.core.permissions import IsProfileComplete, IsProvider
from apps.payments.models import Payment

ICS_SALT = "booking-ics"


class HoldsView(APIView):
    permission_classes = [IsAuthenticated, IsProfileComplete]

    def post(self, request):
        data = HoldCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        from apps.core.platform import payment_channel

        result = services.create_hold(request.user, seats=data.validated_data["seats"],
                                      session_id=data.validated_data.get("session_id"),
                                      cohort_id=data.validated_data.get("cohort_id"),
                                      channel_for=lambda experience, capacity, seats: payment_channel(request, experience, capacity, seats))
        return Response({
            "hold_id": result.hold.id, "expires_at": result.hold.expires_at, "seats": result.hold.seats,
            "price": {"listed_cents": result.listed_cents, "fee_cents": result.fee_cents, "total_cents": result.total_cents,
                      "store_surcharge_cents": result.store_surcharge_cents, "currency": "MXN"},
            "channel": result.hold.channel,
            "credit_available_cents": result.credit_available_cents,
        }, status=status.HTTP_201_CREATED)


class HoldDetailView(APIView):
    def delete(self, request, pk):
        services.release_hold(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _bookings_qs():
    return Booking.objects.select_related("experience__space", "experience__provider", "experience__category").prefetch_related(
        Prefetch("payments", queryset=Payment.objects.prefetch_related("refunds")),
        "experience__experiencemedia_set__media",
    )


class BookingsView(APIView):
    permission_classes = [IsAuthenticated, IsProfileComplete]

    def get(self, request):
        scope = request.query_params.get("scope", "upcoming")
        qs = _bookings_qs().filter(learner=request.user)
        now = timezone.now()
        if scope == "upcoming":
            qs = qs.filter(ends_at__gt=now, status__in=["confirmed", "pending_approval"]).order_by("starts_at")
        else:
            qs = qs.filter(status__in=["completed", "no_show", "cancelled", "declined", "confirmed"]).exclude(
                status="confirmed", ends_at__gt=now).order_by("-starts_at")
        return Response(BookingSerializer(qs[:100], many=True).data)

    def post(self, request):
        data = BookingCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        booking, checkout = services.start_checkout(request.user, data.validated_data["hold_id"],
                                                    use_credits=data.validated_data.get("use_credits", True))
        payment_sheet = app_store = None
        from apps.payments.services import StoreCheckout

        if isinstance(checkout, StoreCheckout):
            app_store = {"product_id": checkout.product_id, "amount_cents": checkout.amount_cents,
                         "app_account_token": checkout.app_account_token, "test_mode": settings.APP_STORE_GATEWAY == "fake"}
        elif checkout:
            payment_sheet = {
                "payment_intent_client_secret": checkout.client_secret, "customer_id": checkout.customer_id,
                "customer_ephemeral_key": checkout.ephemeral_key, "publishable_key": checkout.publishable_key,
                "gateway": booking.payments.order_by("-created_at").values_list("gateway", flat=True).first(),
            }
        payment = booking.payments.order_by("-created_at").first()
        credit_used = sum(p.amount_cents for p in booking.payments.all() if p.gateway == "credit" and p.status == "succeeded")
        return Response({"booking": BookingSerializer(booking).data, "payment_sheet": payment_sheet, "app_store": app_store,
                         "credit_applied_cents": credit_used,
                         "requires_approval": bool(payment and payment.capture_manual)},
                        status=status.HTTP_201_CREATED)


class BookingDetailView(APIView):
    def get(self, request, pk):
        booking = get_object_or_404(_bookings_qs(), pk=pk, learner=request.user)
        data = BookingSerializer(booking).data
        data["calendar_url"] = request.build_absolute_uri(f"/api/v1/calendar/{signing.dumps(str(booking.pk), salt=ICS_SALT)}.ics")
        return Response(data)


class CancellationQuoteView(APIView):
    def get(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, learner=request.user)
        return Response(services.quote_as_dict(services.quote_cancellation(booking)))


class CancelView(APIView):
    def post(self, request, pk):
        data = CancelSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        cancellation = services.cancel_by_learner(request.user, pk, data.validated_data["quote_token"])
        return Response({"status": "cancelled", "refund_cents": cancellation.refund_cents,
                         "listed_refund_cents": cancellation.listed_refund_cents, "fee_refund_cents": cancellation.fee_refund_cents})


class DisputeNoShowView(APIView):
    def post(self, request, pk):
        report = services.dispute_no_show(request.user, pk, str(request.data.get("details", "")))
        return Response({"report_id": report.pk}, status=status.HTTP_201_CREATED)


class CalendarView(APIView):
    """Signed, unauthenticated URL so calendar apps can open the file directly."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, token):
        try:
            booking_id = signing.loads(token, salt=ICS_SALT, max_age=60 * 60 * 24 * 365)
        except signing.BadSignature:
            raise Http404
        booking = get_object_or_404(Booking, pk=booking_id, status__in=["confirmed", "completed"])
        response = HttpResponse(services.booking_ics(booking), content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{booking.code}.ics"'
        return response


# ---------------------------------------------------------------------------
# Provider side
# ---------------------------------------------------------------------------


class ProviderView(APIView):
    permission_classes = [IsAuthenticated, IsProvider]


class RosterView(ProviderView):
    def get(self, request, pk):
        session = get_object_or_404(Session, pk=pk, experience__provider_id=request.user.pk)
        rows = (BookingSession.objects.filter(session=session, booking__status__in=["confirmed", "completed", "no_show", "pending_approval"])
                .select_related("booking__learner__learner_profile").order_by("booking__created_at"))
        return Response({
            "session": {"id": str(session.pk), "starts_at": session.starts_at, "ends_at": session.ends_at,
                        "capacity": session.capacity, "seats_booked": session.seats_booked, "status": session.status},
            "attendees": RosterSerializer(rows, many=True).data,
        })


class AttendanceView(ProviderView):
    def post(self, request, pk):
        data = AttendanceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        updated = services.mark_attendance(request.user, pk, data.validated_data["marks"])
        return Response({"updated": len(updated)})


class ProviderCancelSessionView(ProviderView):
    def post(self, request, pk):
        count = services.cancel_by_provider(request.user, session_id=pk, reason=str(request.data.get("reason", ""))[:500])
        return Response({"cancelled_bookings": count})


class ProviderCancelCohortView(ProviderView):
    def post(self, request, pk):
        count = services.cancel_by_provider(request.user, cohort_id=pk, reason=str(request.data.get("reason", ""))[:500])
        return Response({"cancelled_bookings": count})


class ProviderBookingsView(ProviderView):
    def get(self, request):
        qs = Booking.objects.filter(experience__provider_id=request.user.pk).select_related(
            "learner__learner_profile", "experience").order_by("starts_at")
        if status_filter := request.query_params.get("status"):
            qs = qs.filter(status__in=status_filter.split(","))
        else:
            qs = qs.filter(starts_at__gte=timezone.now())
        return Response(ProviderBookingSerializer(qs[:200], many=True).data)


class ProviderBookingDecisionView(ProviderView):
    def post(self, request, pk, decision):
        if decision == "approve":
            booking = services.approve(request.user, pk)
        elif decision == "decline":
            booking = services.decline(pk, provider_user=request.user)
        else:
            raise Http404
        return Response(ProviderBookingSerializer(booking).data)
