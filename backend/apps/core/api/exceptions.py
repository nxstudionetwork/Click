"""
Uniform error envelope for every Click API:

    {"error": {"code": "...", "message": "...", "details": {...}}}

Internal exceptions never leak stack traces or SQL to clients.
"""

import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class DomainError(exceptions.APIException):
    """A business-rule violation with a stable, machine-readable code."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "domain_error"
    default_detail = "The request could not be completed."

    def __init__(self, message: str | None = None, code: str | None = None, status_code: int | None = None, details=None):
        super().__init__(message or self.default_detail, code or self.default_code)
        if status_code:
            self.status_code = status_code
        self.error_code = code or self.default_code
        self.details = details


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"


def click_exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error", exc_info=exc)
        return Response(
            {"error": {"code": "server_error", "message": "Something went wrong. Please try again."}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, DomainError):
        body = {"code": exc.error_code, "message": str(exc.detail)}
        if exc.details:
            body["details"] = exc.details
    elif isinstance(exc, exceptions.ValidationError):
        body = {"code": "validation_error", "message": "Please check the highlighted fields.", "details": response.data}
    else:
        detail = response.data.get("detail", "") if isinstance(response.data, dict) else ""
        code = getattr(detail, "code", None) or getattr(exc, "default_code", "error")
        body = {"code": code, "message": str(detail) or "Request failed."}
    response.data = {"error": body}
    return response
