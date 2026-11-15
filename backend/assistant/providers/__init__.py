"""Chat model providers. ``get_provider()`` returns the configured one (``ASSISTANT_PROVIDER``)."""

from __future__ import annotations

from django.utils.module_loading import import_string

from .. import conf
from .base import ChatProvider, ModelReply, ProviderError, ToolCall, ToolResult, ToolSpec, Turn

__all__ = [
    "ChatProvider",
    "ModelReply",
    "ProviderError",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
    "Turn",
    "get_provider",
]


def get_provider() -> ChatProvider:
    """A new instance of the configured provider. Raises ProviderError when it cannot be
    created (e.g. missing API key)."""
    try:
        provider_class = import_string(conf.get("ASSISTANT_PROVIDER"))
    except ImportError as exc:
        raise ProviderError(f"cannot import provider: {exc}") from exc
    return provider_class()
