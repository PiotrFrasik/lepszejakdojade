"""GET /cities/{city}/stops/{stop_id}/departures/ (docs/api.md, "Stop departures", #73).

Fictional city "depville": static feeds dep_tram and dep_bus (both may use trip id "T1"),
realtime trip-update feeds dep_tram_tu -> dep_tram and dep_bus_tu -> dep_bus.
Fixed "now": Monday 2026-11-16 10:00 Europe/Warsaw (09:00 UTC, CET = +01:00).
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from cities import registry
from cities.registry import CityConfigError, all_cities
from transit_data.models import FeedFetch, ScheduleRelationship, StopEvent

from .conftest import Builder

pytestmark = pytest.mark.django_db

CITY = "depville"
TRAM, BUS = "dep_tram", "dep_bus"
TRAM_RT, BUS_RT = "dep_tram_tu", "dep_bus_tu"
NOW = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)  # 10:00 in Warsaw
DAY = date(2026, 11, 16)
P_TRAM = f"{TRAM}:P1"
P_BUS = f"{BUS}:P2"


def local(text, day=DAY):
    """ISO string with the Warsaw offset of ``HH:MM[:SS]`` on ``day`` (CET in November)."""
    if text.count(":") == 1:
        text += ":00"
    return f"{day.isoformat()}T{text}+01:00"


def utc(text, day=DAY):
    """UTC datetime of local Warsaw (CET) ``HH:MM`` on ``day``."""
    hours, minutes = (int(p) for p in text.split(":"))
    base = datetime(day.year, day.month, day.day, hours, minutes, tzinfo=UTC)
    return base - timedelta(hours=1)


@pytest.fixture
def make_city(tmp_path, settings):
    real = Path(settings.CITY_CONFIG_DIR)
    data = yaml.safe_load((real / "krakow.yaml").read_text(encoding="utf-8"))

    def make(realtime=True, rt_feeds="default"):
        data["id"] = CITY
        data["timezone"] = "Europe/Warsaw"
        data["vehicle_types"] = ["tram", "bus"]
        data["line_groups"] = [{"id": "day", "names": {"pl": "D", "en": "D"}, "colour": "#112233"}]
        data["line_group_rules"] = []
        data["realtime"] = {"departures": realtime, "vehicles": False}
        if rt_feeds == "default":
            rt_feeds = [
                {"id": TRAM_RT, "entity": "trip_updates", "url": "http://x.invalid/t.pb",
                 "static_feed": TRAM},
                {"id": BUS_RT, "entity": "trip_updates", "url": "http://x.invalid/b.pb",
                 "static_feed": BUS},
            ]  # fmt: skip
        data["feeds"] = {
            "gtfs_static": [
                {"id": TRAM, "url": "http://x.invalid/tram.zip"},
                {"id": BUS, "url": "http://x.invalid/bus.zip"},
            ],
            "gtfs_rt": rt_feeds,
            "other": [],
        }
        config_dir = tmp_path / "cities"
        config_dir.mkdir(exist_ok=True)
        (config_dir / f"{CITY}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
        settings.CITY_CONFIG_DIR = config_dir
        registry.clear_cache()

    make()
    yield make
    registry.clear_cache()


@pytest.fixture
def world(make_city, db):
    """Tram feed: P1 "Plaza" (platform_code A), P3 "Endpoint". Bus feed: P2 "Plaza" about
    30 m from P1 (stop code 02), P4 "Busend". Trips are added by the tests."""
    cache.clear()
    tram = Builder(TRAM, city_id=CITY)
    tram.calendar("WK", ["monday", "tuesday", "wednesday", "thursday", "friday"])
    tram.calendar(
        "ALL", ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    )
    stop = tram.stop("P1", "Plaza", 0, 0)
    stop.platform_code = "A"
    stop.save()
    tram.stop("P3", "Endpoint", 0.01, 0)
    tram.route("RT", "10", 0)
    bus = Builder(BUS, city_id=CITY)
    bus.calendar("WK", ["monday", "tuesday", "wednesday", "thursday", "friday"])
    bus.stop("P2", "Plaza", 0.0003, 0, code="02")
    bus.stop("P4", "Busend", 0.01, 0)
    bus.route("RB", "100", 3)
    yield tram, bus
    cache.clear()


@pytest.fixture
def freeze(monkeypatch):
    """Freezes the view's clock at NOW; returns a setter for another moment."""

    def set_now(moment=NOW):
        monkeypatch.setattr("timetable.views.timezone.now", lambda: moment)

    set_now()
    return set_now


