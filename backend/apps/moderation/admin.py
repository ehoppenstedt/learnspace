from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.catalog import media as media_service
from apps.catalog.models import CancellationPolicy, Category, ExperienceRevision, MediaAsset, Space
from apps.catalog.services import snapshot
from apps.core.exceptions import DomainError
from apps.moderation import services
from apps.moderation.models import AdminAction, ReasonCode, Report
from apps.payments.pricing import current_fee_bps, price


class AuditedAdminMixin:
    """Logs every create/update/delete done through a ModelAdmin form."""

    audit_exclude: tuple = ()

    def save_model(self, request, obj, form, change):
        before = {}
        if change:
            before = services.snapshot_model(type(obj).objects.get(pk=obj.pk), exclude=self.audit_exclude)
        super().save_model(request, obj, form, change)
        services.log(request.user, "config.update" if change else "config.create", obj, before=before,
                     after=services.snapshot_model(obj, exclude=self.audit_exclude))

    def delete_model(self, request, obj):
        services.log(request.user, "config.delete", obj, before=services.snapshot_model(obj, exclude=self.audit_exclude))
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request, obj)


class DecisionForm(forms.Form):
    DECISIONS = [("approve", "Approve"), ("request_changes", "Request changes"), ("reject", "Reject")]
    decision = forms.ChoiceField(choices=DECISIONS, widget=forms.RadioSelect)
    reason_code = forms.ChoiceField(choices=[("", "—")] + [c for c in ReasonCode.choices if c[0] != ReasonCode.APPROVED], required=False)
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), required=False,
                           help_text="Shown to the provider. Required unless approving.")


FIELD_LABELS = [
    ("title", "Title"), ("what_you_learn", "What you'll learn"), ("who_its_for", "Who it's for"),
    ("category_id", "Category"), ("instruction_language", "Language"), ("modality", "Modality"),
    ("offering_type", "Offering type"), ("listed_price_cents", "Listed price"), ("space_id", "Space"),
    ("online_url", "Online link"), ("cancellation_policy_id", "Cancellation policy"), ("media_ids", "Media"),
]


def _display(field: str, value):
    if value in (None, ""):
        return "—"
    if field == "category_id":
        return Category.objects.filter(pk=value).values_list("name_es", flat=True).first() or value
    if field == "space_id":
        space = Space.objects.filter(pk=value).first()
        return f"{space.name} — {space.neighborhood} ({space.address_line})" if space else value
    if field == "listed_price_cents":
        return f"${value / 100:,.2f} MXN"
    if field == "cancellation_policy_id":
        return CancellationPolicy.objects.filter(pk=value).values_list("name_es", flat=True).first() or value
    if field == "media_ids":
        return f"{len(value)} files"
    return value


@admin.register(ExperienceRevision)
class ReviewQueueAdmin(admin.ModelAdmin):
    """Review queue. Default view: pending submissions, oldest first."""

    list_display = ("experience", "kind", "number", "review_status", "provider", "provider_verified", "submitted_at")
    list_filter = ("review_status", "kind")
    search_fields = ("experience__title", "experience__provider__display_name")
    ordering = ("submitted_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("experience__provider")

    def changelist_view(self, request, extra_context=None):
        if "review_status__exact" not in request.GET and not request.GET.get("q"):
            return redirect(f"{request.path}?review_status__exact=pending")
        return super().changelist_view(request, extra_context)

    @admin.display(description="Provider")
    def provider(self, obj):
        return obj.experience.provider

    @admin.display(boolean=True, description="ID verified")
    def provider_verified(self, obj):
        return obj.experience.provider.is_verified

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        revision = self.get_object(request, object_id)
        if revision is None or revision.review_status != ExperienceRevision.ReviewStatus.PENDING:
            return super().change_view(request, object_id, form_url, extra_context)
        experience = revision.experience
        form = DecisionForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            try:
                if data["decision"] == "approve":
                    services.approve(request.user, revision, note=data["note"])
                elif data["decision"] == "request_changes":
                    services.request_changes(request.user, revision, data["reason_code"], data["note"])
                else:
                    services.reject(request.user, revision, data["reason_code"], data["note"])
            except DomainError as exc:
                messages.error(request, str(exc.detail))
            else:
                messages.success(request, f"Decision recorded: {data['decision']}")
                return redirect(reverse("admin:catalog_experiencerevision_changelist"))
        live = snapshot(experience)
        rows = [
            {"field": label, "live": _display(key, live.get(key)), "proposed": _display(key, revision.payload.get(key)),
             "changed": live.get(key) != revision.payload.get(key)}
            for key, label in FIELD_LABELS
        ]
        media_urls = []
        for asset in MediaAsset.objects.filter(pk__in=revision.payload.get("media_ids") or []):
            data = media_service.public_media(asset)
            if data and data.get("urls"):
                media_urls.append(data["urls"]["w400"])
            elif data and data.get("poster_url"):
                media_urls.append(data["poster_url"])
        breakdown = price(revision.payload.get("listed_price_cents") or 0, current_fee_bps())
        context = {
            **self.admin_site.each_context(request),
            "title": f"Review {experience.title}",
            "revision": revision,
            "experience": experience,
            "provider": experience.provider,
            "rows": rows,
            "media_urls": media_urls,
            "sessions": experience.sessions.order_by("starts_at")[:30],
            "price_total": f"{breakdown.total_cents / 100:,.2f}",
            "price_listed": f"{breakdown.listed_cents / 100:,.2f}",
            "price_fee": f"{breakdown.fee_cents / 100:,.2f}",
            "form": form,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/moderation/review_decision.html", context)


@admin.register(AdminAction)
class AdminActionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "admin", "action", "target_type", "target_id", "reason_code")
    list_filter = ("action", "target_type")
    search_fields = ("target_id", "admin__email", "note")
    readonly_fields = [f.name for f in AdminAction._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("created_at", "target_type", "target_id", "reason_code", "status", "reporter")
    list_filter = ("status", "target_type", "reason_code")

