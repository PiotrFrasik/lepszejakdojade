"""Error responses in the API contract format: {"error": {"code": ..., "message": ...}}."""

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.translation import gettext as _
from rest_framework import exceptions
from rest_framework.views import exception_handler


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": str(message)}}


def _first_message(detail) -> str:
    """Return the first human-readable message from a (possibly nested) DRF error detail."""
    if isinstance(detail, dict):
        for value in detail.values():
            return _first_message(value)
        return ""
    if isinstance(detail, list):
        return _first_message(detail[0]) if detail else ""
    return str(detail)


def api_exception_handler(exc, context):
    """Wrap DRF's default handler so every API error uses the contract format.

    Unhandled exceptions return None and become a 500 rendered by
    core.views.server_error.
    """
    # Same conversion DRF does internally, so the error code is known below.
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, exceptions.ValidationError):
        code = "validation_error"
        message = _first_message(exc.detail) or _("Invalid input.")
    else:
        code = exc.default_code
        message = _first_message(exc.detail)

    response.data = error_body(code, message)
    return response
