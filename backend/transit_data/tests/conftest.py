"""Shared helpers for the realtime collector tests (no network, no real feeds)."""

from __future__ import annotations

import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from google.transit import gtfs_realtime_pb2 as pb

from cities import registry

FIXTURES = Path(__file__).parent / "fixtures"

TESTVILLE_URL = "http://testville.invalid/TripUpdates.pb"
KRAKOW_TRAM_FEED = "ztp_tram_trip_updates"
KRAKOW_BUS_FEED = "ztp_bus_trip_updates"


def epoch(*args) -> int:
    """Epoch seconds of a UTC datetime given as (y, m, d, h, mi[, s])."""
    return int(datetime(*args, tzinfo=UTC).timestamp())


def make_message(trips, timestamp: int | None = None) -> bytes:
    """Build a serialized TripUpdates FeedMessage.

    ``trips`` is a list of dicts: trip_id, start_date, route_id, direction, vehicle,
    canceled, stops. A stop is a dict: stop_id, seq, arr, dep (each ``(time, delay)`` where
    either part may be None; ``"empty"`` gives an empty event), rel.
    """
    message = pb.FeedMessage()
    message.header.gtfs_realtime_version = "2.0"
    if timestamp is not None:
        message.header.timestamp = timestamp
    for i, spec in enumerate(trips):
        entity = message.entity.add()
        entity.id = str(i)
        update = entity.trip_update
        update.trip.trip_id = spec["trip_id"]
        if spec.get("start_date"):
            update.trip.start_date = spec["start_date"]
        if spec.get("route_id"):
            update.trip.route_id = spec["route_id"]
        if spec.get("direction") is not None:
            update.trip.direction_id = spec["direction"]
        if spec.get("canceled"):
            update.trip.schedule_relationship = pb.TripDescriptor.CANCELED
        if spec.get("vehicle"):
            update.vehicle.id = spec["vehicle"]
        for stop in spec.get("stops", []):
            stu = update.stop_time_update.add()
            if stop.get("stop_id") is not None:
                stu.stop_id = stop["stop_id"]
            if stop.get("seq") is not None:
                stu.stop_sequence = stop["seq"]
            if stop.get("rel") is not None:
                stu.schedule_relationship = stop["rel"]
            for name, key in (("arrival", "arr"), ("departure", "dep")):
                value = stop.get(key)
                if value is None:
                    continue
                event = getattr(stu, name)
                if value == "empty":
                    event.SetInParent()
                    continue
                time_value, delay = value
                if time_value is not None:
                    event.time = time_value
                if delay is not None:
                    event.delay = delay
    return message.SerializeToString()


@pytest.fixture
def tram_pb() -> bytes:
    return (FIXTURES / "krakow_tram_trip_updates.pb").read_bytes()


@pytest.fixture
def bus_pb() -> bytes:
    return (FIXTURES / "krakow_bus_trip_updates.pb").read_bytes()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any test that forgets to mock HTTP fails loudly instead of hitting a server."""

    def blocked(*args, **kwargs):
        raise AssertionError("network access attempted in a test")

    monkeypatch.setattr(urllib.request, "urlopen", blocked)


@pytest.fixture(autouse=True)
def feeds_never_stale(settings):
    """Recorded feeds have old header timestamps; stale handling has its own tests."""
    settings.TRANSIT_REALTIME_STALE_AFTER = 10**10


@pytest.fixture
def city_config(tmp_path, settings):
    """Registry with krakow, warszawa (no TripUpdates) and a synthetic city "testville"."""
    real = Path(settings.CITY_CONFIG_DIR)
    for name in ("krakow.yaml", "warszawa.yaml"):
        (tmp_path / name).write_text((real / name).read_text(encoding="utf-8"), encoding="utf-8")
    data = yaml.safe_load((real / "krakow.yaml").read_text(encoding="utf-8"))
    data["id"] = "testville"
    data["timezone"] = "Europe/Warsaw"
    data["feeds"] = {
        "gtfs_static": [],
        "gtfs_rt": [
            {"id": "tv_trip_updates", "entity": "trip_updates", "url": TESTVILLE_URL},
            {
                "id": "tv_vehicles",
                "entity": "vehicle_positions",
                "url": "http://testville.invalid/Vehicles.pb",
            },
            {"id": "tv_no_url", "entity": "trip_updates", "url": None},
        ],
        "other": [],
    }
    (tmp_path / "testville.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    settings.CITY_CONFIG_DIR = tmp_path
    registry.clear_cache()
    yield
    registry.clear_cache()


class Served(dict):
    """url -> bytes | Exception; ``requested`` lists the URLs that were fetched."""

    def __init__(self):
        super().__init__()
        self.requested: list[str] = []


@pytest.fixture
def served(monkeypatch):
    """Replace ``fetch_feed`` with a lookup in the returned ``Served`` mapping."""
    from transit_data import realtime

    responses = Served()

    def fake_fetch(url):
        responses.requested.append(url)
        value = responses[url]
        if isinstance(value, Exception):
            raise value
        return value, 200

    monkeypatch.setattr(realtime, "fetch_feed", fake_fetch)
    return responses


def get_feed(city_id: str, feed_id: str):
    city = registry.get_city(city_id)
    feed = next(f for f in city.feeds if f.id == feed_id)
    return city, feed


def krakow_trip_update_urls() -> dict[str, str]:
    """feed id -> URL for every Kraków TripUpdates feed in the shipped config."""
    city = registry.get_city("krakow")
    return {
        f.id: f.url
        for f in city.feeds
        if f.kind == "gtfs_rt" and f.entity == "trip_updates" and f.url
    }


# ----------------------------------------------------------------- static GTFS import


@pytest.fixture
def gtfs_city(tmp_path, settings):
    """Registry with krakow, warszawa and a synthetic city "gtfsville" with static feeds.

    gtfsville feeds: gv_main and gv_second (with URLs) and gv_no_url (``url: null``).
    """
    real = Path(settings.CITY_CONFIG_DIR)
    config_dir = tmp_path / "cities"
    config_dir.mkdir()
    for name in ("krakow.yaml", "warszawa.yaml"):
        (config_dir / name).write_text((real / name).read_text(encoding="utf-8"), encoding="utf-8")
    data = yaml.safe_load((real / "krakow.yaml").read_text(encoding="utf-8"))
    data["id"] = "gtfsville"
    data["timezone"] = "Europe/Warsaw"
    data["feeds"] = {
        "gtfs_static": [
            {"id": "gv_main", "url": "http://gtfsville.invalid/main.zip"},
            {"id": "gv_second", "url": "http://gtfsville.invalid/second.zip"},
            {"id": "gv_no_url", "url": None},
        ],
        "gtfs_rt": [],
        "other": [],
    }
    (config_dir / "gtfsville.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    settings.CITY_CONFIG_DIR = config_dir
    registry.clear_cache()
    yield
    registry.clear_cache()
