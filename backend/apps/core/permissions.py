from rest_framework.permissions import BasePermission


class IsProfileComplete(BasePermission):
    message = "Complete your profile first."
    code = "profile_incomplete"

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.profile_complete)


class IsProvider(BasePermission):
    message = "Provider profile required."
    code = "not_provider"

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and hasattr(request.user, "provider_profile"))
