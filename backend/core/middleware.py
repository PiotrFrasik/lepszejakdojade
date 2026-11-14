"""Language negotiation for every request (docs/api.md, "Language negotiation").

The language comes only from the ``Accept-Language`` header. Cookies, sessions,
query parameters and URL prefixes are ignored, so Django's ``LocaleMiddleware``
is replaced by ``AcceptLanguageMiddleware``.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.utils import translation
from django.utils.cache import patch_vary_headers

# Longer headers are cut at the last complete entry (same limit as Django).
ACCEPT_LANGUAGE_MAX_LENGTH = 500

_TAG_RE = re.compile(r"^[A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*$")


def parse_accept_language(header: str | None) -> list[str]:
    """Return language tags from an ``Accept-Language`` value, most preferred first.

    Entries with ``q=0``, an invalid ``q`` or an invalid tag (including ``*``)
    are skipped. Entries with equal ``q`` keep their header order.
    """
    if not header:
        return []
    if len(header) > ACCEPT_LANGUAGE_MAX_LENGTH:
        header = header[:ACCEPT_LANGUAGE_MAX_LENGTH].rpartition(",")[0]

    entries: list[tuple[float, int, str]] = []
    for index, part in enumerate(header.split(",")):
        tag, _, params = part.partition(";")
        tag = tag.strip()
        if not _TAG_RE.match(tag):
            continue
        quality: float | None = 1.0
        for param in params.split(";") if params else ():
            name, has_value, value = param.partition("=")
            if name.strip().lower() != "q":
                continue
            try:
                quality = float(value) if has_value else None
            except ValueError:
                quality = None
        if quality is None or not 0 < quality <= 1:
            continue
        entries.append((-quality, index, tag))
    return [tag for _, _, tag in sorted(entries)]


def negotiate_language(header: str | None) -> str:
    """Pick the first supported language from the header; ``LANGUAGE_CODE`` otherwise.

    Regional tags map to their base language (``en-GB`` -> ``en``).
    """
    for tag in parse_accept_language(header):
        try:
            return translation.get_supported_language_variant(tag.lower())
        except LookupError:
            continue
    return settings.LANGUAGE_CODE


class AcceptLanguageMiddleware:
    """Activate the negotiated language and send it back in ``Content-Language``."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = negotiate_language(request.headers.get("Accept-Language"))
        translation.activate(language)
        request.LANGUAGE_CODE = language
        try:
            response = self.get_response(request)
        finally:
            translation.deactivate()
        # A view that answers in another language on purpose may set the header itself.
        response.headers.setdefault("Content-Language", language)
        patch_vary_headers(response, ("Accept-Language",))
        return response
