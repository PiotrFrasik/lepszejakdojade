"""Collector against a real database: dedup, merge rules, FeedFetch statuses."""

import urllib.error
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from django.db import connection

from transit_data import realtime
from transit_data.models import FeedFetch, ScheduleRelationship, StopEvent
from transit_data.realtime import FetchError, collect_all_trip_updates, collect_feed

from .conftest import (
    KRAKOW_BUS_FEED,
    KRAKOW_TRAM_FEED,
    TESTVILLE_URL,
    epoch,
    get_feed,
    krakow_trip_update_urls,
    make_message,
)

pytestmark = pytest.mark.django_db

BUS_URL = "https://gtfs.ztp.krakow.pl/TripUpdates_A.pb"
TRAM_URL = "https://gtfs.ztp.krakow.pl/TripUpdates_T.pb"

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def clock(monkeypatch):
    """Controllable replacement for ``timezone.now`` used by the collector."""

    class Clock:
        now = T0

        def advance(self, **kwargs):
            self.now += timedelta(**kwargs)

    clock = Clock()
    monkeypatch.setattr(realtime.timezone, "now", lambda: clock.now)
    return clock


def trip(stops, trip_id="T1", **kwargs):
    return {"trip_id": trip_id, "start_date": "20261110", "stops": stops, **kwargs}


def poll(body, ts=None, feed_id=KRAKOW_BUS_FEED, city_id="krakow"):
    """Collect one message served for the given feed and return the FeedFetch row."""
    city, feed = get_feed(city_id, feed_id)
    return collect_feed(city, feed)


# ----------------------------------------------------------- full recorded feeds


def test_bus_recording_is_stored(served, bus_pb, clock):
    served[BUS_URL] = bus_pb

    log = poll(bus_pb)

    assert log.status == FeedFetch.Status.OK
    assert log.http_status == 200
    assert log.entity_count == 6
    assert log.stop_event_count == 95
    assert log.size_bytes == len(bus_pb)
    assert log.feed_timestamp == datetime.fromtimestamp(1794433999, tz=UTC)
    assert log.error == ""
    assert StopEvent.objects.filter(city_id="krakow", feed_id=KRAKOW_BUS_FEED).count() == 95
    assert FeedFetch.objects.count() == 1


def test_tram_recording_without_stop_sequence_is_stored(served, tram_pb, clock):
    served[TRAM_URL] = tram_pb

    log = poll(tram_pb, feed_id=KRAKOW_TRAM_FEED)

    assert log.status == FeedFetch.Status.OK
    assert log.stop_event_count == 50
    assert StopEvent.objects.count() == 50
    assert StopEvent.objects.filter(stop_sequence__isnull=False).count() == 0


def test_repolling_recorded_feed_does_not_duplicate_rows(served, tram_pb, bus_pb, clock):
    served[TRAM_URL] = tram_pb
    for _ in range(3):
        poll(tram_pb, feed_id=KRAKOW_TRAM_FEED)
        clock.advance(seconds=30)
    served[BUS_URL] = bus_pb
    # A new header timestamp is needed to be treated as a new message, so re-encode.
    poll(bus_pb)

    assert StopEvent.objects.filter(feed_id=KRAKOW_TRAM_FEED).count() == 50
    assert StopEvent.objects.filter(feed_id=KRAKOW_BUS_FEED).count() == 95


# ---------------------------------------------------------------- dedup/upsert


def test_dedup_keeps_first_seen_and_advances_last_seen(served, clock):
    t = epoch(2026, 11, 10, 12, 5)
    served[BUS_URL] = make_message(
        [trip([{"stop_id": "A", "seq": 1, "arr": (t, 60)}])], epoch(2026, 11, 10, 12, 0)
    )
    poll(None)
    first_poll = clock.now
    clock.advance(seconds=30)
    served[BUS_URL] = make_message(
        [trip([{"stop_id": "A", "seq": 1, "arr": (t + 40, 100)}])], epoch(2026, 11, 10, 12, 0, 30)
    )
    poll(None)

    (event,) = StopEvent.objects.all()
    assert event.first_seen == first_poll
    assert event.last_seen == clock.now
    assert event.arrival_delay == 100  # newest prediction wins
    assert event.arrival_time == datetime.fromtimestamp(t + 40, tz=UTC)
    assert event.feed_timestamp == datetime.fromtimestamp(epoch(2026, 11, 10, 12, 0, 30), tz=UTC)
    assert FeedFetch.objects.filter(status=FeedFetch.Status.OK).count() == 2


