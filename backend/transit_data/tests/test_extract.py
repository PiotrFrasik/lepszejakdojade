"""Pure extraction of stop events from TripUpdates messages (no database)."""

from datetime import UTC, date, datetime

import pytest
from google.transit import gtfs_realtime_pb2 as pb

from transit_data.models import ScheduleRelationship
from transit_data.realtime import extract_stop_events, parse_feed

from .conftest import KRAKOW_BUS_FEED, KRAKOW_TRAM_FEED, epoch, get_feed, make_message

FETCHED_AT = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
HEADER_TS = epoch(2026, 11, 10, 12, 0)


def extract(body: bytes, city_id="krakow", feed_id=KRAKOW_BUS_FEED):
    city, feed = get_feed(city_id, feed_id)
    return extract_stop_events(parse_feed(body), city, feed, FETCHED_AT)


def one_trip(stops, **trip):
    return make_message([{"trip_id": "T1", "stops": stops, **trip}], HEADER_TS)


# ------------------------------------------------------------ recorded feeds


def test_tram_feed_without_stop_sequence_yields_all_updates(tram_pb):
    rows = extract(tram_pb, feed_id=KRAKOW_TRAM_FEED)

    assert len(rows) == 50
    assert {r.trip_id for r in rows} == {
        "block_88_trip_17_service_3",
        "block_88_trip_18_service_3",
        "block_88_trip_19_service_3",
        "block_66_trip_20_service_3",
        "block_67_trip_19_service_3",
    }
    assert all(r.stop_sequence is None for r in rows)
    assert all(r.city_id == "krakow" and r.feed_id == KRAKOW_TRAM_FEED for r in rows)
    assert all(r.service_date_inferred for r in rows)  # the feed has no start_date
    # No delay in the tram feed, so scheduled times cannot be derived.
    assert all(r.scheduled_arrival is None and r.scheduled_departure is None for r in rows)
    assert all(r.arrival_delay is None and r.departure_delay is None for r in rows)


def test_bus_feed_mixed_trips(bus_pb):
    rows = extract(bus_pb)

    assert len(rows) == 95
    first = next(r for r in rows if r.stop_id == "18471" and r.stop_sequence == 2)
    assert first.arrival_delay == 59
    assert (first.arrival_time - first.scheduled_arrival).total_seconds() == 59
    assert first.vehicle_id == "BU350"
    assert first.route_id == "163"
    assert first.direction_id is not None

    # Trips without delay/stop_sequence: scheduled is null, not guessed.
    plain = [r for r in rows if r.trip_id == "20261109_3_130096272_18"]
    assert len(plain) == 11
    assert all(r.stop_sequence is None and r.arrival_delay is None for r in plain)
    assert all(r.scheduled_arrival is None and r.scheduled_departure is None for r in plain)
    assert all(r.direction_id is None for r in plain)


def test_bus_feed_time_zero_is_treated_as_missing(bus_pb):
    rows = extract(bus_pb)

    # Last stop of the first trip: arrival is real, departure is "time: 0, delay: 0".
    last = next(r for r in rows if r.trip_id == "20261109_3_130097157_19" and r.stop_id == "8333")
    assert last.arrival_time is not None and last.arrival_delay == 59
    assert last.departure_time is None and last.departure_delay is None
    assert last.scheduled_departure is None
    # First stop of the second trip: arrival is "time: 0, delay: 0".
    first = next(r for r in rows if r.trip_id == "20261109_3_130097158_20" and r.stop_sequence == 1)
    assert first.arrival_time is None and first.arrival_delay is None
    assert first.departure_time is not None
    # No stored timestamp is the epoch.
    for r in rows:
        for value in (r.arrival_time, r.departure_time, r.scheduled_arrival):
            assert value is None or value.year > 2000


def test_recorded_feed_rows_carry_header_timestamp(bus_pb):
    rows = extract(bus_pb)
    assert all(r.feed_timestamp == datetime.fromtimestamp(1794433999, tz=UTC) for r in rows)


# ------------------------------------------------------------ scheduled/delay


