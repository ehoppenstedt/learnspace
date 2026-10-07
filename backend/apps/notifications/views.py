from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import LearnerProfile
from apps.notifications.models import Device
from apps.notifications.services import prefs_for


class DeviceSerializer(serializers.Serializer):
    expo_token = serializers.RegexField(r"^(Exponent|Expo)PushToken\[[A-Za-z0-9_\-]+\]$", max_length=200)
    platform = serializers.ChoiceField(choices=["ios", "android", "web"], required=False, default="")


class DevicesView(APIView):
    def post(self, request):
        data = DeviceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        # A token belongs to one phone; if another account used it, it moves to this one.
        Device.objects.update_or_create(expo_token=data.validated_data["expo_token"],
                                        defaults={"user": request.user, "platform": data.validated_data["platform"]})
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request):
        Device.objects.filter(user=request.user, expo_token=request.data.get("expo_token", "")).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PrefsSerializer(serializers.Serializer):
    push = serializers.BooleanField()
    email = serializers.BooleanField()
    reminders = serializers.BooleanField()


class NotificationPrefsView(APIView):
    def get(self, request):
        return Response(prefs_for(request.user))

    def put(self, request):
        data = PrefsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        profile, _ = LearnerProfile.objects.get_or_create(user=request.user)
        profile.notification_prefs = data.validated_data
        profile.save(update_fields=["notification_prefs"])
        request.user.learner_profile = profile
        return Response(prefs_for(request.user))