def test_dedup_without_stop_sequence_uses_nulls_not_distinct(served, clock):
    t = epoch(2026, 11, 10, 12, 5)
    for second in (0, 1, 2):  # minutes: each poll has a new header timestamp
        served[TRAM_URL] = make_message(
            [trip([{"stop_id": "A", "arr": (t, None)}])], epoch(2026, 11, 10, 12, second)
        )
        poll(None, feed_id=KRAKOW_TRAM_FEED)
        clock.advance(seconds=30)

    assert StopEvent.objects.count() == 1
    assert StopEvent.objects.get().stop_sequence is None


def test_different_sequence_service_date_trip_or_feed_are_separate_events(served, clock):
    t = epoch(2026, 11, 10, 12, 5)
    served[BUS_URL] = make_message(
        [
            trip(
                [
                    {"stop_id": "A", "seq": 1, "arr": (t, 0)},
                    {"stop_id": "A", "seq": 2, "arr": (t, 0)},
                ]
            ),
            trip([{"stop_id": "A", "seq": 1, "arr": (t, 0)}], trip_id="T2"),
            trip([{"stop_id": "A", "seq": 1, "arr": (t, 0)}], start_date="20261111"),
        ],
        epoch(2026, 11, 10, 12, 0),
    )
    served[TRAM_URL] = served[BUS_URL]
    poll(None)
    poll(None, feed_id=KRAKOW_TRAM_FEED)

    assert StopEvent.objects.filter(feed_id=KRAKOW_BUS_FEED).count() == 4
    assert StopEvent.objects.count() == 8


def test_partial_message_does_not_wipe_previous_arrival(served, clock):
    t = epoch(2026, 11, 10, 12, 5)
    served[BUS_URL] = make_message(
        [trip([{"stop_id": "A", "seq": 1, "arr": (t, 30), "dep": (t + 20, 50)}])],
        epoch(2026, 11, 10, 12, 0, 0),
    )
    poll(None)
    served[BUS_URL] = make_message(
        [trip([{"stop_id": "A", "seq": 1, "dep": (t + 90, 120)}])], epoch(2026, 11, 10, 12, 0, 30)
    )
    poll(None)

    (event,) = StopEvent.objects.all()
    # Arrival kept from the first message as a group (time, delay, scheduled).
    assert event.arrival_time == datetime.fromtimestamp(t, tz=UTC)
    assert event.arrival_delay == 30
    assert event.scheduled_arrival == datetime.fromtimestamp(t - 30, tz=UTC)
    # Departure replaced by the newer message.
    assert event.departure_time == datetime.fromtimestamp(t + 90, tz=UTC)
    assert event.departure_delay == 120
    assert event.scheduled_departure == datetime.fromtimestamp(t + 90 - 120, tz=UTC)


def test_time_zero_departure_does_not_wipe_previous_departure(served, clock):
    t = epoch(2026, 11, 10, 12, 5)
    served[BUS_URL] = make_message(
        [trip([{"stop_id": "A", "seq": 1, "arr": (t, 10), "dep": (t + 30, 10)}])],
        epoch(2026, 11, 10, 12, 0, 0),
    )
    poll(None)
    served[BUS_URL] = make_message(
        [trip([{"stop_id": "A", "seq": 1, "arr": (t + 5, 15), "dep": (0, 0)}])],
        epoch(2026, 11, 10, 12, 0, 30),
    )
    poll(None)

    (event,) = StopEvent.objects.all()
    assert event.arrival_delay == 15
    assert event.departure_time == datetime.fromtimestamp(t + 30, tz=UTC)
    assert event.departure_delay == 10


