"""Provider-neutral chat model interface.

A provider turns a conversation (``Turn`` list) plus tool declarations into one model reply:
either final text or a list of tool calls. The chat loop (``assistant.chat``) runs the tools
and calls the provider again. Adding a provider = one ``ChatProvider`` subclass, selected
with the ``ASSISTANT_PROVIDER`` setting; nothing else changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


class ProviderError(Exception):
    """The model could not answer: not configured, network error, timeout, bad response,
    quota exceeded. The message is for logs only, never for clients."""


@dataclass(frozen=True)
class ToolSpec:
    """A function the model may call. ``parameters`` is a JSON Schema object with lowercase
    types (``object``, ``string``, ``integer``, ``number``, ``boolean``), ``description``,
    ``properties``, ``required`` and ``enum`` (string parameters only, a Gemini limit);
    providers convert it as needed."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str | None = None  # provider call id, when the provider uses one


@dataclass(frozen=True)
class ToolResult:
    call: ToolCall
    content: dict[str, Any]  # JSON-serialisable


@dataclass
class Turn:
    """One entry of the conversation.

    - ``user`` / ``assistant`` with ``text``: messages of the chat.
    - ``assistant`` with ``tool_calls``: the model asked for tools. ``raw`` keeps the
      provider's own representation (e.g. Gemini thought signatures) so it can be sent back
      unchanged; other providers ignore it.
    - ``tool`` with ``tool_results``: answers to the previous tool calls.
    """

    role: Literal["user", "assistant", "tool"]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    raw: Any = None


@dataclass(frozen=True)
class ModelReply:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    raw: Any = None  # provider representation of this reply, stored in Turn.raw


class ChatProvider(ABC):
    """One chat model behind a uniform interface."""

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        turns: list[Turn],
        tools: list[ToolSpec],
        timeout: float,
    ) -> ModelReply:
        """Return the model's next reply. Raises ProviderError on any failure."""