def fresh_fetch(feed=TRAM_RT, status=FeedFetch.Status.OK, ago=timedelta(minutes=1)):
    return FeedFetch.objects.create(city_id=CITY, feed_id=feed, fetched_at=NOW - ago, status=status)


def event(trip_id, stop="P1", feed=TRAM_RT, seq=None, day=DAY, ago=timedelta(seconds=30), **kw):
    kw.setdefault("schedule_relationship", ScheduleRelationship.SCHEDULED)
    return StopEvent.objects.create(
        city_id=CITY, feed_id=feed, service_date=day, trip_id=trip_id, stop_id=stop,
        stop_sequence=seq, first_seen=NOW - timedelta(minutes=10), last_seen=NOW - ago, **kw
    )  # fmt: skip


def call(stop=P_TRAM, city=CITY, lang=None, **params):
    extra = {"HTTP_ACCEPT_LANGUAGE": lang} if lang else {}
    return APIClient().get(
        f"/api/v1/cities/{city}/stops/{stop}/departures/", params or None, **extra
    )


def body_of(stop=P_TRAM, **params):
    response = call(stop, **params)
    assert response.status_code == 200, response.content
    return response.json()


def trip(b, gtfs_id, start, route="RT", stops=("P1", "P3"), service="WK", **kw):
    return b.simple_trip(gtfs_id, route, service, list(stops), start, **kw)


def by_trip(body):
    return {d["trip_id"]: d for d in body["departures"]}


# ------------------------------------------------------------------ shape and basics


def test_response_shape_cache_header_and_stop_block(world, freeze):
    tram, _ = world
    trip(tram, "a", "10:05")
    response = call(P_TRAM)
    assert response.status_code == 200
    assert "max-age=15" in response["Cache-Control"]
    body = response.json()
    assert set(body) == {"stop", "generated_at", "realtime_available", "departures"}
    assert body["stop"]["id"] == P_TRAM
    assert body["stop"]["name"] == "Plaza"
    assert sorted(body["stop"]["stop_ids"]) == sorted([P_TRAM, P_BUS])
    assert body["generated_at"] == local("10:00")
    assert body["realtime_available"] is False
    (d,) = body["departures"]
    assert set(d) == {
        "line", "trip_id", "headsign", "platform_id", "platform_code", "scheduled",
        "expected", "delay_seconds", "status",
    }  # fmt: skip
    assert d["line"]["short_name"] == "10"
    assert d["trip_id"] == f"{TRAM}:a"
    assert d["platform_id"] == P_TRAM
    assert d["platform_code"] == "A"
    assert d["scheduled"] == local("10:05")
    assert (d["expected"], d["delay_seconds"], d["status"]) == (None, None, "scheduled")


def test_requested_id_is_echoed_and_whole_group_is_covered(world, freeze):
    tram, bus = world
    trip(tram, "a", "10:05")
    trip(bus, "b", "10:10", route="RB", stops=("P2", "P4"))
    from_bus = body_of(P_BUS)
    assert from_bus["stop"]["id"] == P_BUS
    assert set(by_trip(from_bus)) == {f"{TRAM}:a", f"{BUS}:b"}
    from_tram = body_of(P_TRAM)
    assert from_tram["stop"]["id"] == P_TRAM
    assert set(by_trip(from_tram)) == {f"{TRAM}:a", f"{BUS}:b"}


def test_empty_departures_is_200(world, freeze):
    assert body_of(P_TRAM)["departures"] == []


# ------------------------------------------------------------------ limit and errors


def test_default_limit_is_15_and_max_is_30(world, freeze):
    tram, _ = world
    for i in range(35):
        trip(tram, f"t{i}", f"10:{i + 1:02d}")
    assert len(body_of()["departures"]) == 15
    assert len(body_of(limit=30)["departures"]) == 30
    assert len(body_of(limit=2)["departures"]) == 2
    assert len(body_of(limit=1)["departures"]) == 1


