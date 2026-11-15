"""Fixtures for the assistant tests: the ttville dataset, a fake OTP and a scripted provider.
The real Gemini API is never called."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from rest_framework.test import APIClient

from assistant.tests.fakes import ScriptedProvider
from journeys.tests.conftest import fake_otp, otp_env  # noqa: F401
from timetable.tests.conftest import (  # noqa: F401
    CITY,
    _clear_cache,
    city_config,
    dataset,
)

URL = "/api/v1/assistant/chat/"
ZONE = ZoneInfo("Europe/Warsaw")


def at(text: str) -> datetime:
    """Local Warsaw time from ``YYYY-MM-DD HH:MM``."""
    return datetime.fromisoformat(text).replace(tzinfo=ZONE)


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def use_provider(settings, monkeypatch):
    """Install a ScriptedProvider as the configured provider and return it."""

    def install(*replies, repeat=False) -> ScriptedProvider:
        provider = ScriptedProvider(*replies, repeat=repeat)
        ScriptedProvider.current = provider
        settings.ASSISTANT_PROVIDER = "assistant.tests.fakes.current_provider"
        return provider

    yield install
    ScriptedProvider.current = None


@pytest.fixture
def fixed_now(monkeypatch):
    """Freeze the clock the chat uses for 'now' (the view does not accept it)."""

    def freeze(text: str) -> None:
        moment = at(text)

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return moment.astimezone(tz) if tz else moment

        monkeypatch.setattr("assistant.chat.datetime", FixedDatetime)

    return freeze


def chat(client, text="Hello", city=CITY, lang=None, messages=None, **extra):
    payload = {"city": city, "messages": messages or [{"role": "user", "text": text}]}
    headers = {"HTTP_ACCEPT_LANGUAGE": lang} if lang else {}
    return client.post(URL, payload, format="json", **headers, **extra)
