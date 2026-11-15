"""503 journey_planner_unavailable for every kind of OTP failure (urllib is mocked)."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from journeys.tests.conftest import post

pytestmark = pytest.mark.django_db

REQUEST = {"from": {"stop_id": "tt_main:S1"}, "to": {"stop_id": "tt_main:S4"}}


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _ok(payload):
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def opener(request, timeout=None):
        return _Response(raw)

    return opener


def _raise(exc):
    def opener(request, timeout=None):
        raise exc

    return opener


FAILURES = {
    "connection_refused": _raise(urllib.error.URLError(ConnectionRefusedError("refused"))),
    "timeout": _raise(TimeoutError("timed out")),
    "http_500": _raise(urllib.error.HTTPError("http://otp", 500, "boom", {}, None)),
    "graphql_errors": _ok({"errors": [{"message": "secret internal stack"}], "data": None}),
    "garbage_json": _ok(b"<html>not json</html>"),
    "json_array": _ok([1, 2, 3]),
    "no_data": _ok({"data": None}),
}


@pytest.mark.parametrize("name", list(FAILURES))
def test_otp_failure_gives_503(client, dataset, otp_env, monkeypatch, name):
    monkeypatch.setattr("urllib.request.urlopen", FAILURES[name])
    response = post(client, REQUEST)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "journey_planner_unavailable"
    text = response.content.decode()
    assert "secret" not in text
    assert "refused" not in text


def test_unexpected_otp_shape_gives_503(client, dataset, otp_env, monkeypatch):
    # Valid GraphQL envelope, but an itinerary that lacks required fields.
    bad = {"data": {"planConnection": {"edges": [{"node": {"legs": [{"mode": "WALK"}]}}]}}}
    monkeypatch.setattr("urllib.request.urlopen", _ok(bad))
    response = post(client, REQUEST)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "journey_planner_unavailable"


def test_missing_otp_url_gives_503(client, dataset, monkeypatch):
    monkeypatch.delenv("OTP_URL_TTVILLE", raising=False)
    response = post(client, REQUEST)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "journey_planner_unavailable"


def test_blank_otp_url_gives_503(client, dataset, monkeypatch):
    monkeypatch.setenv("OTP_URL_TTVILLE", "  ")
    assert post(client, REQUEST).status_code == 503


def test_503_message_is_translated(client, dataset, monkeypatch):
    monkeypatch.delenv("OTP_URL_TTVILLE", raising=False)
    en = post(client, REQUEST, lang="en").json()["error"]["message"]
    pl = post(client, REQUEST, lang="pl").json()["error"]["message"]
    assert en == "The journey planner is unavailable. Try again later."
    assert pl and pl != en


def test_validation_message_is_translated(client, dataset, otp_env):
    data = {"from": {"stop_id": "tt_main:NOPE"}, "to": {"stop_id": "tt_main:S4"}}
    en = post(client, data, lang="en").json()["error"]["details"]
    pl = post(client, data, lang="pl").json()["error"]["details"]
    assert en != pl


def test_request_is_posted_to_graphql_path_with_timeout(client, dataset, otp_env, monkeypatch):
    seen = []

    def opener(request, timeout=None):
        seen.append((request.full_url, request.get_method(), timeout))
        return _Response(json.dumps({"data": {"planConnection": {"edges": []}}}).encode())

    monkeypatch.setattr("urllib.request.urlopen", opener)
    response = post(client, REQUEST)
    assert response.status_code == 200
    assert {url for url, _, _ in seen} == {"http://otp.invalid:8080/otp/gtfs/v1"}
    assert all(method == "POST" and timeout == 10.0 for _, method, timeout in seen)
