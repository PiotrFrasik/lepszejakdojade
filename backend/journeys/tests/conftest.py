"""Fixtures for the journey search tests: the ttville dataset and a fake OTP (never live)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

# Reuse the fictional city and its GTFS dataset from the timetable tests.
from timetable.tests.conftest import (  # noqa: F401
    BASE_LAT,
    BASE_LON,
    CITY,
    _clear_cache,
    city_config,
    dataset,
)

URL = f"/api/v1/cities/{CITY}/journeys/search/"
OTP_BASE = "http://otp.invalid:8080"


def place(name, lat, lon, stop=None):
    return {"name": name, "lat": lat, "lon": lon, "stop": {"gtfsId": stop} if stop else None}


def when(value):
    return {"scheduledTime": value, "estimated": None}


def walk_leg(start, end, frm, to, duration=300, distance=400, points=None):
    return {
        "mode": "WALK",
        "transitLeg": False,
        "duration": duration,
        "distance": distance,
        "start": when(start),
        "end": when(end),
        "from": frm,
        "to": to,
        "route": None,
        "trip": None,
        "headsign": None,
        "intermediatePlaces": [],
        "legGeometry": {"points": points} if points else None,
    }


def transit_leg(
    start,
    end,
    frm,
    to,
    route,
    mode="TRAM",
    duration=600,
    distance=3000,
    trip="tt_main:m1",
    headsign="Delta",
    intermediate=(),
    estimated_start=None,
):
    return {
        "mode": mode,
        "transitLeg": True,
        "duration": duration,
        "distance": distance,
        "start": {
            "scheduledTime": start,
            "estimated": {"time": estimated_start} if estimated_start else None,
        },
        "end": when(end),
        "from": frm,
        "to": to,
        "route": route,
        "trip": {"gtfsId": trip, "tripHeadsign": "Trip headsign"},
        "headsign": headsign,
        "intermediatePlaces": list(intermediate),
        "legGeometry": None,
    }


def route(gtfs_id="tt_main:R10", short="10", route_type=0, color="FF0000", text="FFFFFF", long=""):
    return {
        "gtfsId": gtfs_id,
        "shortName": short,
        "longName": long,
        "type": route_type,
        "color": color,
        "textColor": text,
    }


def itinerary(start, end, legs, duration=None):
    return {"start": start, "end": end, "duration": duration or 1200, "legs": legs}


def plan(*nodes):
    return {"planConnection": {"edges": [{"node": n} for n in nodes]}}


def direct(duration, distance):
    return plan(
        {
            "start": "2026-11-16T07:00:00Z",
            "end": "2026-11-16T08:00:00Z",
            "duration": duration,
            "legs": [{"distance": distance}],
        }
    )


class FakeOtp:
    """Stands in for ``journeys.otp.graphql``; records every call."""

    def __init__(self):
        self.transit = plan()
        self.walk = direct(1800, 2000)
        self.bike = direct(600, 2200)
        self.calls: list[dict] = []
        self.urls: list[str] = []

    def __call__(self, base_url, query, variables):
        self.urls.append(base_url)
        self.calls.append(variables)
        modes = variables["modes"]
        if modes.get("directOnly"):
            return self.walk if modes["direct"] == ["WALK"] else self.bike
        return self.transit

    @property
    def transit_call(self):
        return next(c for c in self.calls if not c["modes"].get("directOnly"))

    def direct_call(self, mode):
        return next(c for c in self.calls if c["modes"].get("direct") == [mode])


@pytest.fixture
def otp_env(monkeypatch):
    monkeypatch.setenv("OTP_URL_TTVILLE", OTP_BASE)


@pytest.fixture
def fake_otp(dataset, otp_env, monkeypatch):  # noqa: F811
    fake = FakeOtp()
    monkeypatch.setattr("journeys.otp.graphql", fake)
    return fake


@pytest.fixture
def client():
    return APIClient()


def body(**overrides):
    """A valid request: stop S1 to stop S4."""
    data = {
        "from": {"stop_id": "tt_main:S1"},
        "to": {"stop_id": "tt_main:S4"},
        "time": "2026-11-16T08:00:00+01:00",
    }
    data.update(overrides)
    return data


def post(client, data, lang=None, city=CITY):
    extra = {"HTTP_ACCEPT_LANGUAGE": lang} if lang else {}
    return client.post(f"/api/v1/cities/{city}/journeys/search/", data, format="json", **extra)
