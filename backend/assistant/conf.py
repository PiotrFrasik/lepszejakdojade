"""Assistant settings.

Each value is read from Django settings when defined there, otherwise from the environment
variable of the same name, otherwise the default below.
"""

from __future__ import annotations

import math
import os

from django.conf import settings

DEFAULTS: dict[str, str | float] = {
    # Dotted path of the ChatProvider class.
    "ASSISTANT_PROVIDER": "assistant.providers.gemini.GeminiProvider",
    "GEMINI_API_KEY": "",
    # A current Gemini Flash model (alias kept up to date by Google); override with GEMINI_MODEL.
    "GEMINI_MODEL": "gemini-flash-latest",
    "GEMINI_API_URL": "https://generativelanguage.googleapis.com/v1beta",
    # Time budget (seconds) for all provider calls of one chat request.
    "ASSISTANT_TIMEOUT_SECONDS": 30.0,
    # DRF rate strings, per client IP.
    "ASSISTANT_RATE_PER_MINUTE": "10/min",
    "ASSISTANT_RATE_PER_DAY": "100/day",
}


def get(name: str):
    default = DEFAULTS[name]
    value = getattr(settings, name, None)
    if value is None or value == "":
        value = os.environ.get(name, "").strip() or None
    if value is None:
        return default
    if isinstance(default, float):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return number if math.isfinite(number) and number > 0 else default
    return str(value)
