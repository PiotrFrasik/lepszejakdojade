"""Google Gemini API provider (REST ``generateContent`` with function calling).

Uses ``urllib`` so no SDK dependency is needed. The API key comes only from
``GEMINI_API_KEY`` and is sent in the ``x-goog-api-key`` header (never in the URL, so it
does not end up in logs).

Note: on the free tier Google may use prompts and responses to improve its products.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .. import conf
from .base import ChatProvider, ModelReply, ProviderError, ToolCall, ToolSpec, Turn

logger = logging.getLogger(__name__)

_GENERATION_CONFIG = {"temperature": 0.2, "candidateCount": 1}


def _schema(value: Any) -> Any:
    """JSON Schema with lowercase types -> Gemini OpenAPI subset (uppercase types)."""
    if isinstance(value, dict):
        return {
            key: (item.upper() if key == "type" and isinstance(item, str) else _schema(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_schema(item) for item in value]
    return value


def _contents(turns: list[Turn]) -> list[dict]:
    contents: list[dict] = []
    for turn in turns:
        if turn.role == "user":
            contents.append({"role": "user", "parts": [{"text": turn.text}]})
        elif turn.role == "assistant" and turn.tool_calls:
            if isinstance(turn.raw, dict) and turn.raw.get("parts"):
                # Sent back unchanged: Gemini requires its thought signatures.
                contents.append({"role": "model", "parts": turn.raw["parts"]})
            else:
                contents.append(
                    {
                        "role": "model",
                        "parts": [
                            {"functionCall": {"name": call.name, "args": call.arguments}}
                            for call in turn.tool_calls
                        ],
                    }
                )
        elif turn.role == "assistant":
            contents.append({"role": "model", "parts": [{"text": turn.text}]})
        elif turn.role == "tool":
            parts = []
            for result in turn.tool_results:
                response: dict[str, Any] = {"name": result.call.name, "response": result.content}
                if result.call.id:
                    response["id"] = result.call.id
                parts.append({"functionResponse": response})
            contents.append({"role": "user", "parts": parts})
    return contents


def _reply(payload: Any) -> ModelReply:
    if not isinstance(payload, dict):
        raise ProviderError("response is not an object")
    candidates = payload.get("candidates") or []
    if not candidates:
        feedback = payload.get("promptFeedback") or {}
        raise ProviderError(f"no candidates (blockReason={feedback.get('blockReason')})")
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    texts: list[str] = []
    calls: list[ToolCall] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        function_call = part.get("functionCall")
        if isinstance(function_call, dict) and function_call.get("name"):
            args = function_call.get("args")
            calls.append(
                ToolCall(
                    name=str(function_call["name"]),
                    arguments=args if isinstance(args, dict) else {},
                    id=function_call.get("id"),
                )
            )
        elif isinstance(part.get("text"), str) and not part.get("thought"):
            texts.append(part["text"])
    text = "".join(texts).strip()
    if not calls and not text:
        raise ProviderError(f"empty reply (finishReason={candidates[0].get('finishReason')})")
    return ModelReply(
        text=text,
        tool_calls=tuple(calls),
        raw={"role": "model", "parts": parts} if calls else None,
    )


class GeminiProvider(ChatProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else conf.get("GEMINI_API_KEY")
        self.model = model or conf.get("GEMINI_MODEL")
        self.base_url = conf.get("GEMINI_API_URL").rstrip("/")
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY is not set")

    def _url(self) -> str:
        return f"{self.base_url}/models/{urllib.parse.quote(self.model, safe='')}:generateContent"

    def generate(
        self, system_prompt: str, turns: list[Turn], tools: list[ToolSpec], timeout: float
    ) -> ModelReply:
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": _contents(turns),
            "generationConfig": _GENERATION_CONFIG,
        }
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": _schema(tool.parameters),
                        }
                        for tool in tools
                    ]
                }
            ]
            body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
        request = urllib.request.Request(
            self._url(),
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-goog-api-key": self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            with contextlib.suppress(OSError):
                detail = exc.read(500).decode("utf-8", "replace")
            logger.warning("Gemini returned HTTP %s: %s", exc.code, detail)
            raise ProviderError(f"HTTP {exc.code}") from exc
        # URLError, timeouts, bad JSON, truncated or malformed HTTP responses
        except (OSError, ValueError, http.client.HTTPException) as exc:
            logger.warning("Gemini request failed: %s", exc)
            raise ProviderError(str(exc)) from exc
        return _reply(payload)
