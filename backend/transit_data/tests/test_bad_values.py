"""Values that cannot be stored are skipped and counted; the rest of the poll is kept."""

from collections import Counter
from datetime import UTC, date, datetime

import pytest

from transit_data import realtime
from transit_data.models import FeedFetch, StopEvent
from transit_data.realtime import collect_feed, extract_stop_events, parse_feed

from .conftest import KRAKOW_BUS_FEED, epoch, get_feed, make_message

BUS_URL = "https://gtfs.ztp.krakow.pl/TripUpdates_A.pb"
FETCHED_AT = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
HEADER = epoch(2026, 11, 10, 12, 0)
T = epoch(2026, 11, 10, 12, 5)


def max_length(field):
    return StopEvent._meta.get_field(field).max_length


def good_trip(trip_id="GOOD"):
    return {
        "trip_id": trip_id,
        "start_date": "20261110",
        "stops": [{"stop_id": "A", "seq": 1, "arr": (T, 0)}],
    }


def trip_with(**changes):
    spec = good_trip("BAD")
    spec.update(changes)
    return spec


def extract(trips):
    city, feed = get_feed("krakow", KRAKOW_BUS_FEED)
    skipped = Counter()
    message = parse_feed(make_message(trips, HEADER))
    rows = extract_stop_events(message, city, feed, FETCHED_AT, skipped=skipped)
    return rows, skipped


# ------------------------------------------------------------ extraction


@pytest.mark.parametrize(
    "bad",
    [
        {"trip_id": "x" * (max_length("trip_id") + 1)},
        {"route_id": "r" * (max_length("route_id") + 1)},
        {"vehicle": "v" * (max_length("vehicle_id") + 1)},
        {"trip_id": "bad\x00id"},
        {"route_id": "r\x00"},
        {"vehicle": "\x00"},
        {"direction": 32768},
        {"direction": 2**32 - 1},
    ],
    ids=[
        "long-trip-id",
        "long-route-id",
        "long-vehicle-id",
        "nul-trip-id",
        "nul-route-id",
        "nul-vehicle-id",
        "direction-32768",
        "direction-uint32-max",
    ],
)
def test_bad_entity_value_skips_whole_entity_only(bad):
    rows, skipped = extract([trip_with(**bad), good_trip()])

    assert [r.trip_id for r in rows] == ["GOOD"]
    assert sum(skipped.values()) == 1
    assert next(iter(skipped)).startswith("entity:")


def test_values_at_the_limit_are_accepted():
    rows, skipped = extract(
        [
            trip_with(
                trip_id="x" * max_length("trip_id"),
                route_id="r" * max_length("route_id"),
                vehicle="v" * max_length("vehicle_id"),
                direction=32767,
            )
        ]
    )
    assert len(rows) == 1
    assert not skipped
    assert rows[0].direction_id == 32767


@pytest.mark.parametrize(
    "stop",
    [
        {"stop_id": "s" * (max_length("stop_id") + 1), "seq": 2, "arr": (T, 0)},
        {"stop_id": "n\x00ul", "seq": 2, "arr": (T, 0)},
        {"stop_id": "B", "seq": 2**31, "arr": (T, 0)},
        {"stop_id": "B", "seq": 2**32 - 1, "arr": (T, 0)},
        {"stop_id": "B", "seq": 2, "arr": (epoch(2101, 1, 1, 0, 0), 0)},
        {"stop_id": "B", "seq": 2, "dep": (epoch(1999, 12, 31, 0, 0), 0)},
        {"stop_id": "B", "seq": 2, "arr": (2**62, None)},
        {"stop_id": "B", "seq": 2, "arr": (T, 2**31 - 1)},  # scheduled about 68 years earlier
        {
            "stop_id": "B",
            "seq": 2,
            "arr": (epoch(2099, 12, 31, 23, 0), -86400),
        },  # scheduled in 2100
    ],
    ids=[
        "long-stop-id",
        "nul-stop-id",
        "seq-2^31",
        "seq-2^32-1",
        "year-2101",
        "year-1999",
        "overflow",
        "scheduled-too-early",
        "scheduled-too-late",
    ],
)
def test_bad_stop_update_is_skipped_but_other_stops_and_trip_survive(stop):
    spec = good_trip()
    spec["stops"].append(stop)
    spec["stops"].append({"stop_id": "C", "seq": 3, "arr": (T, 0)})

    rows, skipped = extract([spec])

    assert sorted(r.stop_id for r in rows) == ["A", "C"]
    assert sum(skipped.values()) == 1
    assert next(iter(skipped)).startswith("stop update:")


