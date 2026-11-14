"""Service date of trips without start_date stays stable across polls."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from transit_data import realtime
from transit_data.models import FeedFetch, StopEvent
from transit_data.realtime import (
    TRIP_DATE_MEMORY,
    _resolve_service_date,
    collect_feed,
    recent_service_dates,
)

from .conftest import KRAKOW_BUS_FEED, epoch, get_feed, make_message

pytestmark = pytest.mark.django_db

BUS_URL = "https://gtfs.ztp.krakow.pl/TripUpdates_A.pb"
WARSAW = ZoneInfo("Europe/Warsaw")
NOW = datetime(2026, 11, 11, 3, 0, tzinfo=UTC)


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = NOW

    clock = Clock()
    monkeypatch.setattr(realtime.timezone, "now", lambda: clock.now)
    return clock


def make_event(trip_id, service_date, *, inferred=True, last_seen=NOW, city="krakow", feed=None):
    return StopEvent.objects.create(
        city_id=city,
        feed_id=feed or KRAKOW_BUS_FEED,
        service_date=service_date,
        service_date_inferred=inferred,
        trip_id=trip_id,
        stop_id="S",
        first_seen=last_seen,
        last_seen=last_seen,
    )


def poll():
    city, feed = get_feed("krakow", KRAKOW_BUS_FEED)
    return collect_feed(city, feed)


# ------------------------------------------------------------ recent_service_dates


def test_recent_service_dates_returns_inferred_trips_seen_recently():
    make_event("fresh", date(2026, 11, 10), last_seen=NOW - timedelta(hours=1))
    make_event("old", date(2026, 11, 10), last_seen=NOW - TRIP_DATE_MEMORY - timedelta(minutes=1))

    result = recent_service_dates("krakow", KRAKOW_BUS_FEED, NOW)

    assert result == {"fresh": date(2026, 11, 10)}


def test_recent_service_dates_ignores_explicit_dates_other_cities_and_feeds():
    make_event("explicit", date(2026, 11, 10), inferred=False)
    make_event("other_city", date(2026, 11, 10), city="warszawa")
    make_event("other_feed", date(2026, 11, 10), feed="ztp_tram_trip_updates")

    assert recent_service_dates("krakow", KRAKOW_BUS_FEED, NOW) == {}


def test_recent_service_dates_earlier_date_wins_when_trip_has_two():
    make_event("T", date(2026, 11, 11))
    StopEvent.objects.filter(trip_id="T").update(stop_id="X")
    make_event("T", date(2026, 11, 10))

    assert recent_service_dates("krakow", KRAKOW_BUS_FEED, NOW) == {"T": date(2026, 11, 10)}


def test_recent_service_dates_empty_database():
    assert recent_service_dates("krakow", KRAKOW_BUS_FEED, NOW) == {}


# ------------------------------------------------------------ _resolve_service_date

# 01:50 UTC on 11 Nov = 02:50 local (CET): inferred day is 10 Nov.
EARLY = datetime(2026, 11, 11, 1, 50, tzinfo=UTC)
# 02:10 UTC on 11 Nov = 03:10 local: inferred day is 11 Nov.
LATE = datetime(2026, 11, 11, 2, 10, tzinfo=UTC)


@pytest.mark.parametrize(
    ("known", "first_event", "expected"),
    [
        (None, LATE, date(2026, 11, 11)),  # nothing remembered: infer
        (date(2026, 11, 10), LATE, date(2026, 11, 10)),  # day before inferred: reuse
        (date(2026, 11, 11), LATE, date(2026, 11, 11)),  # equal to inferred: reuse
        (date(2026, 11, 9), LATE, date(2026, 11, 11)),  # two days before: older run, infer
        (date(2026, 11, 12), LATE, date(2026, 11, 11)),  # in the future: infer
        (date(2026, 11, 9), EARLY, date(2026, 11, 9)),  # day before inferred: reuse
        (date(2026, 11, 8), EARLY, date(2026, 11, 10)),
        (date(2026, 11, 10), EARLY, date(2026, 11, 10)),
    ],
)
def test_resolve_service_date(known, first_event, expected):
    assert _resolve_service_date(known, first_event, NOW, WARSAW) == expected


def test_resolve_service_date_falls_back_when_no_event_time():
    fallback = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    assert _resolve_service_date(None, None, fallback, WARSAW) == date(2026, 11, 11)


# ------------------------------------------------------------ end to end


def serve(served, stops_utc, header):
    served[BUS_URL] = make_message(
        [
            {
                "trip_id": "NIGHT",
                "stops": [
                    {"stop_id": f"S{i}", "seq": i, "arr": (epoch(*t), None)} for i, t in stops_utc
                ],
            }
        ],
        epoch(*header),
    )


def test_trip_crossing_service_cutoff_keeps_one_date_across_polls(served, clock):
    # CET: 02:50, 03:10, 03:20 local = 01:50, 02:10, 02:20 UTC on 11 Nov.
    s1, s2, s3 = (2026, 11, 11, 1, 50), (2026, 11, 11, 2, 10), (2026, 11, 11, 2, 20)
    serve(served, [(1, s1), (2, s2)], (2026, 11, 11, 1, 45))
    clock.now = datetime(2026, 11, 11, 1, 46, tzinfo=UTC)
    assert poll().status == FeedFetch.Status.OK

    # Stop 1 has dropped out of the feed; the first remaining event is now 03:10 local.
    serve(served, [(2, s2), (3, s3)], (2026, 11, 11, 2, 11))
    clock.now = datetime(2026, 11, 11, 2, 12, tzinfo=UTC)
    assert poll().status == FeedFetch.Status.OK

    events = StopEvent.objects.order_by("stop_sequence")
    assert [e.stop_sequence for e in events] == [1, 2, 3]  # stop 2 not duplicated
    assert {e.service_date for e in events} == {date(2026, 11, 10)}
    assert all(e.service_date_inferred for e in events)


def test_same_trip_id_on_next_day_outside_memory_window_gets_new_date(served, clock):
    serve(served, [(1, (2026, 11, 10, 8, 0))], (2026, 11, 10, 7, 55))
    clock.now = datetime(2026, 11, 10, 7, 56, tzinfo=UTC)
    poll()

    # Same daily-repeated trip_id the next morning: yesterday's rows are far past 4 hours.
    serve(served, [(1, (2026, 11, 11, 8, 0))], (2026, 11, 11, 7, 55))
    clock.now = datetime(2026, 11, 11, 7, 56, tzinfo=UTC)
    poll()

    dates = sorted(StopEvent.objects.values_list("service_date", flat=True))
    assert dates == [date(2026, 11, 10), date(2026, 11, 11)]


def test_stored_date_two_days_old_is_not_reused_even_inside_window(served, clock):
    make_event("NIGHT", date(2026, 11, 8), last_seen=datetime(2026, 11, 11, 7, 0, tzinfo=UTC))
    serve(served, [(1, (2026, 11, 11, 8, 0))], (2026, 11, 11, 7, 55))
    clock.now = datetime(2026, 11, 11, 7, 56, tzinfo=UTC)
    poll()

    assert StopEvent.objects.get(stop_sequence=1).service_date == date(2026, 11, 11)
