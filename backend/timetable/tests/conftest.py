"""Fictional city "ttville" with a small hand-built static GTFS dataset (no network).

Layout (all ids fictional):

feed tt_main (active), city config groups: day, night, agglomeration, replacement
  line 10 (tram, FF0000/FFFFFF), direction 0 main pattern S1 S2 S3 S4
    main trips (WEEKDAY): m1 05:12 (low floor), m2 06:00 (no pickup at S2), m3 07:00 (no
    departure at S2), m4 23:50, m5 24:15 (after midnight)
    short turn S2 S3: st1 09:00, st2 10:00 (WEEKDAY)
    depot D S1 S2 S3 S4: dp1 11:00 (WEEKDAY)
    other S1 X S3 S4: ot1 12:00 (WEEKDAY)
    SATURDAY: sa1 07:00 (main), SUNDAY: su1 08:00 (main)
  line 10 direction 1: S4 S3 S2 S1, d1 06:00 (WEEKDAY only)
  line 52 (tram, white colour), stop S3b: same name as S3, 100 m away
  line N1 (bus, black colour), stops at S3 (night group)
  line 99 (bus) at S3far (same name as S3 but about 500 m away) and line 77 (bus) at S3near
    (different name, 50 m away): neither is a transfer
  line 20 (tram), trips without direction_id (WEEKDAY)
  line M1 (metro) frequency based: template trip at S1 +0 s, S2 +180 s, 06:00-07:00 every 10 min
  line BLK (tram), trips with a blank headsign
  two lines without short name (one with a long name)
feed tt_second (active): lines 2 and 3 (bus)
feed tt_main older SUPERSEDED version: line OLD (must never appear)
feed not_in_config (active): line ZZ (must never appear)
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml
from django.contrib.gis.geos import LineString, Point
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from cities import registry
from transit_data.models import (
    Calendar,
    CalendarDate,
    FeedVersion,
    Frequency,
    Route,
    Shape,
    Stop,
    StopTime,
    Trip,
)

CITY = "ttville"
MAIN = "tt_main"
SECOND = "tt_second"

# 2026-11-16 is a Monday; 2026-11-11 (Wednesday) is a public holiday run as Sunday.
MONDAY = "2026-11-16"
FRIDAY = "2026-11-20"
SATURDAY = "2026-11-21"
SUNDAY = "2026-11-22"
HOLIDAY = "2026-11-11"
DST_START_SUNDAY = "2026-03-29"

DAY_COLOUR = "#112233"
NIGHT_COLOUR = "#f0e68c"

BASE_LAT = 50.0600
BASE_LON = 19.9400
LAT_PER_100M = 0.0009


def hms(text: str) -> int:
    hours, minutes, *rest = (int(part) for part in text.split(":"))
    return hours * 3600 + minutes * 60 + (rest[0] if rest else 0)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def city_config(tmp_path, settings):
    real = Path(settings.CITY_CONFIG_DIR)
    config_dir = tmp_path / "cities"
    config_dir.mkdir()
    data = yaml.safe_load((real / "krakow.yaml").read_text(encoding="utf-8"))
    data["id"] = CITY
    data["timezone"] = "Europe/Warsaw"
    data["vehicle_types"] = ["tram", "bus", "metro", "rail"]
    data["line_groups"] = [
        {"id": "day", "names": {"pl": "Dzienne", "en": "Day"}, "colour": DAY_COLOUR},
        {"id": "night", "names": {"pl": "Nocne", "en": "Night"}, "colour": NIGHT_COLOUR},
        {"id": "agglomeration", "names": {"pl": "Aglo", "en": "Agglo"}, "colour": "#445566"},
        {"id": "replacement", "names": {"pl": "Zast", "en": "Repl"}, "colour": "#778899"},
    ]
    data["line_group_rules"] = [
        {"group": "night", "short_name": "N\\d+"},
        {"group": "agglomeration", "feeds": [SECOND]},
        {"group": "replacement", "vehicle_types": ["bus"], "short_name": "9\\d"},
    ]
    data["feeds"] = {
        "gtfs_static": [
            {"id": MAIN, "url": "http://ttville.invalid/main.zip"},
            {"id": SECOND, "url": "http://ttville.invalid/second.zip"},
        ],
        "gtfs_rt": [],
        "other": [],
    }
    (config_dir / f"{CITY}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    settings.CITY_CONFIG_DIR = config_dir
    registry.clear_cache()
    yield
    registry.clear_cache()


class Builder:
    """Creates GTFS rows of one feed version directly through the ORM."""

    def __init__(self, feed_id: str, status=FeedVersion.Status.ACTIVE, city_id: str = CITY):
        self.version = FeedVersion.objects.create(
            city_id=city_id, feed_id=feed_id, status=status, downloaded_at=timezone.now()
        )
        self.city_id = city_id
        self.stops: dict[str, Stop] = {}
        self.routes: dict[str, Route] = {}
        self.trips: dict[str, Trip] = {}

    def calendar(self, service_id, days, start="2026-01-01", end="2026-12-31"):
        keys = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        Calendar.objects.create(
            feed_version=self.version,
            service_id=service_id,
            start_date=date.fromisoformat(start),
            end_date=date.fromisoformat(end),
            **{key: key in days for key in keys},
        )

    def exception(self, service_id, day, exception_type):
        CalendarDate.objects.create(
            feed_version=self.version,
            service_id=service_id,
            date=date.fromisoformat(day),
            exception_type=exception_type,
        )

    def stop(self, gtfs_id, name, dlat=0.0, dlon=0.0, code="", wheelchair=0):
        self.stops[gtfs_id] = Stop.objects.create(
            feed_version=self.version,
            city_id=self.city_id,
            gtfs_id=gtfs_id,
            name=name,
            code=code,
            point=Point(BASE_LON + dlon, BASE_LAT + dlat, srid=4326),
            wheelchair_boarding=wheelchair,
        )
        return self.stops[gtfs_id]

    def route(self, gtfs_id, short_name, route_type=0, color="", text_color="", long_name=""):
        self.routes[gtfs_id] = Route.objects.create(
            feed_version=self.version,
            city_id=self.city_id,
            gtfs_id=gtfs_id,
            short_name=short_name,
            long_name=long_name,
            route_type=route_type,
            color=color,
            text_color=text_color,
        )
        return self.routes[gtfs_id]

    def trip(
        self,
        gtfs_id,
        route,
        service,
        times,
        direction=0,
        headsign="Terminus A",
        wheelchair=0,
        shape=None,
    ):
        """``times``: list of ``(stop_gtfs_id, "HH:MM" arrival, "HH:MM" departure[, extra])``.

        A time may be None; ``extra`` is a dict of StopTime fields (e.g. pickup_type).
        """
        trip = Trip.objects.create(
            feed_version=self.version,
            gtfs_id=gtfs_id,
            route=self.routes[route],
            service_id=service,
            headsign=headsign,
            direction_id=direction,
            wheelchair_accessible=wheelchair,
            shape=shape,
        )
        for sequence, item in enumerate(times, start=1):
            stop_id, arrival, departure, *rest = item
            StopTime.objects.create(
                feed_version=self.version,
                trip=trip,
                stop=self.stops[stop_id],
                stop_sequence=sequence,
                arrival_time=hms(arrival) if arrival else None,
                departure_time=hms(departure) if departure else None,
                **(rest[0] if rest else {}),
            )
        self.trips[gtfs_id] = trip
        return trip

    def simple_trip(self, gtfs_id, route, service, stop_ids, start, step=5, **kwargs):
        """Trip calling at ``stop_ids`` from ``start`` ("HH:MM") every ``step`` minutes."""
        minutes = hms(start) // 60
        times = []
        for index, stop_id in enumerate(stop_ids):
            total = minutes + index * step
            clock = f"{total // 60}:{total % 60:02d}"
            times.append((stop_id, clock, clock))
        return self.trip(gtfs_id, route, service, times, **kwargs)


@pytest.fixture
def dataset(db, city_config):
    b = Builder(MAIN)
    b.calendar("WK", ["monday", "tuesday", "wednesday", "thursday", "friday"])
    b.calendar("SA", ["saturday"])
    b.calendar("SU", ["sunday"])
    # The holiday runs the Sunday timetable.
    b.exception("WK", HOLIDAY, 2)
    b.exception("SU", HOLIDAY, 1)

    b.stop("S1", "Alpha", 0, 0, code="01", wheelchair=1)
    b.stop("S2", "Beta", LAT_PER_100M * 10, 0, wheelchair=2)
    b.stop("S3", "Gamma", LAT_PER_100M * 20, 0)
    b.stop("S4", "Delta", LAT_PER_100M * 30, 0, code="04")
    b.stop("D", "Depot", -LAT_PER_100M * 10, 0)
    b.stop("X", "Xi", LAT_PER_100M * 5, 0.0005)
    b.stop("S3b", "Gamma", LAT_PER_100M * 21, 0)  # ~100 m from S3
    b.stop("S3far", "Gamma", LAT_PER_100M * 25, 0)  # ~500 m from S3
    b.stop("S3near", "Other name", LAT_PER_100M * 20.5, 0)  # ~50 m, different name

    shape = Shape.objects.create(
        feed_version=b.version,
        gtfs_id="SH1",
        geometry=LineString((19.94, 50.06), (19.95, 50.07), (19.96, 50.08), srid=4326),
    )

    b.route("R10", "10", 0, color="FF0000", text_color="FFFFFF", long_name="Alpha - Delta")
    main = ["S1", "S2", "S3", "S4"]
    b.simple_trip("m1", "R10", "WK", main, "05:12", wheelchair=1, shape=shape)
    b.trip(
        "m2",
        "R10",
        "WK",
        [
            ("S1", "06:00", "06:00"),
            ("S2", "06:05", "06:05", {"pickup_type": 1}),
            ("S3", "06:10", "06:10"),
            ("S4", "06:15", "06:15"),
        ],
        shape=shape,
    )
    b.trip(
        "m3",
        "R10",
        "WK",
        [
            ("S1", "07:00", "07:00"),
            ("S2", "07:05", None),
            ("S3", "07:10", "07:10"),
            ("S4", "07:15", "07:15"),
        ],
        shape=shape,
    )
    b.simple_trip("m4", "R10", "WK", main, "23:50", shape=shape)
    b.trip(
        "m5",
        "R10",
        "WK",
        [
            ("S1", "24:15", "24:15"),
            ("S2", "24:20", "24:20"),
            ("S3", "24:25", "24:25"),
            ("S4", "24:30", "24:30"),
        ],
        shape=shape,
    )
    b.simple_trip("st1", "R10", "WK", ["S2", "S3"], "09:00", headsign="Gamma short")
    b.simple_trip("st2", "R10", "WK", ["S2", "S3"], "10:00", headsign="Gamma short")
    b.simple_trip("dp1", "R10", "WK", ["D", "S1", "S2", "S3", "S4"], "11:00")
    b.simple_trip("ot1", "R10", "WK", ["S1", "X", "S3", "S4"], "12:00", headsign="Via Xi")
    b.simple_trip("sa1", "R10", "SA", main, "07:00")
    b.simple_trip("su1", "R10", "SU", main, "08:00")
    b.simple_trip(
        "d1", "R10", "WK", list(reversed(main)), "06:00", direction=1, headsign="Start place"
    )

    b.route("R52", "52", 0, color="FFFFFF", text_color="000000")
    b.simple_trip("t52", "R52", "WK", ["S3b", "S4"], "08:00")
    b.route("RN1", "N1", 3, color="000000")
    b.simple_trip("tn1", "RN1", "WK", ["S3", "S4"], "01:00")
    b.route("R99", "99", 3)
    b.simple_trip("t99", "R99", "WK", ["S3far", "S4"], "08:00")
    b.route("R77", "77", 3)
    b.simple_trip("t77", "R77", "WK", ["S3near", "S4"], "08:00")

    b.route("R20", "20", 0)
    b.trip(
        "n1",
        "R20",
        "WK",
        [("S1", "08:00", "08:00"), ("S2", "08:05", "08:05")],
        direction=None,
        headsign="Beta end",
    )

    b.route("RM1", "M1", 1)
    b.trip(
        "f1",
        "RM1",
        "WK",
        [("S1", "00:00", "00:00"), ("S2", "00:03", "00:03"), ("S4", "00:06", "00:06")],
        headsign="Beta metro",
    )
    Frequency.objects.create(
        feed_version=b.version,
        trip=b.trips["f1"],
        start_time=hms("06:00"),
        end_time=hms("07:00"),
        headway_secs=600,
    )

    b.route("RD1", "D1", 0)
    b.simple_trip("only1", "RD1", "WK", ["S2", "S1"], "09:30", direction=1, headsign="Alpha end")

    b.route("RBLK", "BLK", 0)
    b.simple_trip("blk1", "RBLK", "WK", ["S1", "S2"], "13:00", headsign="")

    b.route("RLONG", "", 0, long_name="Long Name Only")
    b.route("RNONE", "", 0)

    second = Builder(SECOND)
    second.route("B2", "2", 3)
    second.route("B3", "3", 3, color="00AA00")

    old = Builder(MAIN, status=FeedVersion.Status.SUPERSEDED)
    old.route("OLD", "OLD", 0)

    other = Builder("not_in_config")
    other.route("ZZ", "ZZ", 0)
    return b


@pytest.fixture
def client():
    return APIClient()


class Api:
    def __init__(self, client: APIClient):
        self.client = client

    def get(self, path: str, lang: str | None = None, city: str = CITY, **params):
        extra = {"HTTP_ACCEPT_LANGUAGE": lang} if lang else {}
        return self.client.get(f"/api/v1/cities/{city}/{path}", params or None, **extra)


@pytest.fixture
def api(client):
    return Api(client)


def today_in_city() -> date:
    return datetime.now(ZoneInfo("Europe/Warsaw")).date()