@pytest.mark.parametrize("value", ["0", "31", "abc", "-1"])
def test_invalid_limit_is_400(world, freeze, value):
    response = call(P_TRAM, limit=value)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "limit" in error["details"]


@pytest.mark.parametrize(
    ("lang", "text"), [("pl", "Nie znaleziono przystanku."), ("en", "Stop not found.")]
)
def test_unknown_stop_is_404_translated(world, freeze, lang, text):
    response = call(f"{TRAM}:nope", lang=lang)
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert text in str(error)


def test_unknown_city_is_404(world, freeze):
    response = call(P_TRAM, city="nowhere")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_post_is_not_allowed(world, freeze):
    response = APIClient().post(f"/api/v1/cities/{CITY}/stops/{P_TRAM}/departures/")
    assert response.status_code == 405


# ------------------------------------------------------------------ time window


def test_window_bounds_and_sorting(world, freeze):
    tram, _ = world
    trip(tram, "too_old", "09:58")  # 2 min ago
    trip(tram, "just_gone", "09:59")  # exactly 1 min ago: included
    trip(tram, "later", "10:30")
    trip(tram, "soon", "10:01")
    trip(tram, "edge", "13:00")  # exactly now + 3 h: included
    trip(tram, "too_far", "13:01")
    got = [d["trip_id"] for d in body_of()["departures"]]
    assert got == [f"{TRAM}:{t}" for t in ("just_gone", "soon", "later", "edge")]


def test_late_trip_scheduled_earlier_still_appears_and_sorts_by_expected(world, freeze):
    tram, _ = world
    trip(tram, "late", "09:30")
    trip(tram, "ontime", "10:10")
    trip(tram, "gone", "09:00")  # 1 h ago, no live data: not shown
    fresh_fetch()
    event("late", "P1", seq=1, departure_delay=1800, departure_time=utc("10:00"))
    event("ontime", "P1", seq=1, departure_delay=1500, departure_time=utc("10:35"))
    body = body_of()
    assert [d["trip_id"] for d in body["departures"]] == [f"{TRAM}:late", f"{TRAM}:ontime"]
    late = body["departures"][0]
    assert late["scheduled"] == local("09:30")
    assert late["expected"] == local("10:00")
    assert late["delay_seconds"] == 1800
    assert late["status"] == "live"


def test_vehicle_running_early_out_of_window_is_dropped(world, freeze):
    tram, _ = world
    trip(tram, "early", "10:02")
    fresh_fetch()
    event("early", "P1", seq=1, departure_delay=-300, departure_time=utc("09:57"))
    assert body_of()["departures"] == []


def test_ties_are_sorted_by_scheduled_time(world, freeze):
    tram, _ = world
    trip(tram, "x_late_sched", "10:05")
    trip(tram, "y_early_sched", "10:00")
    fresh_fetch()
    event("y_early_sched", "P1", seq=1, departure_delay=300, departure_time=utc("10:05"))
    event("x_late_sched", "P1", seq=1, departure_delay=0, departure_time=utc("10:05"))
    ids = [d["trip_id"] for d in body_of()["departures"]]
    assert ids == [f"{TRAM}:y_early_sched", f"{TRAM}:x_late_sched"]


def test_trip_past_midnight_of_yesterdays_service_day(world, freeze):
    tram, _ = world
    # Service day Monday 2026-11-16, departure 24:15 = Tuesday 00:15 local.
    tram.trip("night", "RT", "WK", [("P1", "24:15", "24:15"), ("P3", "24:25", "24:25")])
    freeze(utc("00:10", date(2026, 11, 17)))
    (d,) = body_of()["departures"]
    assert d["trip_id"] == f"{TRAM}:night"
    assert d["scheduled"] == local("00:15", date(2026, 11, 17))


def test_tomorrows_early_trip_appears_late_in_the_evening(world, freeze):
    tram, _ = world
    trip(tram, "early", "00:30", service="ALL")
    freeze(utc("23:00"))  # Monday 23:00 local
    (d,) = body_of()["departures"]
    assert d["scheduled"] == local("00:30", date(2026, 11, 17))


def test_service_not_running_today_is_not_listed(world, freeze):
    tram, _ = world
    tram.calendar("SUNONLY", ["sunday"])
    trip(tram, "sun", "10:05", service="SUNONLY")
    assert body_of()["departures"] == []


