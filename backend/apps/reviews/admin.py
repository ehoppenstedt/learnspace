from django.contrib import admin, messages

from apps.core.exceptions import DomainError
from apps.reviews import services
from apps.reviews.models import ConductAppeal, ConductRating, Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("created_at", "experience", "author", "overall", "moderation", "revealed_at")
    list_filter = ("moderation", "overall")
    search_fields = ("experience__title", "author__email", "public_text")
    readonly_fields = [f.name for f in Review._meta.fields]
    actions = ["hide", "show"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Hide from public (moderation)")
    def hide(self, request, queryset):
        for review in queryset:
            services.set_review_visibility(request.user, review, visible=False, note="admin action")

    @admin.action(description="Show again")
    def show(self, request, queryset):
        for review in queryset:
            services.set_review_visibility(request.user, review, visible=True, note="admin action")


@admin.register(ConductRating)
class ConductRatingAdmin(admin.ModelAdmin):
    list_display = ("created_at", "learner", "provider", "respect", "punctuality", "excluded", "revealed_at")
    list_filter = ("excluded",)
    readonly_fields = [f.name for f in ConductRating._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(ConductAppeal)
class ConductAppealAdmin(admin.ModelAdmin):
    """Write the decision note, save, then use an action to decide."""

    list_display = ("created_at", "learner", "status", "decided_by")
    list_filter = ("status",)
    readonly_fields = ("rating", "learner", "statement", "status", "decided_by", "decided_at", "rating_detail")
    fields = ("rating", "rating_detail", "learner", "statement", "decision_note", "status", "decided_by", "decided_at")
    actions = ["overturn", "uphold"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="Rating")
    def rating_detail(self, obj):
        r = obj.rating
        return f"respect {r.respect} · punctuality {r.punctuality} · provider note: {r.admin_note or '—'}"

    def _decide(self, request, queryset, overturn):
        for appeal in queryset:
            try:
                services.decide_appeal(request.user, appeal, overturn=overturn, note=appeal.decision_note or "")
            except DomainError as exc:
                messages.error(request, str(exc.detail))

    @admin.action(description="Overturn: exclude the rating from the score")
    def overturn(self, request, queryset):
        self._decide(request, queryset, True)

    @admin.action(description="Uphold: keep the rating")
    def uphold(self, request, queryset):
        self._decide(request, queryset, False)