def test_stop_sequence_at_limit_is_accepted():
    spec = good_trip()
    spec["stops"][0]["seq"] = 2**31 - 1
    rows, skipped = extract([spec])
    assert rows[0].stop_sequence == 2**31 - 1
    assert not skipped


def test_skipped_counts_are_grouped_by_reason():
    long_stop = "s" * (max_length("stop_id") + 1)
    spec = good_trip()
    spec["stops"] += [{"stop_id": long_stop, "seq": 10 + i, "arr": (T, 0)} for i in range(3)]
    rows, skipped = extract([spec, trip_with(direction=40000)])

    assert len(rows) == 1
    assert sum(skipped.values()) == 4
    assert len(skipped) == 2


def test_clean_feed_has_nothing_skipped(bus_pb):
    city, feed = get_feed("krakow", KRAKOW_BUS_FEED)
    skipped = Counter()
    rows = extract_stop_events(parse_feed(bus_pb), city, feed, FETCHED_AT, skipped=skipped)
    assert len(rows) == 95
    assert not skipped


def test_extract_works_without_skipped_counter():
    city, feed = get_feed("krakow", KRAKOW_BUS_FEED)
    message = parse_feed(make_message([trip_with(direction=40000), good_trip()], HEADER))
    assert len(extract_stop_events(message, city, feed, FETCHED_AT)) == 1


def test_known_service_dates_are_used_for_trips_without_start_date():
    city, feed = get_feed("krakow", KRAKOW_BUS_FEED)
    # 02:10 UTC = 03:10 local, inferred day 11 Nov; remembered 10 Nov is the day before.
    body = make_message(
        [{"trip_id": "N", "stops": [{"stop_id": "A", "arr": (epoch(2026, 11, 11, 2, 10), None)}]}],
        HEADER,
    )
    (row,) = extract_stop_events(
        parse_feed(body), city, feed, FETCHED_AT, known_service_dates={"N": date(2026, 11, 10)}
    )
    assert row.service_date == date(2026, 11, 10)
    assert row.service_date_inferred


# ------------------------------------------------------------ poll level


@pytest.mark.django_db
def test_poll_with_bad_values_is_ok_and_reports_skips(served, caplog):
    long_stop = "s" * (max_length("stop_id") + 1)
    spec = good_trip()
    spec["stops"] += [{"stop_id": long_stop, "seq": 2, "arr": (T, 0)}]
    served[BUS_URL] = make_message(
        [spec, trip_with(trip_id="x" * (max_length("trip_id") + 1)), good_trip("GOOD2")], HEADER
    )
    city, feed = get_feed("krakow", KRAKOW_BUS_FEED)

    with caplog.at_level("WARNING", logger=realtime.logger.name):
        log = collect_feed(city, feed)

    assert log.status == FeedFetch.Status.OK
    assert log.stop_event_count == 2
    assert log.skipped_count == 2  # one oversized stop id, one oversized trip id
    assert log.error.startswith("skipped: ")
    assert "stop update" in log.error
    assert "entity" in log.error
    assert sorted(StopEvent.objects.values_list("trip_id", flat=True)) == ["GOOD", "GOOD2"]
    warnings = [r for r in caplog.records if "skipped" in r.getMessage()]
    assert len(warnings) == 1
    stored = FeedFetch.objects.get()
    assert stored.skipped_count == 2
    assert stored.error == log.error


@pytest.mark.django_db
def test_clean_poll_has_zero_skipped_and_no_error(served):
    served[BUS_URL] = make_message([good_trip()], HEADER)
    city, feed = get_feed("krakow", KRAKOW_BUS_FEED)

    log = collect_feed(city, feed)

    assert log.status == FeedFetch.Status.OK
    assert log.skipped_count == 0
    assert log.error == ""


@pytest.mark.django_db
def test_error_summary_fits_the_column_when_many_distinct_reasons(served):
    trips = [good_trip()]
    trips += [trip_with(trip_id=f"t{i}", direction=40000 + i) for i in range(60)]
    trips += [trip_with(trip_id=f"u{i}", route_id="r" * 100) for i in range(5)]
    served[BUS_URL] = make_message(trips, HEADER)
    city, feed = get_feed("krakow", KRAKOW_BUS_FEED)

    log = collect_feed(city, feed)

    assert log.status == FeedFetch.Status.OK
    assert log.skipped_count == 65
    assert len(log.error) <= 500
    assert log.error.startswith("skipped: ")
