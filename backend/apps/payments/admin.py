from django.contrib import admin

from apps.moderation.admin import AuditedAdminMixin
from apps.payments.models import FeeConfig


@admin.register(FeeConfig)
class FeeConfigAdmin(AuditedAdminMixin, admin.ModelAdmin):
    """Fee rows are immutable: change the fee by adding a row with a future effective date."""

    list_display = ("fee_pct", "effective_from", "note", "created_by")
    fields = ("fee_bps", "effective_from", "note")

    @admin.display(description="Fee %")
    def fee_pct(self, obj):
        return f"{obj.fee_bps / 100:.2f}%"

    def has_change_permission(self, request, obj=None):
        return obj is None and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        super().save_model(request, obj, form, change)
