import logging
import time

from apps.core.ids import uuid7

logger = logging.getLogger("request")


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.headers.get("X-Request-ID") or str(uuid7())
        start = time.perf_counter()
        response = self.get_response(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        response["X-Request-ID"] = request.request_id
        if request.path.startswith("/api/"):
            user = getattr(request, "user", None)
            logger.info(
                "request",
                extra={
                    "request_id": request.request_id,
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": elapsed_ms,
                    "user_id": str(user.pk) if user is not None and user.is_authenticated else None,
                },
            )
        return response


class DevCorsMiddleware:
    """Development only: lets the Expo web preview call the API from another port.
    Active only when DEBUG is on and DEV_CORS_ORIGINS is set. Native apps don't need CORS."""

    def __init__(self, get_response):
        from django.conf import settings

        self.get_response = get_response
        self.origins = set(settings.DEV_CORS_ORIGINS) if settings.DEBUG else set()

    def __call__(self, request):
        origin = request.headers.get("Origin")
        allowed = origin in self.origins
        if allowed and request.method == "OPTIONS":
            from django.http import HttpResponse

            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        if allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept-Language, X-Client-Platform"
            response["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return response