def test_scheduled_is_time_minus_delay_only_when_both_present():
    t = epoch(2026, 11, 10, 12, 5)
    body = one_trip(
        [
            {"stop_id": "A", "seq": 1, "arr": (t, 120), "dep": (t + 30, 150)},
            {"stop_id": "B", "seq": 2, "arr": (t, None), "dep": (None, 60)},
        ],
        start_date="20261110",
    )

    a, b = extract(body)

    assert (a.scheduled_arrival, a.scheduled_departure) == (
        datetime.fromtimestamp(t - 120, tz=UTC),
        datetime.fromtimestamp(t + 30 - 150, tz=UTC),
    )
    assert b.arrival_time == datetime.fromtimestamp(t, tz=UTC)
    assert b.scheduled_arrival is None  # time without delay
    assert b.departure_time is None and b.departure_delay == 60
    assert b.scheduled_departure is None  # delay without time


def test_negative_delay_gives_later_scheduled_time():
    t = epoch(2026, 11, 10, 12, 0)
    (row,) = extract(one_trip([{"stop_id": "A", "seq": 1, "arr": (t, -45)}], start_date="20261110"))
    assert (row.scheduled_arrival - row.arrival_time).total_seconds() == 45


def test_time_zero_with_nonzero_delay_is_still_missing():
    t = epoch(2026, 11, 10, 12, 0)
    (row,) = extract(
        one_trip([{"stop_id": "A", "seq": 1, "arr": (0, 30), "dep": (t, 0)}], start_date="20261110")
    )
    assert row.arrival_time is None and row.arrival_delay is None
    assert row.departure_delay == 0  # a real zero delay is kept, not turned into null


# ----------------------------------------------------------------- service date


def test_start_date_is_used_when_present():
    t = epoch(2026, 11, 10, 12, 0)
    (row,) = extract(one_trip([{"stop_id": "A", "arr": (t, None)}], start_date="20261109"))
    assert row.service_date == date(2026, 11, 9)
    assert row.service_date_inferred is False


def test_start_date_wins_over_event_times_after_midnight():
    t = epoch(2026, 11, 10, 23, 30)  # 00:30 local on 11 Nov
    (row,) = extract(one_trip([{"stop_id": "A", "arr": (t, None)}], start_date="20261110"))
    assert row.service_date == date(2026, 11, 10)
    assert row.service_date_inferred is False


@pytest.mark.parametrize("bad", ["garbage", "2026111", "20261340", "2026-11-10"])
def test_invalid_start_date_falls_back_to_inference(bad):
    t = epoch(2026, 11, 10, 12, 0)
    (row,) = extract(one_trip([{"stop_id": "A", "arr": (t, None)}], start_date=bad))
    assert row.service_date == date(2026, 11, 10)
    assert row.service_date_inferred is True


@pytest.mark.parametrize(
    ("first_stop_utc", "second_stop_utc", "expected"),
    [
        # Winter (CET, UTC+1): 23:50 local on 10 Nov and 00:20 local on 11 Nov.
        ((2026, 11, 10, 22, 50), (2026, 11, 10, 23, 20), date(2026, 11, 10)),
        # Summer (CEST, UTC+2): 23:50 local on 10 Jul and 00:20 local on 11 Jul.
        ((2026, 7, 10, 21, 50), (2026, 7, 10, 22, 20), date(2026, 7, 10)),
    ],
)
def test_trip_crossing_midnight_keeps_its_starting_service_date(
    first_stop_utc, second_stop_utc, expected
):
    body = one_trip(
        [
            {"stop_id": "A", "arr": (epoch(*first_stop_utc), None)},
            {"stop_id": "B", "arr": (epoch(*second_stop_utc), None)},
        ]
    )
    rows = extract(body)
    assert {r.service_date for r in rows} == {expected}
    assert all(r.service_date_inferred for r in rows)


def test_remaining_stops_after_midnight_still_belong_to_previous_day():
    # Poll shortly after midnight: only the stop at 00:10 local (23:10 UTC) is left.
    (row,) = extract(one_trip([{"stop_id": "B", "arr": (epoch(2026, 11, 10, 23, 10), None)}]))
    assert row.service_date == date(2026, 11, 10)


