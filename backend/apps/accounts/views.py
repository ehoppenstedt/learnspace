from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts import services
from apps.accounts.models import (
    AuthIdentity,
    ConsentRecord,
    Interest,
    LearnerProfile,
    OTPChallenge,
    ProviderProfile,
    ProviderVerification,
)
from apps.accounts.serializers import (
    AppleLoginSerializer,
    CompleteProfileSerializer,
    ConsentSerializer,
    FiltersSerializer,
    GoogleLoginSerializer,
    InterestsSerializer,
    MeSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    PhoneRequestSerializer,
    ProviderProfileSerializer,
)
from apps.accounts.throttles import AuthIPThrottle, OTPRequestIPThrottle, OTPVerifyIPThrottle
from apps.catalog.models import MediaAsset
from apps.core.exceptions import DomainError
from apps.core.permissions import IsProfileComplete, IsProvider


def _client_ip(request):
    return request.META.get("REMOTE_ADDR")


def _session_payload(user, created: bool) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "created": created,
        "user": MeSerializer(user).data,
    }


class OTPRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [OTPRequestIPThrottle]

    def post(self, request):
        data = OTPRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        challenge = services.request_otp(**data.validated_data, ip=_client_ip(request))
        return Response({"challenge_id": challenge.id, "expires_at": challenge.expires_at}, status=status.HTTP_202_ACCEPTED)


class OTPVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [OTPVerifyIPThrottle]

    def post(self, request):
        data = OTPVerifySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = services.login_with_otp(data.validated_data["challenge_id"], data.validated_data["code"])
        return Response(_session_payload(result.user, result.created))


class AppleLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [AuthIPThrottle]

    def post(self, request):
        data = AppleLoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        claims = services.verify_apple_token(data.validated_data["identity_token"], data.validated_data.get("nonce"))
        result = services.login_with_identity(AuthIdentity.Provider.APPLE, claims)
        # Apple sends the name only on the very first authorization, via the client.
        user = result.user
        if result.created:
            user.first_name = data.validated_data.get("first_name", "")[:80]
            user.last_name = data.validated_data.get("last_name", "")[:80]
            user.save(update_fields=["first_name", "last_name"])
        return Response(_session_payload(user, result.created))


class GoogleLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [AuthIPThrottle]

    def post(self, request):
        data = GoogleLoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        claims = services.verify_google_token(data.validated_data["id_token"])
        result = services.login_with_identity(AuthIdentity.Provider.GOOGLE, claims)
        user = result.user
        if result.created:
            user.first_name = (claims.get("given_name") or "")[:80]
            user.last_name = (claims.get("family_name") or "")[:80]
            user.save(update_fields=["first_name", "last_name"])
        return Response(_session_payload(user, result.created))


class RefreshView(TokenRefreshView):
    throttle_classes = [AuthIPThrottle]


class LogoutView(APIView):
    # The refresh token itself is the credential; the access token may already be expired.
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh", "")).blacklist()
        except TokenError:
            pass  # already invalid: logging out is idempotent
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        LearnerProfile.objects.get_or_create(user=request.user)
        return Response(MeSerializer(request.user).data)

    def patch(self, request):
        LearnerProfile.objects.get_or_create(user=request.user)
        serializer = MeSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MeSerializer(request.user).data)


class CompleteProfileView(APIView):
    def post(self, request):
        user = request.user
        if not user.phone_verified:
            raise DomainError("phone_not_verified", _("Verifica tu teléfono primero."), status.HTTP_400_BAD_REQUEST)
        serializer = CompleteProfileSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            user.first_name = data["first_name"].strip()
            user.last_name = data["last_name"].strip()
            user.date_of_birth = data["date_of_birth"]
            if data.get("email") and data["email"].lower() != (user.email or ""):
                user.email = data["email"].lower()
                user.email_verified = False
            user.save()
            profile, _created = LearnerProfile.objects.get_or_create(user=user)
            services.record_consent(user, ConsentRecord.Purpose.PRIVACY_NOTICE)
            if data.get("fluent_languages"):
                services.record_consent(user, ConsentRecord.Purpose.FLUENT_LANGUAGES)
                profile.fluent_languages = data["fluent_languages"]
            if data.get("accessibility_needs"):
                services.record_consent(user, ConsentRecord.Purpose.ACCESSIBILITY)
                profile.accessibility_needs = data["accessibility_needs"]
            profile.save()
        return Response(MeSerializer(user).data)


