"""Per-IP rate limits of the chat endpoint (rates from ``assistant.conf``).

Counters live in Django's default cache. Until a shared cache (Redis) is configured, that
is the per-process local-memory cache, so with several server processes each process
counts separately. Behind a reverse proxy set DRF's ``NUM_PROXIES`` so the client address
is taken from ``X-Forwarded-For``.
"""

from __future__ import annotations

from rest_framework.exceptions import Throttled
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle

from . import conf


class RateLimited(Throttled):
    default_code = "rate_limited"


class _IpRateThrottle(SimpleRateThrottle):
    rate_setting = ""

    def get_rate(self) -> str:
        return conf.get(self.rate_setting)

    def get_ident(self, request) -> str:
        # DRF trusts the whole X-Forwarded-For header when NUM_PROXIES is unset, which lets
        # a client pick its own identity. Without configured proxies use the socket address.
        if api_settings.NUM_PROXIES is None:
            return request.META.get("REMOTE_ADDR") or ""
        return super().get_ident(request)

    def get_cache_key(self, request, view) -> str:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class ChatMinuteThrottle(_IpRateThrottle):
    scope = "assistant_minute"
    rate_setting = "ASSISTANT_RATE_PER_MINUTE"


class ChatDayThrottle(_IpRateThrottle):
    scope = "assistant_day"
    rate_setting = "ASSISTANT_RATE_PER_DAY"