@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        ((2026, 11, 11, 1, 50), date(2026, 11, 10)),  # 02:50 local: still the previous day
        ((2026, 11, 11, 2, 10), date(2026, 11, 11)),  # 03:10 local: new service day
    ],
)
def test_service_day_cutoff_is_three_hours_local(utc, expected):
    (row,) = extract(one_trip([{"stop_id": "A", "arr": (epoch(*utc), None)}]))
    assert row.service_date == expected


def test_trip_without_any_usable_time_uses_header_timestamp():
    (row,) = extract(one_trip([{"stop_id": "A", "rel": ScheduleRelationship.SKIPPED}]))
    assert row.service_date == date(2026, 11, 10)
    assert row.service_date_inferred is True


# ----------------------------------------------------------------- skipping


def test_cancelled_trips_are_skipped():
    t = epoch(2026, 11, 10, 12, 0)
    body = make_message(
        [
            {"trip_id": "gone", "canceled": True, "stops": [{"stop_id": "A", "arr": (t, 0)}]},
            {"trip_id": "kept", "stops": [{"stop_id": "A", "arr": (t, 0)}]},
        ],
        HEADER_TS,
    )
    assert [r.trip_id for r in extract(body)] == ["kept"]


def test_updates_without_stop_id_are_skipped():
    t = epoch(2026, 11, 10, 12, 0)
    rows = extract(
        one_trip(
            [
                {"stop_id": None, "seq": 1, "arr": (t, 0)},
                {"stop_id": "B", "seq": 2, "arr": (t, 0)},
            ]
        )
    )
    assert [r.stop_id for r in rows] == ["B"]


def test_skipped_stops_are_kept_without_times():
    rows = extract(one_trip([{"stop_id": "A", "seq": 1, "rel": ScheduleRelationship.SKIPPED}]))
    assert len(rows) == 1
    assert rows[0].schedule_relationship == ScheduleRelationship.SKIPPED
    assert rows[0].arrival_time is None and rows[0].departure_time is None


def test_updates_with_no_data_and_not_skipped_are_dropped():
    rows = extract(
        one_trip(
            [
                {"stop_id": "A", "seq": 1},
                {"stop_id": "B", "seq": 2, "arr": "empty", "dep": "empty"},
                {"stop_id": "C", "seq": 3, "arr": (0, 0), "dep": (0, 0)},
            ]
        )
    )
    assert rows == []


def test_trip_without_trip_id_deleted_and_non_trip_entities_are_skipped():
    t = epoch(2026, 11, 10, 12, 0)
    message = pb.FeedMessage()
    message.header.gtfs_realtime_version = "2.0"
    message.header.timestamp = HEADER_TS
    no_id = message.entity.add()
    no_id.id = "1"
    no_id.trip_update.trip.SetInParent()
    stu = no_id.trip_update.stop_time_update.add()
    stu.stop_id = "A"
    stu.arrival.time = t
    deleted = message.entity.add()
    deleted.id = "2"
    deleted.is_deleted = True
    deleted.trip_update.trip.trip_id = "deleted"
    deleted.trip_update.stop_time_update.add().stop_id = "A"
    vehicle_only = message.entity.add()
    vehicle_only.id = "3"
    vehicle_only.vehicle.trip.trip_id = "veh"

    assert extract(message.SerializeToString()) == []


def test_feed_with_no_entities_gives_no_rows():
    assert extract(make_message([], HEADER_TS)) == []


def test_duplicate_stop_in_one_message_collapses_to_last():
    t = epoch(2026, 11, 10, 12, 0)
    rows = extract(
        one_trip(
            [
                {"stop_id": "A", "seq": 1, "arr": (t, 10)},
                {"stop_id": "A", "seq": 1, "arr": (t + 60, 70)},
            ],
            start_date="20261110",
        )
    )
    assert len(rows) == 1
    assert rows[0].arrival_delay == 70


def test_same_stop_with_different_sequence_is_two_events():
    t = epoch(2026, 11, 10, 12, 0)
    rows = extract(
        one_trip(
            [
                {"stop_id": "A", "seq": 1, "arr": (t, 0)},
                {"stop_id": "A", "seq": 9, "arr": (t + 600, 0)},
            ],
            start_date="20261110",
        )
    )
    assert sorted(r.stop_sequence for r in rows) == [1, 9]