def test_route_direction_vehicle_are_coalesced(served, clock):
    t = epoch(2026, 11, 10, 12, 5)
    stops = [{"stop_id": "A", "seq": 1, "arr": (t, 0)}]
    served[BUS_URL] = make_message(
        [trip(stops, route_id="163", direction=1, vehicle="BU350")], epoch(2026, 11, 10, 12, 0, 0)
    )
    poll(None)
    served[BUS_URL] = make_message([trip(stops)], epoch(2026, 11, 10, 12, 0, 30))
    poll(None)

    (event,) = StopEvent.objects.all()
    assert (event.route_id, event.direction_id, event.vehicle_id) == ("163", 1, "BU350")

    served[BUS_URL] = make_message(
        [trip(stops, route_id="164", direction=0, vehicle="BU351")], epoch(2026, 11, 10, 12, 1, 0)
    )
    poll(None)
    event.refresh_from_db()
    assert (event.route_id, event.direction_id, event.vehicle_id) == ("164", 0, "BU351")


def test_direction_zero_is_stored_not_treated_as_missing(served, clock):
    t = epoch(2026, 11, 10, 12, 5)
    served[BUS_URL] = make_message(
        [trip([{"stop_id": "A", "seq": 1, "arr": (t, 0)}], direction=0)], epoch(2026, 11, 10, 12, 0)
    )
    poll(None)
    assert StopEvent.objects.get().direction_id == 0


def test_skipped_stop_is_stored_and_keeps_earlier_times(served, clock):
    t = epoch(2026, 11, 10, 12, 5)
    served[BUS_URL] = make_message(
        [trip([{"stop_id": "A", "seq": 1, "arr": (t, 0)}])], epoch(2026, 11, 10, 12, 0, 0)
    )
    poll(None)
    served[BUS_URL] = make_message(
        [trip([{"stop_id": "A", "seq": 1, "rel": ScheduleRelationship.SKIPPED}])],
        epoch(2026, 11, 10, 12, 0, 30),
    )
    poll(None)

    (event,) = StopEvent.objects.all()
    assert event.schedule_relationship == ScheduleRelationship.SKIPPED
    assert event.arrival_time == datetime.fromtimestamp(t, tz=UTC)


def test_inferred_service_date_across_midnight_is_stored(served, clock):
    # 23:50 and 00:20 local (CET) as two polls: before and after midnight.
    served[BUS_URL] = make_message(
        [
            {
                "trip_id": "N1",
                "stops": [
                    {"stop_id": "A", "seq": 1, "arr": (epoch(2026, 11, 10, 22, 50), None)},
                    {"stop_id": "B", "seq": 2, "arr": (epoch(2026, 11, 10, 23, 20), None)},
                ],
            }
        ],
        epoch(2026, 11, 10, 22, 45),
    )
    poll(None)
    served[BUS_URL] = make_message(
        [
            {
                "trip_id": "N1",
                "stops": [{"stop_id": "B", "seq": 2, "arr": (epoch(2026, 11, 10, 23, 25), None)}],
            }
        ],
        epoch(2026, 11, 10, 23, 15),
    )
    poll(None)

    assert StopEvent.objects.count() == 2  # B updated in place, not duplicated across days
    assert {e.service_date for e in StopEvent.objects.all()} == {date(2026, 11, 10)}
    assert all(e.service_date_inferred for e in StopEvent.objects.all())


# ------------------------------------------------------------------- statuses


def test_unchanged_header_timestamp_writes_nothing(served, clock):
    t = epoch(2026, 11, 10, 12, 5)
    body = make_message(
        [trip([{"stop_id": "A", "seq": 1, "arr": (t, 0)}])], epoch(2026, 11, 10, 12)
    )
    served[BUS_URL] = body
    first = poll(None)
    event_before = StopEvent.objects.values().get()
    clock.advance(seconds=30)

    second = poll(None)

    assert first.status == FeedFetch.Status.OK
    assert second.status == FeedFetch.Status.UNCHANGED
    assert second.stop_event_count is None
    assert second.feed_timestamp == first.feed_timestamp
    assert StopEvent.objects.values().get() == event_before  # last_seen not touched
    assert FeedFetch.objects.count() == 2