class PhoneRequestView(APIView):
    throttle_classes = [OTPRequestIPThrottle]

    def post(self, request):
        data = PhoneRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        challenge = services.request_otp(
            channel=OTPChallenge.Channel.SMS, destination=data.validated_data["phone"],
            purpose=OTPChallenge.Purpose.VERIFY_PHONE, user=request.user, ip=_client_ip(request),
        )
        return Response({"challenge_id": challenge.id, "expires_at": challenge.expires_at}, status=status.HTTP_202_ACCEPTED)


class PhoneVerifyView(APIView):
    throttle_classes = [OTPVerifyIPThrottle]

    def post(self, request):
        data = OTPVerifySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = services.verify_phone_for_user(request.user, data.validated_data["challenge_id"], data.validated_data["code"])
        return Response(MeSerializer(user).data)


class FiltersView(APIView):
    def get(self, request):
        profile, _ = LearnerProfile.objects.get_or_create(user=request.user)
        return Response(profile.feed_filters)

    def put(self, request):
        serializer = FiltersSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile, _ = LearnerProfile.objects.get_or_create(user=request.user)
        profile.feed_filters = serializer.data
        profile.save(update_fields=["feed_filters"])
        return Response(profile.feed_filters)


class InterestsView(APIView):
    def get(self, request):
        return Response({"category_ids": list(Interest.objects.filter(user=request.user).values_list("category_id", flat=True))})

    def put(self, request):
        serializer = InterestsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            Interest.objects.filter(user=request.user).delete()
            Interest.objects.bulk_create(
                [Interest(user=request.user, category=c) for c in serializer.validated_data["category_ids"]]
            )
        return self.get(request)


class ConsentsView(APIView):
    def get(self, request):
        return Response(ConsentSerializer(request.user.consents.order_by("-granted_at"), many=True).data)


class ConsentRevokeView(APIView):
    def delete(self, request, purpose):
        if purpose not in ConsentRecord.Purpose.values or purpose == ConsentRecord.Purpose.PRIVACY_NOTICE:
            raise DomainError("invalid_purpose", _("Este consentimiento no se puede revocar aquí."), status.HTTP_400_BAD_REQUEST)
        services.revoke_consent(request.user, purpose)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Provider identity
# ---------------------------------------------------------------------------


class ProviderActivateView(APIView):
    permission_classes = [IsAuthenticated, IsProfileComplete]

    def post(self, request):
        profile, created = ProviderProfile.objects.get_or_create(
            user=request.user, defaults={"display_name": request.user.full_name}
        )
        return Response(ProviderProfileSerializer(profile).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ProviderProfileView(APIView):
    permission_classes = [IsAuthenticated, IsProvider]

    def get(self, request):
        return Response(ProviderProfileSerializer(request.user.provider_profile).data)

    def patch(self, request):
        serializer = ProviderProfileSerializer(request.user.provider_profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        avatar = serializer.validated_data.get("avatar")
        if avatar and avatar.owner_id != request.user.pk:
            raise DomainError("media_not_found", _("Archivo no encontrado."), status.HTTP_404_NOT_FOUND)
        serializer.save()
        return Response(serializer.data)


class VerificationDocsView(APIView):
    permission_classes = [IsAuthenticated, IsProvider]

    def get(self, request):
        docs = request.user.provider_profile.verifications.order_by("-created_at")
        return Response([
            {"id": d.id, "doc_type": d.doc_type, "status": d.status, "reason_code": d.reason_code, "created_at": d.created_at}
            for d in docs
        ])

    def post(self, request):
        doc_type = request.data.get("doc_type")
        if doc_type not in ProviderVerification.DocType.values:
            raise DomainError("invalid_doc_type", _("Tipo de documento inválido."), status.HTTP_400_BAD_REQUEST)
        media = MediaAsset.objects.filter(pk=request.data.get("media_id"), owner=request.user).first()
        if media is None or media.status == MediaAsset.Status.PENDING_UPLOAD:
            raise DomainError("media_not_found", _("Archivo no encontrado."), status.HTTP_404_NOT_FOUND)
        provider = request.user.provider_profile
        with transaction.atomic():
            doc = ProviderVerification.objects.create(provider=provider, doc_type=doc_type, media=media)
            if provider.verification_status in (ProviderProfile.Verification.UNVERIFIED, ProviderProfile.Verification.REJECTED):
                provider.verification_status = ProviderProfile.Verification.PENDING
                provider.save(update_fields=["verification_status"])
        return Response({"id": doc.id, "doc_type": doc.doc_type, "status": doc.status}, status=status.HTTP_201_CREATED)
