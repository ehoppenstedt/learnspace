from rest_framework.throttling import SimpleRateThrottle


class _ScopedIPThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class OTPRequestIPThrottle(_ScopedIPThrottle):
    scope = "otp_request_ip"


class OTPVerifyIPThrottle(_ScopedIPThrottle):
    scope = "otp_verify_ip"


class AuthIPThrottle(_ScopedIPThrottle):
    scope = "auth_ip"