def test_new_header_timestamp_after_unchanged_is_processed(served, clock):
    t = epoch(2026, 11, 10, 12, 5)
    for second, expected in ((0, "ok"), (0, "unchanged"), (30, "ok")):
        served[BUS_URL] = make_message(
            [trip([{"stop_id": "A", "seq": 1, "arr": (t, 0)}])], epoch(2026, 11, 10, 12, 0, second)
        )
        assert poll(None).status == expected
        clock.advance(seconds=30)


def test_unchanged_is_tracked_per_feed(served, clock):
    t = epoch(2026, 11, 10, 12, 5)
    body = make_message([trip([{"stop_id": "A", "arr": (t, 0)}])], epoch(2026, 11, 10, 12))
    served[BUS_URL] = body
    served[TRAM_URL] = body
    assert poll(None).status == "ok"
    assert poll(None, feed_id=KRAKOW_TRAM_FEED).status == "ok"  # same timestamp, other feed


def test_stale_feed_is_logged_and_not_stored(served, clock, settings):
    settings.TRANSIT_REALTIME_STALE_AFTER = 300
    old = epoch(2026, 11, 10, 11, 0)  # an hour before ``clock.now``
    served[BUS_URL] = make_message([trip([{"stop_id": "A", "seq": 1, "arr": (old, 0)}])], old)

    log = poll(None)

    assert log.status == FeedFetch.Status.STALE
    assert log.entity_count == 1
    assert log.stop_event_count is None
    assert log.feed_timestamp == datetime.fromtimestamp(old, tz=UTC)
    assert StopEvent.objects.count() == 0


def test_feed_just_inside_stale_threshold_is_stored(served, clock, settings):
    settings.TRANSIT_REALTIME_STALE_AFTER = 300
    ts = epoch(2026, 11, 10, 11, 56)  # 4 minutes old
    served[BUS_URL] = make_message([trip([{"stop_id": "A", "arr": (ts, 0)}])], ts)
    assert poll(None).status == FeedFetch.Status.OK


def test_stale_feed_recovers_when_fresh_again(served, clock, settings):
    settings.TRANSIT_REALTIME_STALE_AFTER = 300
    stale = epoch(2026, 11, 10, 11, 0)
    served[BUS_URL] = make_message([trip([{"stop_id": "A", "arr": (stale, 0)}])], stale)
    assert poll(None).status == "stale"
    fresh = epoch(2026, 11, 10, 11, 59)
    served[BUS_URL] = make_message([trip([{"stop_id": "A", "arr": (fresh, 0)}])], fresh)
    assert poll(None).status == "ok"
    assert StopEvent.objects.count() == 1


def test_http_error_is_logged_without_raising(served, clock):
    served[BUS_URL] = FetchError(FeedFetch.Status.HTTP_ERROR, "HTTP 503", 503)
    log = poll(None)
    assert log.status == FeedFetch.Status.HTTP_ERROR
    assert log.http_status == 503
    assert "503" in log.error
    assert log.stop_event_count is None
    assert FeedFetch.objects.get().status == "http_error"


