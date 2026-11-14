"""Error responses in the API contract format.

Body: {"error": {"code": ..., "message": ..., "details": {...}?}}. ``code`` is a
stable, untranslated identifier; ``message`` and the messages in ``details`` are
translated to the request language (see core.middleware).
"""

import math

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from rest_framework import exceptions, parsers
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler

PARSERS_MODULE = parsers.__name__


def error_body(code: str, message: str, details: dict[str, list[str]] | None = None) -> dict:
    error = {"code": code, "message": str(message)}
    if details:
        error["details"] = details
    return {"error": error}


def _first_message(detail) -> str:
    """Return the first human-readable message from a (possibly nested) DRF error detail."""
    if isinstance(detail, dict):
        for value in detail.values():
            return _first_message(value)
        return ""
    if isinstance(detail, list):
        return _first_message(detail[0]) if detail else ""
    return str(detail)


def _flatten_details(detail, prefix: str = "") -> dict[str, list[str]]:
    """Map field paths to message lists, e.g. {"stops.0.name": ["This field is required."]}."""
    result: dict[str, list[str]] = {}
    if isinstance(detail, dict):
        for key, value in detail.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            for name, messages in _flatten_details(value, path).items():
                result.setdefault(name, []).extend(messages)
    elif isinstance(detail, list):
        for index, item in enumerate(detail):
            if isinstance(item, dict | list):
                # Errors of a nested list (many=True); empty entries mean "no error".
                nested = _flatten_details(item, f"{prefix}.{index}" if prefix else str(index))
                for name, messages in nested.items():
                    result.setdefault(name, []).extend(messages)
            else:
                result.setdefault(prefix or api_settings.NON_FIELD_ERRORS_KEY, []).append(str(item))
    else:
        result.setdefault(prefix or api_settings.NON_FIELD_ERRORS_KEY, []).append(str(detail))
    return result


def _raised_by_parser(exc: Exception) -> bool:
    """True if the exception was raised inside a DRF parser (rest_framework.parsers)."""
    tb = exc.__traceback__
    if tb is None:
        return False
    while tb.tb_next is not None:
        tb = tb.tb_next
    return tb.tb_frame.f_globals.get("__name__") == PARSERS_MODULE


def _throttled_message(exc: exceptions.Throttled) -> str:
    if exc.wait is None:
        return _("Too many requests. Try again later.")
    # Same rounding as the Retry-After header DRF sets.
    seconds = max(1, math.ceil(exc.wait))
    return ngettext(
        "Too many requests. Try again in %(seconds)d second.",
        "Too many requests. Try again in %(seconds)d seconds.",
        seconds,
    ) % {"seconds": seconds}


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

    code = exc.default_code
    details = None
    if isinstance(exc, exceptions.ValidationError):
        code = "validation_error"
        message = _first_message(exc.detail) or _("Invalid input.")
        if isinstance(exc.detail, dict):
            details = _flatten_details(exc.detail)
    elif isinstance(exc, exceptions.Throttled):
        message = _throttled_message(exc)
    elif isinstance(exc, exceptions.ParseError) and _raised_by_parser(exc):
        # DRF parsers put untranslated parser output in the detail
        # ("JSON parse error - Expecting value ..."). A ParseError raised by a
        # view keeps its own (translated) detail.
        message = _("The request body could not be parsed.")
    elif isinstance(exc, exceptions.PermissionDenied) and str(exc.detail).startswith("CSRF Failed"):
        # SessionAuthentication reports CSRF failures with untranslated Django reasons.
        message = _("CSRF verification failed.")
    else:
        message = _first_message(exc.detail)

    response.data = error_body(code, message, details)
    return response