def test_last_stop_of_trip_is_excluded(world, freeze):
    tram, _ = world
    trip(tram, "a", "10:05")  # ends at P3
    assert body_of(f"{TRAM}:P3")["departures"] == []


def test_no_pickup_is_excluded(world, freeze):
    tram, _ = world
    tram.trip(
        "np", "RT", "WK",
        [("P1", "10:05", "10:05", {"pickup_type": 1}), ("P3", "10:10", "10:10")],
    )  # fmt: skip
    tram.trip("ok", "RT", "WK", [("P1", "10:06", "10:06"), ("P3", "10:10", "10:10")])
    assert [d["trip_id"] for d in body_of()["departures"]] == [f"{TRAM}:ok"]


# ------------------------------------------------------------------ headsign / platform code


def test_headsign_fallback_chain(world, freeze):
    tram, _ = world
    tram.trip(
        "sh", "RT", "WK",
        [("P1", "10:01", "10:01", {"stop_headsign": "Stop HS"}), ("P3", "10:05", "10:05")],
        headsign="Trip HS",
    )  # fmt: skip
    tram.trip(
        "th", "RT", "WK", [("P1", "10:02", "10:02"), ("P3", "10:05", "10:05")],
        headsign="Trip HS",
    )  # fmt: skip
    tram.trip("last", "RT", "WK", [("P1", "10:03", "10:03"), ("P3", "10:05", "10:05")], headsign="")
    got = {d["trip_id"]: d["headsign"] for d in body_of()["departures"]}
    assert got == {f"{TRAM}:sh": "Stop HS", f"{TRAM}:th": "Trip HS", f"{TRAM}:last": "Endpoint"}


def test_platform_code_falls_back_to_stop_code_then_null(world, freeze):
    tram, bus = world
    trip(tram, "a", "10:05")  # platform_code "A"
    bus.stop("P5", "Plaza", 0.0003, 0.0001)  # same group, no codes
    trip(bus, "b", "10:06", route="RB", stops=("P2", "P4"))  # stop code "02"
    trip(bus, "c", "10:07", route="RB", stops=("P5", "P4"))
    cache.clear()
    codes = {d["trip_id"]: d["platform_code"] for d in body_of()["departures"]}
    assert codes == {f"{TRAM}:a": "A", f"{BUS}:b": "02", f"{BUS}:c": None}


# ------------------------------------------------------------------ realtime availability


def test_scheduled_when_city_has_no_realtime_departures(make_city, world, freeze):
    tram, _ = world
    make_city(realtime=False)
    trip(tram, "a", "10:05")
    fresh_fetch()
    event("a", "P1", seq=1, departure_delay=60, departure_time=utc("10:06"))
    body = body_of()
    assert body["realtime_available"] is False
    d = body["departures"][0]
    assert (d["status"], d["expected"], d["delay_seconds"]) == ("scheduled", None, None)


def test_scheduled_when_city_has_no_trip_update_feeds(make_city, world, freeze):
    tram, _ = world
    make_city(rt_feeds=[])
    trip(tram, "a", "10:05")
    assert body_of()["realtime_available"] is False


@pytest.mark.parametrize(
    "status", [FeedFetch.Status.STALE, FeedFetch.Status.ERROR, FeedFetch.Status.HTTP_ERROR]
)
def test_failed_fetch_does_not_count_as_available(world, freeze, status):
    tram, _ = world
    trip(tram, "a", "10:05")
    fresh_fetch(status=status)
    event("a", "P1", seq=1, departure_delay=60, departure_time=utc("10:06"))
    body = body_of()
    assert body["realtime_available"] is False
    assert body["departures"][0]["status"] == "scheduled"
    assert body["departures"][0]["delay_seconds"] is None


def test_old_fetch_does_not_count_as_available(world, freeze):
    tram, _ = world
    trip(tram, "a", "10:05")
    fresh_fetch(ago=timedelta(minutes=6))
    assert body_of()["realtime_available"] is False


@pytest.mark.parametrize("status", [FeedFetch.Status.OK, FeedFetch.Status.UNCHANGED])
def test_ok_and_unchanged_fetches_count(world, freeze, status):
    tram, _ = world
    trip(tram, "a", "10:05")
    fresh_fetch(status=status)
    assert body_of()["realtime_available"] is True


