from django.utils.translation import gettext as _
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import DomainError
from apps.moderation.models import Report

REASONS = ["spam", "inappropriate", "harassment", "fraud", "off_platform_payment", "safety", "misleading", "other"]


class ReportInput(serializers.Serializer):
    target_type = serializers.ChoiceField(choices=["experience", "review", "message", "user"])
    target_id = serializers.UUIDField()
    reason_code = serializers.ChoiceField(choices=REASONS)
    details = serializers.CharField(max_length=2000, required=False, allow_blank=True)


def _visible_target(user, target_type, target_id) -> bool:
    """Users can only report things they can actually see."""
    from apps.accounts.models import User
    from apps.catalog.models import Experience
    from apps.messaging.models import Message, MessageThread
    from apps.reviews.models import Review

    if target_type == "experience":
        return Experience.objects.filter(pk=target_id, status="live").exists()
    if target_type == "review":
        return Review.objects.filter(pk=target_id, revealed_at__isnull=False).exists()
    if target_type == "message":
        return Message.objects.filter(pk=target_id, thread__in=MessageThread.objects.filter(learner=user) |
                                      MessageThread.objects.filter(provider_id=user.pk)).exists()
    if target_type == "user":
        threads = MessageThread.objects.filter(learner=user) | MessageThread.objects.filter(provider_id=user.pk)
        return User.objects.filter(pk=target_id).exists() and (
            threads.filter(learner_id=target_id).exists() or threads.filter(provider_id=target_id).exists())
    return False


class ReportsView(APIView):
    def post(self, request):
        data = ReportInput(data=request.data)
        data.is_valid(raise_exception=True)
        d = data.validated_data
        if not _visible_target(request.user, d["target_type"], d["target_id"]):
            raise DomainError("not_found", _("No encontramos lo que quieres reportar."), status.HTTP_404_NOT_FOUND)
        report, created = Report.objects.get_or_create(
            reporter=request.user, target_type=d["target_type"], target_id=str(d["target_id"]), status=Report.Status.OPEN,
            defaults={"reason_code": d["reason_code"], "details": d.get("details", "")},
        )
        return Response({"id": str(report.pk)}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
