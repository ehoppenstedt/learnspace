from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from apps.catalog.models import Area, CancellationPolicy, CancellationRule, Category, Experience, MediaAsset, Session, Space
from apps.catalog.policies import RuleSpec, validate_rules
from apps.moderation.admin import AuditedAdminMixin


@admin.register(Category)
class CategoryAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("slug", "name_es", "name_en", "icon", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name", "borough", "city")
    search_fields = ("name", "borough")


class RuleFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        specs = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            d = form.cleaned_data
            specs.append(RuleSpec(d["applies_to"], d["min_hours_before"], d.get("max_hours_before"),
                                  d["listed_refund_pct"], d.get("refund_fee", False)))
        errors = validate_rules(specs)
        if errors:
            raise ValidationError(errors)


class RuleInline(admin.TabularInline):
    model = CancellationRule
    formset = RuleFormSet
    extra = 0


@admin.register(CancellationPolicy)
class CancellationPolicyAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name_es", "is_active", "is_default")
    inlines = [RuleInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        from apps.moderation import services

        services.log(request.user, "config.policy_rules", form.instance, after={
            "rules": [str(r) for r in form.instance.rules.all()]
        })


class SessionInline(admin.TabularInline):
    model = Session
    fields = ("starts_at", "ends_at", "capacity", "seats_booked", "status", "cohort")
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    """Read-only view. State changes happen through the review queue."""

    list_display = ("title", "provider", "category", "status", "listed_price_cents", "next_session_at")
    list_filter = ("status", "category", "modality", "offering_type")
    search_fields = ("title", "provider__display_name")
    readonly_fields = [f.name for f in Experience._meta.fields if f.name not in ("online_url",)]
    exclude = ("online_url", "media")
    inlines = [SessionInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False  # view permission only: renders read-only

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Space)
class SpaceAdmin(admin.ModelAdmin):
    list_display = ("name", "neighborhood", "owner", "owner_role", "verification_status")
    list_filter = ("verification_status", "owner_role")
    search_fields = ("name", "neighborhood")
    exclude = ("address_line", "address_reference")
    readonly_fields = ("owner", "point_exact", "point_public", "area")


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "kind", "status", "rejection_reason", "created_at")
    list_filter = ("kind", "status")
    readonly_fields = [f.name for f in MediaAsset._meta.fields]

    def has_add_permission(self, request):
        return False