def test_fetch_of_another_city_or_feed_does_not_count(world, freeze):
    FeedFetch.objects.create(
        city_id="elsewhere", feed_id=TRAM_RT, fetched_at=NOW, status=FeedFetch.Status.OK
    )
    FeedFetch.objects.create(
        city_id=CITY, feed_id="unrelated", fetched_at=NOW, status=FeedFetch.Status.OK
    )
    assert body_of()["realtime_available"] is False


# ------------------------------------------------------------------ live matching


@pytest.fixture
def live(world, freeze):
    fresh_fetch()
    fresh_fetch(feed=BUS_RT)
    return world


def test_live_departure_with_time_and_delay(live):
    tram, _ = live
    trip(tram, "a", "10:05")
    event("a", "P1", seq=1, departure_time=utc("10:07"), departure_delay=120)
    body = body_of()
    assert body["realtime_available"] is True
    (d,) = body["departures"]
    assert (d["status"], d["expected"], d["delay_seconds"]) == ("live", local("10:07"), 120)
    assert d["scheduled"] == local("10:05")


def test_delay_is_computed_when_only_time_is_given(live):
    tram, _ = live
    trip(tram, "a", "10:05")
    event("a", "P1", seq=1, departure_time=utc("10:08"))
    (d,) = body_of()["departures"]
    assert (d["status"], d["expected"], d["delay_seconds"]) == ("live", local("10:08"), 180)


def test_time_is_computed_when_only_delay_is_given(live):
    tram, _ = live
    trip(tram, "a", "10:05")
    event("a", "P1", seq=1, departure_delay=90)
    (d,) = body_of()["departures"]
    assert (d["status"], d["expected"], d["delay_seconds"]) == ("live", local("10:06:30"), 90)


@pytest.mark.parametrize("delay", [0, -60])
def test_zero_and_negative_delay_are_live(live, delay):
    tram, _ = live
    trip(tram, "a", "10:05")
    event("a", "P1", seq=1, departure_delay=delay)
    (d,) = body_of()["departures"]
    assert d["status"] == "live"
    assert d["delay_seconds"] == delay


def test_arrival_values_are_used_when_departure_is_missing(live):
    tram, _ = live
    trip(tram, "a", "10:05")
    event("a", "P1", seq=1, arrival_delay=120)
    (d,) = body_of()["departures"]
    assert (d["status"], d["delay_seconds"]) == ("live", 120)


def test_skipped_stop_is_canceled_with_nulls(live):
    tram, _ = live
    trip(tram, "a", "10:05")
    event("a", "P1", seq=1, schedule_relationship=ScheduleRelationship.SKIPPED)
    (d,) = body_of()["departures"]
    assert (d["status"], d["expected"], d["delay_seconds"]) == ("canceled", None, None)
    assert d["scheduled"] == local("10:05")


def test_event_without_times_stays_scheduled(live):
    tram, _ = live
    trip(tram, "a", "10:05")
    event("a", "P1", seq=1)
    (d,) = body_of()["departures"]
    assert (d["status"], d["expected"], d["delay_seconds"]) == ("scheduled", None, None)


def test_event_older_than_5_minutes_is_ignored(live):
    tram, _ = live
    trip(tram, "a", "10:05")
    event("a", "P1", seq=1, departure_delay=600, ago=timedelta(minutes=5, seconds=1))
    (d,) = body_of()["departures"]
    assert d["status"] == "scheduled"


def test_event_of_another_service_day_is_ignored(live):
    tram, _ = live
    trip(tram, "a", "10:05")
    event("a", "P1", seq=1, departure_delay=600, day=DAY - timedelta(days=1))
    (d,) = body_of()["departures"]
    assert d["status"] == "scheduled"


def test_event_of_another_stop_is_ignored(live):
    tram, _ = live
    trip(tram, "a", "10:05")
    event("a", "P3", seq=2, departure_delay=600)
    (d,) = body_of()["departures"]
    assert d["status"] == "scheduled"


