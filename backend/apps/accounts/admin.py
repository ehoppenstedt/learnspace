from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html

from apps.accounts.models import ConsentRecord, ProviderProfile, ProviderVerification, User
from apps.catalog.storage import get_storage
from apps.core.exceptions import DomainError
from apps.moderation import services
from apps.moderation.models import ReasonCode


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "phone_e164", "first_name", "last_name", "status", "is_staff", "date_joined")
    list_filter = ("status", "is_staff", "phone_verified")
    search_fields = ("email", "phone_e164", "first_name", "last_name")
    fields = ("email", "email_verified", "phone_e164", "phone_verified", "first_name", "last_name",
              "date_of_birth", "ui_language", "status", "is_active", "is_staff", "is_superuser", "groups",
              "user_permissions", "date_joined", "last_login")
    readonly_fields = ("date_joined", "last_login")
    filter_horizontal = ("groups", "user_permissions")

    def save_model(self, request, obj, form, change):
        before = services.snapshot_model(User.objects.get(pk=obj.pk), exclude=("password",)) if change else {}
        super().save_model(request, obj, form, change)
        services.log(request.user, "user.update" if change else "user.create", obj, before=before,
                     after=services.snapshot_model(obj, exclude=("password",)))


class VerificationInline(admin.TabularInline):
    model = ProviderVerification
    fk_name = "provider"
    fields = ("doc_type", "status", "reason_code", "reviewed_at", "review_link")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Review")
    def review_link(self, obj):
        url = reverse("admin:accounts_providerverification_change", args=[obj.pk])
        return format_html('<a href="{}">open</a>', url)


@admin.register(ProviderProfile)
class ProviderProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "kind", "verification_status", "penalty_points", "created_at")
    list_filter = ("verification_status", "kind")
    search_fields = ("display_name", "user__email")
    readonly_fields = ("user", "verification_status", "penalty_points", "rating_avg", "rating_count", "created_at")
    inlines = [VerificationInline]


class VerificationDecisionForm(forms.Form):
    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("reject", "Reject")], widget=forms.RadioSelect)
    reason_code = forms.ChoiceField(
        choices=[("", "—")] + [(c, label) for c, label in ReasonCode.choices if c.startswith("id_") or c == "other"],
        required=False,
    )
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)


@admin.register(ProviderVerification)
class ProviderVerificationAdmin(admin.ModelAdmin):
    """Verification queue: pending documents, oldest first. Documents open via short-lived signed URLs."""

    list_display = ("provider", "doc_type", "status", "created_at", "reviewed_by")
    list_filter = ("status", "doc_type")
    ordering = ("created_at",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        doc = self.get_object(request, object_id)
        form = VerificationDecisionForm(request.POST or None)
        if request.method == "POST" and doc.status == ProviderVerification.Status.PENDING and form.is_valid():
            try:
                services.decide_verification(
                    request.user, doc, approve_doc=form.cleaned_data["decision"] == "approve",
                    reason_code=form.cleaned_data["reason_code"], note=form.cleaned_data["note"],
                )
            except DomainError as exc:
                messages.error(request, str(exc.detail))
            else:
                messages.success(request, "Decision recorded.")
                return redirect(reverse("admin:accounts_providerverification_changelist"))
        services.log(request.user, "provider.view_doc", doc.provider, after={"doc_id": str(doc.pk)})
        context = {
            **self.admin_site.each_context(request),
            "title": f"Verify {doc.provider.display_name}",
            "doc": doc,
            "doc_url": get_storage().url(doc.media.storage_key),
            "is_pdf": doc.media.content_type == "application/pdf",
            "user_obj": doc.provider.user,
            "form": form,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/moderation/verification_decision.html", context)


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "notice_version", "granted_at", "revoked_at")
    list_filter = ("purpose",)
    readonly_fields = [f.name for f in ConsentRecord._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
