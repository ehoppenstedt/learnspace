from django.contrib import admin

from apps.messaging.models import Message, MessageThread
from apps.moderation import services as audit


class MessageInline(admin.TabularInline):
    model = Message
    fields = ("created_at", "sender", "body", "detected", "hidden")
    readonly_fields = ("created_at", "sender", "body", "detected")
    extra = 0
    can_delete = False


@admin.register(MessageThread)
class MessageThreadAdmin(admin.ModelAdmin):
    """Read for moderation only (reports). Every view is audited."""

    list_display = ("experience", "learner", "provider", "booking", "last_message_at")
    search_fields = ("experience__title", "learner__email", "provider__display_name")
    readonly_fields = ("experience", "learner", "provider", "booking", "last_message_at")
    exclude = ("learner_read_at", "provider_read_at")
    inlines = [MessageInline]

    def has_add_permission(self, request):
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        thread = self.get_object(request, object_id)
        if thread and request.method == "GET":
            audit.log(request.user, "thread.view", thread)
        return super().change_view(request, object_id, form_url, extra_context)


@admin.register(Message)
class FlaggedMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "thread", "sender", "body", "detected", "hidden")
    list_filter = ("hidden",)
    readonly_fields = ("thread", "sender", "body", "detected", "created_at")
    actions = ["hide"]

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(detected=[])

    def has_add_permission(self, request):
        return False

    @admin.action(description="Hide message")
    def hide(self, request, queryset):
        for m in queryset:
            Message.objects.filter(pk=m.pk).update(hidden=True)
            audit.log(request.user, "message.hide", m)
