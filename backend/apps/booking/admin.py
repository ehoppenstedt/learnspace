from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.booking.models import Booking, BookingSession, Cancellation, SeatHold
from apps.core.exceptions import DomainError
from apps.moderation import services as audit
from apps.payments.models import Payment, Refund, Transfer


class BookingSessionInline(admin.TabularInline):
    model = BookingSession
    fields = ("session", "attendance", "marked_by", "marked_at")
    readonly_fields = fields
    extra = 0
    can_delete = False


class CancellationInline(admin.TabularInline):
    model = Cancellation
    fields = ("cancelled_at", "actor_role", "actor", "hours_before_start", "listed_refund_cents", "fee_refund_cents", "refund_cents", "reason_code")
    readonly_fields = fields
    extra = 0
    can_delete = False


class PaymentInline(admin.TabularInline):
    model = Payment
    fields = ("gateway", "external_id", "status", "amount_cents", "refunded_cents", "method", "capture_manual")
    readonly_fields = fields
    extra = 0
    can_delete = False


class AdminRefundForm(forms.Form):
    listed_refund_pesos = forms.DecimalField(min_value=0, decimal_places=2, label="Refund of listed price (MXN)")
    refund_fee = forms.BooleanField(required=False, label="Also refund the service fee")
    reason_code = forms.ChoiceField(choices=[("admin_goodwill", "Goodwill"), ("dispute_resolution", "Dispute resolution"),
                                             ("provider_fault", "Provider fault"), ("duplicate_charge", "Duplicate charge")])
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("code", "experience", "learner", "status", "seats", "total_cents", "starts_at", "created_at")
    list_filter = ("status",)
    search_fields = ("code", "learner__email", "experience__title")
    readonly_fields = [f.name for f in Booking._meta.fields]
    inlines = [BookingSessionInline, PaymentInline, CancellationInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        return [path("<uuid:pk>/refund/", self.admin_site.admin_view(self.refund_view), name="booking_booking_refund")] + super().get_urls()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), "refund_url": reverse("admin:booking_booking_refund", args=[object_id])}
        return super().change_view(request, object_id, form_url, extra_context)

    def refund_view(self, request, pk):
        """Admin refund/dispute tool: any amount up to what remains, always audited."""
        from apps.payments import services as payments

        booking = Booking.objects.get(pk=pk)
        payment = booking.payments.exclude(status__in=["requires_payment", "failed", "canceled", "authorized"]).order_by("-created_at").first()
        form = AdminRefundForm(request.POST or None)
        if request.method == "POST" and form.is_valid() and payment:
            listed = int(form.cleaned_data["listed_refund_pesos"] * 100)
            fee = booking.fee_cents if form.cleaned_data["refund_fee"] else 0
            already_fee = sum(r.fee_refund_cents for r in payment.refunds.all())
            fee = max(fee - already_fee, 0)
            try:
                if listed + fee <= 0:
                    raise DomainError("nothing_to_refund", "Nothing to refund.")
                if listed > booking.listed_cents - payments.listed_refunded(booking):
                    raise DomainError("too_much", "Exceeds the listed price still unrefunded.")
                with transaction.atomic():
                    refund = payments.refund_payment(payment, listed_cents=listed, fee_cents=fee,
                                                     reason=form.cleaned_data["reason_code"], created_by=request.user)
                    audit.log(request.user, "booking.refund", booking, reason_code=form.cleaned_data["reason_code"],
                              note=form.cleaned_data["note"], after={"refund_id": str(refund.pk), "listed": listed, "fee": fee})
            except DomainError as exc:
                messages.error(request, str(exc.detail))
            else:
                messages.success(request, f"Refund of ${(listed + fee) / 100:,.2f} queued.")
                return redirect(reverse("admin:booking_booking_change", args=[pk]))
        context = {**self.admin_site.each_context(request), "title": f"Refund {booking.code}", "booking": booking,
                   "payment": payment, "form": form, "opts": self.model._meta,
                   "remaining_listed": booking.listed_cents - payments.listed_refunded(booking)}
        return TemplateResponse(request, "admin/booking/refund.html", context)


@admin.register(SeatHold)
class SeatHoldAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "experience", "seats", "status", "expires_at")
    list_filter = ("status",)
    readonly_fields = [f.name for f in SeatHold._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    """Failed refunds land here for follow-up."""

    list_display = ("created_at", "payment", "total_refund_cents", "reason", "status", "external_id")
    list_filter = ("status", "reason")
    readonly_fields = [f.name for f in Refund._meta.fields]
    actions = ["retry"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Retry failed refunds")
    def retry(self, request, queryset):
        from apps.payments.tasks import execute_refund_task

        for refund in queryset.filter(status=Refund.Status.FAILED):
            Refund.objects.filter(pk=refund.pk).update(status=Refund.Status.PENDING)
            execute_refund_task.defer(refund_id=str(refund.pk))
            audit.log(request.user, "refund.retry", refund)


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = ("booking", "provider", "gross_cents", "net_cents", "status", "hold_reason", "release_at", "sent_at")
    list_filter = ("status", "hold_reason")
    readonly_fields = [f.name for f in Transfer._meta.fields]
    actions = ["hold", "release"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Put on hold (dispute)")
    def hold(self, request, queryset):
        for t in queryset.filter(status=Transfer.Status.SCHEDULED):
            Transfer.objects.filter(pk=t.pk).update(status=Transfer.Status.ON_HOLD, hold_reason="admin_hold")
            audit.log(request.user, "transfer.hold", t)

    @admin.action(description="Release hold (schedule again)")
    def release(self, request, queryset):
        for t in queryset.filter(status=Transfer.Status.ON_HOLD):
            Transfer.objects.filter(pk=t.pk).update(status=Transfer.Status.SCHEDULED, hold_reason="")
            audit.log(request.user, "transfer.release", t)