def test_network_error_is_logged_without_raising(monkeypatch, clock):
    def boom(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    log = poll(None)
    assert log.status == FeedFetch.Status.NETWORK_ERROR
    assert "connection refused" in log.error
    assert log.http_status is None


@pytest.mark.parametrize(
    "body",
    [b"", b"\xff\xfe not protobuf", b"<html>Bad gateway</html>"],
    ids=["empty", "bin", "html"],
)
def test_parse_error_is_logged_and_stores_nothing(served, clock, body):
    served[BUS_URL] = body
    log = poll(None)
    assert log.status == FeedFetch.Status.PARSE_ERROR
    assert log.size_bytes == len(body)
    assert log.error
    assert StopEvent.objects.count() == 0


def test_parse_error_does_not_break_unchanged_detection(served, clock):
    t = epoch(2026, 11, 10, 12, 5)
    good = make_message([trip([{"stop_id": "A", "arr": (t, 0)}])], epoch(2026, 11, 10, 12))
    served[BUS_URL] = good
    assert poll(None).status == "ok"
    served[BUS_URL] = b""
    assert poll(None).status == "parse_error"
    served[BUS_URL] = good
    assert poll(None).status == "unchanged"


def test_unexpected_exception_is_logged_as_error(served, clock, monkeypatch, caplog):
    served[BUS_URL] = make_message(
        [trip([{"stop_id": "A", "arr": (1, 0)}])], epoch(2026, 11, 10, 12)
    )

    def explode(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(realtime, "extract_stop_events", explode)

    log = poll(None)

    assert log.status == FeedFetch.Status.ERROR
    assert "kaboom" in log.error
    assert FeedFetch.objects.get().status == "error"


def test_database_failure_during_upsert_rolls_back_and_logs_error(served, clock, monkeypatch):
    t = epoch(2026, 11, 10, 12, 5)
    served[BUS_URL] = make_message(
        [trip([{"stop_id": "A", "seq": 1, "arr": (t, 0)}])], epoch(2026, 11, 10, 12)
    )

    def failing(rows, seen_at):
        raise RuntimeError("db down")

    monkeypatch.setattr(realtime, "upsert_stop_events", failing)
    assert poll(None).status == FeedFetch.Status.ERROR
    assert StopEvent.objects.count() == 0


def test_dump_dir_saves_raw_feed(served, clock, tmp_path):
    body = make_message([trip([{"stop_id": "A", "arr": (1, 0)}])], epoch(2026, 11, 10, 12))
    served[BUS_URL] = body
    city, feed = get_feed("krakow", KRAKOW_BUS_FEED)

    collect_feed(city, feed, dump_dir=tmp_path / "dumps")

    (dumped,) = list(Path(tmp_path / "dumps").glob("*.pb"))
    assert dumped.read_bytes() == body
    assert dumped.name.startswith("krakow_ztp_bus_trip_updates_")


def test_overlapping_poll_of_same_feed_is_skipped(served, clock, monkeypatch):
    served[BUS_URL] = make_message(
        [trip([{"stop_id": "A", "arr": (1, 0)}])], epoch(2026, 11, 10, 12)
    )
    monkeypatch.setattr(realtime, "_try_lock", lambda key: False)

    assert poll(None) is None
    assert served.requested == []
    assert FeedFetch.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_advisory_lock_held_by_another_session_skips_poll(served, clock):
    served[BUS_URL] = make_message(
        [trip([{"stop_id": "A", "arr": (1, 0)}])], epoch(2026, 11, 10, 12)
    )
    key = realtime._feed_lock_key("krakow", KRAKOW_BUS_FEED)
    settings_dict = connection.settings_dict
    other = psycopg.connect(
        dbname=settings_dict["NAME"],
        user=settings_dict["USER"],
        password=settings_dict["PASSWORD"],
        host=settings_dict["HOST"],
        port=settings_dict["PORT"],
        autocommit=True,
    )
    try:
        other.execute("SELECT pg_advisory_lock(hashtext(%s))", [key])
        assert poll(None) is None
        other.execute("SELECT pg_advisory_unlock(hashtext(%s))", [key])
        assert poll(None).status == FeedFetch.Status.OK  # lock was released, polling resumes
    finally:
        other.close()


def test_lock_is_released_after_every_poll(served, clock):
    served[BUS_URL] = b""
    assert poll(None).status == "parse_error"
    assert poll(None).status == "parse_error"  # would return None if the lock leaked


# ------------------------------------------------------------ all cities/feeds


def test_collects_every_city_with_trip_updates_feeds(served, clock, city_config):
    t = epoch(2026, 11, 10, 12, 5)
    body = make_message(
        [trip([{"stop_id": "A", "seq": 1, "arr": (t, 0)}])], epoch(2026, 11, 10, 12)
    )
    krakow = krakow_trip_update_urls()
    for url in krakow.values():
        served[url] = body
    served[TESTVILLE_URL] = body

    logs = collect_all_trip_updates()

    assert {KRAKOW_BUS_FEED, KRAKOW_TRAM_FEED} <= set(krakow)
    assert sorted(served.requested) == sorted([*krakow.values(), TESTVILLE_URL])
    assert {(log.city_id, log.feed_id) for log in logs} == {
        *(("krakow", feed_id) for feed_id in krakow),
        ("testville", "tv_trip_updates"),
    }
    assert all(log.status == "ok" for log in logs)
    # Same trip id in every feed/city: stored separately.
    assert StopEvent.objects.count() == len(krakow) + 1
    assert set(StopEvent.objects.values_list("city_id", flat=True)) == {"krakow", "testville"}


def test_city_without_trip_updates_feed_is_ignored(served, clock, city_config):
    for url in krakow_trip_update_urls().values():
        served[url] = b""
    served[TESTVILLE_URL] = b""
    collect_all_trip_updates()
    assert not [u for u in served.requested if "warszawa" in u or "um.warszawa" in u]
    assert not FeedFetch.objects.filter(city_id="warszawa").exists()


def test_vehicle_position_and_url_less_feeds_are_not_polled(served, clock, city_config):
    krakow = krakow_trip_update_urls()
    for url in krakow.values():
        served[url] = b""
    served[TESTVILLE_URL] = b""
    collect_all_trip_updates()
    assert "http://testville.invalid/Vehicles.pb" not in served.requested
    assert sorted(served.requested) == sorted([*krakow.values(), TESTVILLE_URL])


def test_filters_by_city_and_feed(served, clock, city_config):
    for url in krakow_trip_update_urls().values():
        served[url] = b""
    served[TESTVILLE_URL] = b""

    collect_all_trip_updates(city_id="testville")
    assert served.requested == [TESTVILLE_URL]

    served.requested.clear()
    collect_all_trip_updates(city_id="krakow", feed_id=KRAKOW_TRAM_FEED)
    assert served.requested == [TRAM_URL]

    served.requested.clear()
    assert collect_all_trip_updates(city_id="nowhere") == []
    assert collect_all_trip_updates(city_id="krakow", feed_id="tv_trip_updates") == []
    assert served.requested == []


def test_one_failing_feed_does_not_stop_the_others(served, clock, city_config):
    t = epoch(2026, 11, 10, 12, 5)
    krakow = krakow_trip_update_urls()
    for url in krakow.values():
        served[url] = b"garbage \xff"
    served[BUS_URL] = FetchError(FeedFetch.Status.HTTP_ERROR, "HTTP 500", 500)
    served[TESTVILLE_URL] = make_message(
        [trip([{"stop_id": "A", "arr": (t, 0)}])], epoch(2026, 11, 10, 12)
    )

    logs = collect_all_trip_updates()

    assert {log.feed_id: log.status for log in logs} == {
        **dict.fromkeys(krakow, "parse_error"),
        KRAKOW_BUS_FEED: "http_error",
        "tv_trip_updates": "ok",
    }
    assert StopEvent.objects.filter(city_id="testville").count() == 1


def test_city_timezone_drives_service_date_inference(served, clock, city_config, settings):
    # 22:30 UTC is 23:30 in Europe/Warsaw (CET): the inferred day is the 10th either way,
    # but 01:30 UTC (02:30 local) must still belong to the previous local day.
    served[TESTVILLE_URL] = make_message(
        [{"trip_id": "X", "stops": [{"stop_id": "A", "arr": (epoch(2026, 11, 11, 1, 30), None)}]}],
        epoch(2026, 11, 11, 1, 25),
    )
    collect_all_trip_updates(city_id="testville")
    assert StopEvent.objects.get().service_date == date(2026, 11, 10)


def test_real_http_error_from_urllib_is_logged_as_http_error(monkeypatch, clock):
    def forbidden(request, timeout=None):
        raise urllib.error.HTTPError(BUS_URL, 403, "forbidden", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    log = poll(None)
    assert log.status == FeedFetch.Status.HTTP_ERROR
    assert log.http_status == 403
