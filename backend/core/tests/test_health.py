"""Tests for GET /api/v1/health/ and the contract error format."""

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

URL = "/api/v1/health/"
BACKEND_DIR = Path(__file__).resolve().parents[2]
SECRET = "super-secret-redis-password"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def ok_checks(monkeypatch):
    monkeypatch.setattr("core.views.check_database", lambda: "ok")
    monkeypatch.setattr("core.views.check_redis", lambda: "ok")


def assert_error_format(body, code=None):
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    if code:
        assert body["error"]["code"] == code


def test_health_ok_exact_body(client, ok_checks, settings):
    settings.APP_VERSION = "9.9.9"
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok"},
        "version": "9.9.9",
    }


@pytest.mark.django_db
def test_health_real_database_check_ok(client, monkeypatch):
    monkeypatch.setattr("core.views.check_redis", lambda: "ok")
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json()["checks"]["database"] == "ok"


def test_health_requires_no_auth(client, ok_checks):
    assert client.get(URL).status_code == 200


def test_health_503_when_redis_down(client, monkeypatch):
    monkeypatch.setattr("core.views.check_database", lambda: "ok")
    monkeypatch.setattr("core.views.check_redis", lambda: "error")
    response = client.get(URL)
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["checks"] == {"database": "ok", "redis": "error"}
    assert set(body) == {"status", "checks", "version"}


def test_health_503_when_database_down(client, monkeypatch):
    monkeypatch.setattr("core.views.check_database", lambda: "error")
    monkeypatch.setattr("core.views.check_redis", lambda: "ok")
    response = client.get(URL)
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["checks"] == {"database": "error", "redis": "ok"}


def test_health_database_exception_is_hidden_and_logged(client, monkeypatch, caplog):
    def boom():
        raise RuntimeError(f"postgres://user:{SECRET}@db:5432/x unreachable")

    monkeypatch.setattr("core.views.connection.cursor", boom)
    monkeypatch.setattr("core.views.check_redis", lambda: "ok")
    with caplog.at_level(logging.ERROR):
        response = client.get(URL)
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "error"
    assert SECRET not in response.content.decode()
    assert "unreachable" not in response.content.decode()
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


def test_health_redis_exception_is_hidden_and_logged(client, monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise ConnectionError(f"redis://:{SECRET}@redis:6379/0 refused")

    monkeypatch.setattr("core.views.redis.Redis.from_url", boom)
    monkeypatch.setattr("core.views.check_database", lambda: "ok")
    with caplog.at_level(logging.ERROR):
        response = client.get(URL)
    assert response.status_code == 503
    body = response.content.decode()
    assert response.json()["checks"]["redis"] == "error"
    assert SECRET not in body and "refused" not in body and "redis://" not in body
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_health_only_get_allowed(client, ok_checks, method):
    response = getattr(client, method)(URL)
    assert response.status_code == 405
    assert_error_format(response.json(), "method_not_allowed")


def test_unknown_api_path_returns_json_404(client):
    with override_settings(DEBUG=False):
        response = client.get("/api/v1/does-not-exist/")
    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    assert_error_format(response.json(), "not_found")


def test_unknown_non_api_path_is_not_json_contract(client):
    response = client.get("/nope/")
    assert response.status_code == 404
    assert "error" not in response.content.decode()[:20]


def test_405_message_follows_accept_language(client, ok_checks):
    pl = client.post(URL, HTTP_ACCEPT_LANGUAGE="pl").json()["error"]["message"]
    en = client.post(URL, HTTP_ACCEPT_LANGUAGE="en").json()["error"]["message"]
    assert pl != en
    assert "not allowed" in en.lower()
    assert "niedozwolona" in pl.lower() or "metoda" in pl.lower()


def test_404_message_follows_accept_language(client):
    pl = client.get("/api/v1/nope/", HTTP_ACCEPT_LANGUAGE="pl").json()["error"]["message"]
    en = client.get("/api/v1/nope/", HTTP_ACCEPT_LANGUAGE="en").json()["error"]["message"]
    assert en == "Not found."
    assert pl != en


def test_default_language_is_polish(client, ok_checks):
    default = client.post(URL).json()["error"]["message"]
    pl = client.post(URL, HTTP_ACCEPT_LANGUAGE="pl").json()["error"]["message"]
    assert default == pl


def test_schema_includes_health(client):
    response = client.get("/api/schema/")
    assert response.status_code == 200
    assert "/api/v1/health/" in response.content.decode()


def test_test_settings_are_safe(settings):
    assert settings.DEBUG is False
    assert settings.SECRET_KEY


def _run_prod_settings(env_overrides):
    env = {k: v for k, v in os.environ.items() if not k.startswith("DJANGO_")}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "import config.settings.prod"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


def test_prod_settings_refuse_empty_secret_key():
    result = _run_prod_settings({"DJANGO_SECRET_KEY": "", "DJANGO_ALLOWED_HOSTS": "example.com"})
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_prod_settings_refuse_empty_allowed_hosts():
    result = _run_prod_settings({"DJANGO_SECRET_KEY": "x" * 50, "DJANGO_ALLOWED_HOSTS": ""})
    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in result.stderr


def test_prod_settings_load_with_secrets():
    result = _run_prod_settings(
        {"DJANGO_SECRET_KEY": "x" * 50, "DJANGO_ALLOWED_HOSTS": "example.com"}
    )
    assert result.returncode == 0, result.stderr
