"""GeminiProvider request/response mapping with urlopen mocked (the real API is never called)."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from assistant.providers import ProviderError, ToolCall, ToolResult, ToolSpec, Turn
from assistant.providers.gemini import GeminiProvider

KEY = "AIza-test-secret-key"
SPEC = ToolSpec(
    "next_departures",
    "Next departures",
    {
        "type": "object",
        "properties": {
            "stop_id": {"type": "string", "enum": ["a", "b"]},
            "limit": {"type": "integer"},
            "flag": {"type": "boolean"},
        },
        "required": ["stop_id"],
    },
)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Recorder:
    """Replaces urllib.request.urlopen; returns ``payload`` or raises ``error``."""

    def __init__(self, payload=None, error=None, raw=None):
        self.payload, self.error, self.raw = payload, error, raw
        self.requests: list = []
        self.timeouts: list = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.error:
            raise self.error
        data = self.raw if self.raw is not None else json.dumps(self.payload).encode()
        return FakeResponse(data)

    @property
    def body(self):
        return json.loads(self.requests[0].data.decode())


def text_payload(*parts, finish="STOP"):
    return {
        "candidates": [{"content": {"role": "model", "parts": list(parts)}, "finishReason": finish}]
    }


@pytest.fixture
def provider(settings):
    settings.GEMINI_API_URL = "https://gemini.example.invalid/v1beta"
    return GeminiProvider(api_key=KEY, model="gemini-test")


def use(monkeypatch, recorder):
    monkeypatch.setattr("assistant.providers.gemini.urllib.request.urlopen", recorder)
    return recorder


def generate(provider, turns=None, tools=(SPEC,), timeout=7.5):
    return provider.generate(
        "SYSTEM", turns or [Turn(role="user", text="Hi")], list(tools), timeout
    )


# ---------------------------------------------------------------------------- request


def test_api_key_is_in_the_header_not_in_the_url(provider, monkeypatch):
    rec = use(monkeypatch, Recorder(text_payload({"text": "ok"})))
    generate(provider)
    request = rec.requests[0]
    assert request.get_header("X-goog-api-key") == KEY
    assert KEY not in request.full_url
    assert "key=" not in request.full_url
    assert KEY not in request.data.decode()


def test_url_method_and_timeout(provider, monkeypatch):
    rec = use(monkeypatch, Recorder(text_payload({"text": "ok"})))
    generate(provider, timeout=7.5)
    request = rec.requests[0]
    assert request.get_method() == "POST"
    assert request.full_url == (
        "https://gemini.example.invalid/v1beta/models/gemini-test:generateContent"
    )
    assert rec.timeouts == [7.5]
    assert request.get_header("Content-type") == "application/json"


def test_system_prompt_user_turn_and_tools_are_mapped(provider, monkeypatch):
    rec = use(monkeypatch, Recorder(text_payload({"text": "ok"})))
    generate(provider)
    body = rec.body
    assert body["systemInstruction"] == {"parts": [{"text": "SYSTEM"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "Hi"}]}]
    declaration = body["tools"][0]["functionDeclarations"][0]
    assert declaration["name"] == "next_departures"
    assert declaration["description"] == "Next departures"
    props = declaration["parameters"]["properties"]
    assert declaration["parameters"]["type"] == "OBJECT"
    assert props["stop_id"] == {"type": "STRING", "enum": ["a", "b"]}
    assert props["limit"]["type"] == "INTEGER"
    assert props["flag"]["type"] == "BOOLEAN"
    assert declaration["parameters"]["required"] == ["stop_id"]
    assert body["toolConfig"]["functionCallingConfig"]["mode"] == "AUTO"


def test_no_tools_means_no_tool_config(provider, monkeypatch):
    rec = use(monkeypatch, Recorder(text_payload({"text": "ok"})))
    generate(provider, tools=())
    assert "tools" not in rec.body
    assert "toolConfig" not in rec.body


def test_assistant_text_turn_maps_to_model_role(provider, monkeypatch):
    rec = use(monkeypatch, Recorder(text_payload({"text": "ok"})))
    generate(
        provider,
        [
            Turn(role="user", text="q1"),
            Turn(role="assistant", text="a1"),
            Turn(role="user", text="q2"),
        ],
    )
    assert [(c["role"], c["parts"][0]["text"]) for c in rec.body["contents"]] == [
        ("user", "q1"),
        ("model", "a1"),
        ("user", "q2"),
    ]


def test_function_call_and_function_response_turns(provider, monkeypatch):
    rec = use(monkeypatch, Recorder(text_payload({"text": "ok"})))
    tool_call = ToolCall("next_departures", {"stop_id": "a"}, id="call-1")
    generate(
        provider,
        [
            Turn(role="user", text="when?"),
            Turn(role="assistant", tool_calls=[tool_call]),
            Turn(
                role="tool",
                tool_results=[ToolResult(tool_call, {"result": {"departures": []}})],
            ),
        ],
    )
    model, tool = rec.body["contents"][1:]
    assert model == {
        "role": "model",
        "parts": [{"functionCall": {"name": "next_departures", "args": {"stop_id": "a"}}}],
    }
    assert tool == {
        "role": "user",
        "parts": [
            {
                "functionResponse": {
                    "name": "next_departures",
                    "response": {"result": {"departures": []}},
                    "id": "call-1",
                }
            }
        ],
    }


def test_function_response_without_call_id_omits_id(provider, monkeypatch):
    rec = use(monkeypatch, Recorder(text_payload({"text": "ok"})))
    tool_call = ToolCall("next_departures", {})
    generate(
        provider,
        [
            Turn(role="assistant", tool_calls=[tool_call]),
            Turn(role="tool", tool_results=[ToolResult(tool_call, {"error": "x"})]),
        ],
    )
    assert "id" not in rec.body["contents"][1]["parts"][0]["functionResponse"]


def test_raw_model_parts_are_sent_back_unchanged(provider, monkeypatch):
    rec = use(monkeypatch, Recorder(text_payload({"text": "ok"})))
    raw = {
        "role": "model",
        "parts": [
            {"functionCall": {"name": "next_departures", "args": {}}, "thoughtSignature": "SIG"}
        ],
    }
    generate(
        provider,
        [Turn(role="assistant", tool_calls=[ToolCall("next_departures", {})], raw=raw)],
    )
    assert rec.body["contents"][0] == {"role": "model", "parts": raw["parts"]}


def test_multiple_function_responses_share_one_user_turn(provider, monkeypatch):
    rec = use(monkeypatch, Recorder(text_payload({"text": "ok"})))
    calls = [ToolCall("a", {}), ToolCall("b", {})]
    generate(
        provider,
        [Turn(role="tool", tool_results=[ToolResult(c, {"result": 1}) for c in calls])],
    )
    assert len(rec.body["contents"]) == 1
    assert len(rec.body["contents"][0]["parts"]) == 2


# --------------------------------------------------------------------------- response


def test_text_reply(provider, monkeypatch):
    use(monkeypatch, Recorder(text_payload({"text": "Hello "}, {"text": "world"})))
    reply = generate(provider)
    assert reply.text == "Hello world"
    assert reply.tool_calls == ()
    assert reply.raw is None


def test_function_call_reply_keeps_raw_parts(provider, monkeypatch):
    parts = [
        {
            "functionCall": {"name": "next_departures", "args": {"stop_id": "a"}, "id": "c9"},
            "thoughtSignature": "SIG",
        }
    ]
    use(monkeypatch, Recorder(text_payload(*parts)))
    reply = generate(provider)
    assert reply.tool_calls == (ToolCall("next_departures", {"stop_id": "a"}, id="c9"),)
    assert reply.raw == {"role": "model", "parts": parts}


def test_thought_parts_are_skipped(provider, monkeypatch):
    use(
        monkeypatch,
        Recorder(text_payload({"text": "secret reasoning", "thought": True}, {"text": "Answer"})),
    )
    assert generate(provider).text == "Answer"


def test_only_thoughts_is_an_error(provider, monkeypatch):
    use(monkeypatch, Recorder(text_payload({"text": "thinking", "thought": True})))
    with pytest.raises(ProviderError):
        generate(provider)


def test_function_call_with_bad_args_gets_empty_arguments(provider, monkeypatch):
    use(monkeypatch, Recorder(text_payload({"functionCall": {"name": "x", "args": "oops"}})))
    assert generate(provider).tool_calls[0].arguments == {}


def test_function_call_and_text_together_prefers_the_tool_call(provider, monkeypatch):
    use(
        monkeypatch,
        Recorder(
            text_payload({"text": "let me check"}, {"functionCall": {"name": "x", "args": {}}})
        ),
    )
    assert generate(provider).tool_calls


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"candidates": []},
        {"promptFeedback": {"blockReason": "SAFETY"}},
        {"candidates": [{"finishReason": "SAFETY"}]},
        {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]},
        {"candidates": [{"content": {"parts": [{"text": "   "}]}}]},
        [1, 2],
        "text",
    ],
)
def test_unusable_responses_are_provider_errors(provider, monkeypatch, payload):
    use(monkeypatch, Recorder(payload))
    with pytest.raises(ProviderError):
        generate(provider)


# ---------------------------------------------------------------------------- failures


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("refused"),
        TimeoutError("timed out"),
        ConnectionResetError("reset"),
        urllib.error.HTTPError("http://x", 429, "quota", {}, io.BytesIO(b"quota exceeded")),
        urllib.error.HTTPError("http://x", 500, "boom", {}, None),
        urllib.error.HTTPError("http://x", 403, "bad key", {}, io.BytesIO(KEY.encode())),
    ],
)
def test_network_and_http_errors_are_provider_errors(provider, monkeypatch, error):
    use(monkeypatch, Recorder(error=error))
    with pytest.raises(ProviderError) as info:
        generate(provider)
    assert KEY not in str(info.value)


@pytest.mark.parametrize("raw", [b"<html>nope</html>", b"", b"\xff\xfe", b"{"])
def test_garbage_body_is_a_provider_error(provider, monkeypatch, raw):
    use(monkeypatch, Recorder(raw=raw))
    with pytest.raises(ProviderError):
        generate(provider)


def test_missing_key_raises_provider_error(settings, monkeypatch):
    settings.GEMINI_API_KEY = ""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ProviderError):
        GeminiProvider()


def test_key_and_model_come_from_settings(settings):
    settings.GEMINI_API_KEY = "from-settings"
    settings.GEMINI_MODEL = "gemini-custom"
    provider = GeminiProvider()
    assert provider.api_key == "from-settings"
    assert provider.model == "gemini-custom"


def test_key_falls_back_to_the_environment(settings, monkeypatch):
    settings.GEMINI_API_KEY = ""
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert GeminiProvider().api_key == "from-env"


def test_model_name_cannot_inject_url_parts(settings, monkeypatch):
    settings.GEMINI_API_URL = "https://gemini.example.invalid/v1beta"
    rec = use(monkeypatch, Recorder(text_payload({"text": "ok"})))
    GeminiProvider(api_key=KEY, model="../evil?x=1").generate("S", [Turn("user", "Hi")], [], 5)
    assert rec.requests[0].full_url.count("?") == 0
    assert "/../" not in rec.requests[0].full_url
