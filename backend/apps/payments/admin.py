from django.contrib import admin

from apps.moderation.admin import AuditedAdminMixin
from apps.payments.models import FeeConfig, Payment, PaymentAccount, ProviderTaxProfile, WebhookEvent, WithholdingConfig


class ImmutableConfigAdmin(AuditedAdminMixin, admin.ModelAdmin):
    """Config rows are immutable: changes are new rows with a future effective date."""

    def has_change_permission(self, request, obj=None):
        return obj is None and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FeeConfig)
class FeeConfigAdmin(ImmutableConfigAdmin):
    list_display = ("fee_pct", "effective_from", "note", "created_by")
    fields = ("fee_bps", "effective_from", "note")

    @admin.display(description="Fee %")
    def fee_pct(self, obj):
        return f"{obj.fee_bps / 100:.2f}%"

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(WithholdingConfig)
class WithholdingConfigAdmin(ImmutableConfigAdmin):
    list_display = ("isr_bps", "iva_bps", "effective_from", "note")
    fields = ("isr_bps", "iva_bps", "effective_from", "note")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "booking", "gateway", "status", "amount_cents", "refunded_cents", "method")
    list_filter = ("status", "gateway")
    search_fields = ("external_id", "booking__code")
    readonly_fields = [f.name for f in Payment._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(PaymentAccount)
class PaymentAccountAdmin(admin.ModelAdmin):
    list_display = ("provider", "gateway", "kyc_status", "payouts_enabled", "external_id")
    list_filter = ("kyc_status", "payouts_enabled")
    readonly_fields = [f.name for f in PaymentAccount._meta.fields]


@admin.register(ProviderTaxProfile)
class ProviderTaxProfileAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("provider", "person_type", "rfc", "legal_name", "validated_at")
    list_filter = ("person_type",)
    search_fields = ("rfc", "legal_name")
    readonly_fields = ("provider", "updated_at")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "gateway", "type", "event_id", "processed_at", "attempts")
    list_filter = ("gateway", "type")
    readonly_fields = [f.name for f in WebhookEvent._meta.fields]

    def has_add_permission(self, request):
        return False
