"""Uniform API error envelope: {"error": {"code", "message", "fields"}}."""

from rest_framework import exceptions, status
from rest_framework.views import exception_handler


class DomainError(exceptions.APIException):
    """Business-rule violation with a stable machine-readable code."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_detail = "Conflict"

    def __init__(self, code: str, message: str, status_code: int | None = None, fields: dict | None = None):
        super().__init__(detail=message, code=code)
        self.code = code
        self.fields = fields or {}
        if status_code:
            self.status_code = status_code


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, DomainError):
        body = {"code": exc.code, "message": str(exc.detail), "fields": exc.fields}
    elif isinstance(exc, exceptions.ValidationError):
        detail = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
        body = {"code": "validation_error", "message": "Invalid input.", "fields": detail}
    else:
        codes = exc.get_codes() if hasattr(exc, "get_codes") else "error"
        body = {
            "code": codes if isinstance(codes, str) else "error",
            "message": str(getattr(exc, "detail", exc)),
            "fields": {},
        }
    if getattr(response, "headers", None) and "Retry-After" in response.headers:
        body["retry_after"] = int(response.headers["Retry-After"])
    response.data = {"error": body}
    return response
