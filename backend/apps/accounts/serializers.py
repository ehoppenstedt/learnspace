from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.models import ConsentRecord, LearnerProfile, OTPChallenge, ProviderProfile, User, age_on, local_today
from apps.catalog.models import Category


class OTPRequestSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=OTPChallenge.Channel.choices)
    destination = serializers.CharField(max_length=254)


class OTPVerifySerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    code = serializers.RegexField(r"^\d{6}$")


class AppleLoginSerializer(serializers.Serializer):
    identity_token = serializers.CharField()
    nonce = serializers.CharField(required=False, allow_blank=False)
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=80)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=80)


class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField()


class PhoneRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=30)


class ProviderSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderProfile
        fields = ["display_name", "kind", "verification_status"]


class MeSerializer(serializers.ModelSerializer):
    profile_complete = serializers.BooleanField(read_only=True)
    is_provider = serializers.BooleanField(read_only=True)
    provider = serializers.SerializerMethodField()
    bio = serializers.CharField(source="learner_profile.bio", required=False, allow_blank=True, max_length=500)
    fluent_languages = serializers.ListField(source="learner_profile.fluent_languages", read_only=True)
    has_accessibility_needs = serializers.SerializerMethodField()
    conduct_score = serializers.DecimalField(source="learner_profile.conduct_score", max_digits=3, decimal_places=2, read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "email_verified", "phone_e164", "phone_verified", "first_name", "last_name",
            "date_of_birth", "ui_language", "profile_complete", "is_provider", "provider", "bio",
            "fluent_languages", "has_accessibility_needs", "conduct_score",
        ]
        read_only_fields = [
            "id", "email", "email_verified", "phone_e164", "phone_verified", "date_of_birth",
        ]

    def get_provider(self, obj):
        profile = getattr(obj, "provider_profile", None)
        return ProviderSummarySerializer(profile).data if profile else None

    def get_has_accessibility_needs(self, obj):
        profile = getattr(obj, "learner_profile", None)
        return bool(profile and profile.accessibility_needs)

    def update(self, instance, validated_data):
        learner = validated_data.pop("learner_profile", {})
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if learner:
            profile, _ = LearnerProfile.objects.get_or_create(user=instance)
            for key, value in learner.items():
                setattr(profile, key, value)
            profile.save()
        return instance


class CompleteProfileSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80)
    email = serializers.EmailField(required=False)
    date_of_birth = serializers.DateField()
    accept_privacy_notice = serializers.BooleanField()
    fluent_languages = serializers.ListField(child=serializers.ChoiceField(choices=["es", "en", "fr", "de", "pt", "it", "ja", "zh", "ko", "nah", "other"]), required=False, max_length=10)
    consent_fluent_languages = serializers.BooleanField(required=False, default=False)
    accessibility_needs = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    consent_accessibility = serializers.BooleanField(required=False, default=False)

    def validate_date_of_birth(self, value):
        today = local_today()
        if value > today or value.year < 1900:
            raise serializers.ValidationError(_("Fecha de nacimiento inválida."))
        if age_on(value, today) < settings.MIN_AGE_YEARS:
            raise serializers.ValidationError(_("Debes tener al menos 18 años."), code="underage")
        return value

    def validate_accept_privacy_notice(self, value):
        if not value:
            raise serializers.ValidationError(_("Debes aceptar el aviso de privacidad."))
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        email = attrs.get("email")
        if not user.email and not email:
            raise serializers.ValidationError({"email": _("El correo es obligatorio.")})
        if email and User.objects.filter(email=email.lower()).exclude(pk=user.pk).exists():
            raise serializers.ValidationError({"email": _("Este correo ya está registrado.")})
        if attrs.get("fluent_languages") and not attrs.get("consent_fluent_languages"):
            raise serializers.ValidationError({"consent_fluent_languages": _("Se requiere tu consentimiento.")})
        if attrs.get("accessibility_needs") and not attrs.get("consent_accessibility"):
            raise serializers.ValidationError({"consent_accessibility": _("Se requiere tu consentimiento expreso.")})
        return attrs


class ConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsentRecord
        fields = ["purpose", "notice_version", "granted_at", "revoked_at"]


class InterestsSerializer(serializers.Serializer):
    category_ids = serializers.PrimaryKeyRelatedField(queryset=Category.objects.filter(is_active=True), many=True)


class FiltersSerializer(serializers.Serializer):
    """Persisted feed filters. Same shape the feed endpoint accepts."""

    categories = serializers.ListField(child=serializers.SlugField(), required=False, max_length=20)
    price_min_cents = serializers.IntegerField(required=False, min_value=0, allow_null=True)
    price_max_cents = serializers.IntegerField(required=False, min_value=0, allow_null=True)
    radius_km = serializers.IntegerField(required=False, min_value=1, max_value=settings.FEED_MAX_RADIUS_KM)
    days = serializers.ListField(child=serializers.IntegerField(min_value=1, max_value=7), required=False, max_length=7)
    time_from = serializers.TimeField(required=False, allow_null=True, format="%H:%M")
    time_to = serializers.TimeField(required=False, allow_null=True, format="%H:%M")
    modality = serializers.ChoiceField(choices=["in_person", "online"], required=False, allow_null=True)
    language = serializers.CharField(required=False, max_length=5, allow_null=True)
    area = serializers.SlugField(required=False, allow_null=True)


class ProviderProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderProfile
        fields = ["display_name", "about_me", "about_school", "kind", "avatar", "verification_status", "rating_avg", "rating_count"]
        read_only_fields = ["verification_status", "rating_avg", "rating_count"]
