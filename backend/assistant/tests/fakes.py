"""A scripted ChatProvider for tests: replies are queued, every call is recorded."""

from __future__ import annotations

from assistant.providers import ChatProvider, ModelReply, ProviderError, ToolCall


def say(text: str) -> ModelReply:
    return ModelReply(text=text)


def call(name: str, **arguments) -> ToolCall:
    return ToolCall(name=name, arguments=arguments)


def ask(*calls: ToolCall) -> ModelReply:
    return ModelReply(tool_calls=tuple(calls))


class ScriptedProvider(ChatProvider):
    """Returns the queued replies in order; an Exception in the queue is raised.
    When the queue is empty the last reply is repeated (``repeat``) or the test fails."""

    current: ScriptedProvider | None = None

    def __init__(self, *replies, repeat: bool = False):
        self.replies = list(replies)
        self.repeat = repeat
        self.calls: list[dict] = []

    def generate(self, system_prompt, turns, tools, timeout):
        # Snapshot: the chat loop keeps appending to the same list.
        self.calls.append(
            {"system": system_prompt, "turns": list(turns), "tools": tools, "timeout": timeout}
        )
        if not self.replies:
            raise AssertionError("provider called more often than scripted")
        reply = self.replies[0] if self.repeat else self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    @property
    def tool_results(self) -> list[dict]:
        """Contents of all tool results sent back to the model (seen by the last call)."""
        return [
            result.content
            for turn in self.calls[-1]["turns"]
            if turn.role == "tool"
            for result in turn.tool_results
        ]


def current_provider() -> ScriptedProvider:
    """Factory used as ``ASSISTANT_PROVIDER`` in tests."""
    assert ScriptedProvider.current is not None
    return ScriptedProvider.current


__all__ = ["ProviderError", "ScriptedProvider", "ask", "call", "current_provider", "say"]