def test_stop_sequence_match_is_preferred(live):
    tram, _ = live
    trip(tram, "a", "10:05")
    event("a", "P1", seq=7, departure_delay=999)  # a different visit of the same stop
    event("a", "P1", seq=1, departure_delay=60)
    event("a", "P1", seq=None, departure_delay=500)
    (d,) = body_of()["departures"]
    assert d["delay_seconds"] == 60


def test_event_without_stop_sequence_is_the_fallback(live):
    tram, _ = live
    trip(tram, "a", "10:05")
    event("a", "P1", seq=None, departure_delay=240)
    (d,) = body_of()["departures"]
    assert (d["status"], d["delay_seconds"]) == ("live", 240)


def test_same_trip_id_in_other_feed_pair_does_not_cross_match(live):
    tram, bus = live
    trip(tram, "T1", "10:05")
    trip(bus, "T1", "10:10", route="RB", stops=("P2", "P4"))
    event("T1", "P2", feed=BUS_RT, seq=1, departure_delay=60)  # the bus trip's own event
    event("T1", "P1", feed=BUS_RT, seq=1, departure_delay=999)  # tram stop id, wrong feed
    event("T1", "P2", feed=TRAM_RT, seq=1, departure_delay=888)  # bus stop id, wrong feed
    got = by_trip(body_of())
    tram_dep, bus_dep = got[f"{TRAM}:T1"], got[f"{BUS}:T1"]
    assert (tram_dep["status"], tram_dep["delay_seconds"]) == ("scheduled", None)
    assert (bus_dep["status"], bus_dep["delay_seconds"]) == ("live", 60)


def test_realtime_trip_updates_feed_without_static_link_is_rejected(make_city):
    with pytest.raises(CityConfigError, match=r"gtfs_rt\[0\]\.static_feed.*required.*t_rt"):
        make_city(rt_feeds=[{"id": "t_rt", "entity": "trip_updates", "url": "http://x.invalid/t"}])
        registry.get_city(CITY)


def test_loop_trip_second_call_stays_scheduled_when_only_first_has_an_event(live):
    tram, _ = live
    # One trip calling twice at P1 (sequences 1 and 3), then P3.
    tram.trip(
        "loop", "RT", "WK",
        [("P1", "10:05", "10:05"), ("P3", "10:10", "10:10"), ("P1", "10:20", "10:20"),
         ("P3", "10:30", "10:30")],
    )  # fmt: skip
    event("loop", "P1", seq=1, departure_delay=120)
    got = sorted(body_of()["departures"], key=lambda d: d["scheduled"])
    assert [(d["scheduled"], d["status"], d["delay_seconds"]) for d in got] == [
        (local("10:05"), "live", 120),
        (local("10:20"), "scheduled", None),
    ]


def test_event_with_other_stop_sequence_is_not_a_fallback(live):
    tram, _ = live
    trip(tram, "a", "10:05")
    event("a", "P1", seq=5, departure_delay=300)
    (d,) = body_of()["departures"]
    assert (d["status"], d["delay_seconds"]) == ("scheduled", None)


# ------------------------------------------------------------------ DST

# (now in UTC, trip id, expected local ISO with offset). Service "ALL" runs every day.
DST_CASES = [
    # Spring forward, Sunday 2026-03-29 (02:00 CET -> 03:00 CEST).
    (datetime(2026, 3, 28, 23, 0, tzinfo=UTC), "mar_sat_2430", "2026-03-29T00:30:00+01:00"),
    (datetime(2026, 3, 28, 23, 0, tzinfo=UTC), "mar_sun_0330", "2026-03-29T03:30:00+02:00"),
    (datetime(2026, 3, 29, 22, 0, tzinfo=UTC), "mar_sun_2430", "2026-03-30T00:30:00+02:00"),
    # Fall back, Sunday 2026-10-25 (03:00 CEST -> 02:00 CET).
    (datetime(2026, 10, 24, 22, 0, tzinfo=UTC), "oct_sat_2430", "2026-10-25T00:30:00+02:00"),
    (datetime(2026, 10, 25, 1, 0, tzinfo=UTC), "oct_sun_0330", "2026-10-25T03:30:00+01:00"),
    (datetime(2026, 10, 25, 22, 0, tzinfo=UTC), "oct_sun_2430", "2026-10-26T00:30:00+01:00"),
]


