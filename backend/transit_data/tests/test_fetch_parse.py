"""HTTP download and protobuf parsing (urllib is always mocked)."""

import io
import urllib.error
import urllib.request

import pytest

from transit_data.models import FeedFetch
from transit_data.realtime import FetchError, fetch_feed, parse_feed

from .conftest import epoch, make_message

URL = "http://feeds.invalid/TripUpdates.pb"


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def patch_urlopen(monkeypatch, result):
    seen = {}

    def fake(request, timeout=None):
        seen["request"] = request
        seen["timeout"] = timeout
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return seen


def test_fetch_returns_body_and_status(monkeypatch):
    seen = patch_urlopen(monkeypatch, FakeResponse(b"payload"))

    assert fetch_feed(URL) == (b"payload", 200)
    assert seen["request"].full_url == URL
    assert seen["timeout"] > 0


def test_fetch_sends_generic_user_agent(monkeypatch):
    seen = patch_urlopen(monkeypatch, FakeResponse(b"x"))
    fetch_feed(URL)
    agent = seen["request"].get_header("User-agent")
    assert agent and "@" not in agent and "lepsze" not in agent.lower()


def test_fetch_uses_configured_timeout(monkeypatch, settings):
    settings.TRANSIT_REALTIME_HTTP_TIMEOUT = 3
    seen = patch_urlopen(monkeypatch, FakeResponse(b"x"))
    fetch_feed(URL)
    assert seen["timeout"] == 3


@pytest.mark.parametrize("code", [403, 404, 500, 503])
def test_http_error_status_is_reported(monkeypatch, code):
    patch_urlopen(monkeypatch, urllib.error.HTTPError(URL, code, "err", {}, None))
    with pytest.raises(FetchError) as info:
        fetch_feed(URL)
    assert info.value.status == FeedFetch.Status.HTTP_ERROR
    assert info.value.http_status == code


@pytest.mark.parametrize(
    "exc",
    [
        urllib.error.URLError("name or service not known"),
        TimeoutError("timed out"),
        TimeoutError("timed out"),
        ConnectionResetError("reset"),
    ],
)
def test_network_failures_are_reported(monkeypatch, exc):
    patch_urlopen(monkeypatch, exc)
    with pytest.raises(FetchError) as info:
        fetch_feed(URL)
    assert info.value.status == FeedFetch.Status.NETWORK_ERROR


def test_oversized_download_is_rejected(monkeypatch, settings):
    settings.TRANSIT_REALTIME_MAX_BYTES = 10
    patch_urlopen(monkeypatch, FakeResponse(b"x" * 500))
    with pytest.raises(FetchError) as info:
        fetch_feed(URL)
    assert info.value.status == FeedFetch.Status.ERROR


def test_parse_valid_feed():
    body = make_message(
        [{"trip_id": "T", "stops": [{"stop_id": "A", "arr": (1, 0)}]}], epoch(2026, 1, 1, 0, 0)
    )
    message = parse_feed(body)
    assert len(message.entity) == 1
    assert message.header.timestamp == epoch(2026, 1, 1, 0, 0)


@pytest.mark.parametrize(
    "body",
    [b"", b"\xff\xfe\xfd garbage", b"<html>503 Service Unavailable</html>", b"\x0a"],
    ids=["empty", "binary-garbage", "html-page", "truncated"],
)
def test_parse_rejects_invalid_or_empty_body(body):
    with pytest.raises(FetchError) as info:
        parse_feed(body)
    assert info.value.status == FeedFetch.Status.PARSE_ERROR


def test_parse_rejects_truncated_valid_message():
    body = make_message(
        [{"trip_id": "T", "stops": [{"stop_id": "A", "arr": (5, 0)}]}], epoch(2026, 1, 1, 0, 0)
    )
    with pytest.raises(FetchError) as info:
        parse_feed(body[: len(body) // 2])
    assert info.value.status == FeedFetch.Status.PARSE_ERROR