@pytest.mark.parametrize(("now", "trip_id", "expected"), DST_CASES)
def test_departures_around_dst_changes(world, freeze, now, trip_id, expected):
    tram, _ = world
    clock = "24:30" if trip_id.endswith("2430") else "03:30"
    tram.trip(trip_id, "RT", "ALL", [("P1", clock, clock), ("P3", "27:00", "27:00")])
    freeze(now)
    got = by_trip(body_of())
    assert got[f"{TRAM}:{trip_id}"]["scheduled"] == expected


# ------------------------------------------------------------------ query count


def test_query_count_does_not_grow_with_trips(live):
    tram, _ = live
    trip(tram, "a0", "10:05")
    event("a0", "P1", seq=1, departure_delay=60)
    with CaptureQueriesContext(connection) as small:
        assert call().status_code == 200
    for i in range(1, 25):
        trip(tram, f"a{i}", f"10:{5 + i:02d}", headsign="")
        event(f"a{i}", "P1", seq=1, departure_delay=60)
    cache.clear()
    with CaptureQueriesContext(connection) as big:
        response = call(limit=30)
    assert len(response.json()["departures"]) == 25
    assert len(big) <= len(small) + 2  # the blank-headsign fallback adds at most a query
    assert len(big) < 25


# ------------------------------------------------------------------ registry validation


def _registry_city(tmp_path, settings, rt, departures=True):
    path = Path(settings.CITY_CONFIG_DIR) / "krakow.yaml"
    data = yaml.safe_load(path.read_text("utf-8"))
    data["id"] = "regville"
    data["realtime"] = {"departures": departures, "vehicles": False}
    data["feeds"] = {
        "gtfs_static": [{"id": "s1", "url": "http://x.invalid/s.zip"}],
        "gtfs_rt": [rt],
        "other": [],
    }
    (tmp_path / "regville.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    settings.CITY_CONFIG_DIR = tmp_path
    registry.clear_cache()


RT_FEED = {"id": "r1", "entity": "trip_updates", "url": "http://x.invalid/r.pb"}


def test_static_feed_is_parsed(tmp_path, settings):
    _registry_city(tmp_path, settings, {**RT_FEED, "static_feed": "s1"})
    (rt,) = [f for f in registry.get_city("regville").feeds if f.kind == "gtfs_rt"]
    assert rt.static_feed == "s1"
    registry.clear_cache()


def test_static_feed_is_optional(tmp_path, settings):
    _registry_city(tmp_path, settings, RT_FEED, departures=False)
    (rt,) = [f for f in registry.get_city("regville").feeds if f.kind == "gtfs_rt"]
    assert rt.static_feed is None
    registry.clear_cache()


def test_unknown_static_feed_is_rejected(tmp_path, settings):
    _registry_city(tmp_path, settings, {**RT_FEED, "static_feed": "nope"})
    with pytest.raises(CityConfigError, match=r"gtfs_rt\[0\]\.static_feed"):
        all_cities()
    registry.clear_cache()


def test_static_feed_is_optional_on_other_entities_even_with_departures(tmp_path, settings):
    feed = {**RT_FEED, "entity": "vehicle_positions"}
    _registry_city(tmp_path, settings, feed, departures=True)
    (rt,) = [f for f in registry.get_city("regville").feeds if f.kind == "gtfs_rt"]
    assert rt.static_feed is None
    registry.clear_cache()


def test_trip_updates_feed_requires_static_feed_when_departures_are_on(tmp_path, settings):
    _registry_city(tmp_path, settings, RT_FEED, departures=True)
    with pytest.raises(
        CityConfigError,
        match=r"feeds\.gtfs_rt\[0\]\.static_feed: required on trip_updates feed 'r1' "
        r"when realtime\.departures is true",
    ):
        all_cities()
    registry.clear_cache()


def test_shipped_krakow_realtime_feeds_point_to_static_feeds():
    registry.clear_cache()
    city = registry.get_city("krakow")
    static_ids = {f.id for f in city.feeds if f.kind == "gtfs_static"}
    realtime = [f for f in city.feeds if f.kind == "gtfs_rt"]
    assert realtime
    assert all(f.static_feed in static_ids for f in realtime)
    tram_updates = next(f for f in realtime if f.id == "ztp_tram_trip_updates")
    assert tram_updates.static_feed == "ztp_tram"
