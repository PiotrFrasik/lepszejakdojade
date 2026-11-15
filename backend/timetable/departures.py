"""Next departures at a stop group with live times (docs/api.md, "Departures (#73)").

Departures come from the static timetable of the active feed versions. Where the city has
realtime departures, each one is matched to a collected GTFS-Realtime stop event
(``transit_data.StopEvent``) by realtime->static feed pair (``static_feed`` of the city's
gtfs_rt feeds), trip, platform and service day.

Known limitations: frequency-based trips (``frequencies.txt``) are not expanded; trips
cancelled as a whole are not stored by the realtime collector, so only skipped stops
show as ``canceled``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db.models import Exists, OuterRef, Q

from cities.registry import City
from transit_data.models import FeedFetch, PickupDropOff, ScheduleRelationship, StopEvent, StopTime

from .calendar import ServiceCalendar, service_day_origin
from .lines import Feeds, lines_by_pk, make_id
from .stops import StopGroup

DEFAULT_LIMIT = 15
MAX_LIMIT = 30
# Departures whose effective time is at most this far ahead of now.
WINDOW_AHEAD = timedelta(hours=3)
# Departures whose effective time is at most this far behind now (a vehicle at the stop).
WINDOW_BEHIND = timedelta(minutes=1)
# Trips scheduled at most this long before now are considered, so late vehicles appear.
SCHEDULED_LOOKBACK = timedelta(minutes=60)
# Stop events and feed fetches older than this are not live.
REALTIME_FRESHNESS = timedelta(minutes=5)

LIVE = "live"
CANCELED = "canceled"
SCHEDULED = "scheduled"
STATUSES = (LIVE, CANCELED, SCHEDULED)

_TRIP_UPDATES = "trip_updates"
_SUCCESSFUL_FETCHES = (FeedFetch.Status.OK, FeedFetch.Status.UNCHANGED)

_STOP_TIME_FIELDS = (
    "feed_version_id",
    "trip_id",
    "stop_sequence",
    "departure_time",
    "stop_headsign",
    "trip__gtfs_id",
    "trip__headsign",
    "trip__route_id",
    "trip__service_id",
    "stop__gtfs_id",
    "stop__platform_code",
    "stop__code",
)
_EVENT_FIELDS = (
    "feed_id",
    "service_date",
    "trip_id",
    "stop_id",
    "stop_sequence",
    "schedule_relationship",
    "arrival_time",
    "arrival_delay",
    "departure_time",
    "departure_delay",
)


@dataclass
class _Departure:
    row: dict
    feed_id: str  # static feed
    service_date: date
    scheduled: datetime
    status: str = SCHEDULED
    expected: datetime | None = None
    delay_seconds: int | None = None

    @property
    def effective(self) -> datetime:
        return self.expected or self.scheduled


def _trip_update_feeds(city: City) -> list:
    return [f for f in city.feeds if f.kind == "gtfs_rt" and f.entity == _TRIP_UPDATES]


def realtime_available(city: City, now: datetime) -> bool:
    """True when the city declares realtime departures and at least one of its trip-update
    feeds was fetched successfully within REALTIME_FRESHNESS."""
    if not city.realtime.departures:
        return False
    feed_ids = [feed.id for feed in _trip_update_feeds(city)]
    if not feed_ids:
        return False
    return FeedFetch.objects.filter(
        city_id=city.id,
        feed_id__in=feed_ids,
        fetched_at__gte=now - REALTIME_FRESHNESS,
        status__in=_SUCCESSFUL_FETCHES,
    ).exists()


def _scheduled_candidates(
    city: City, feeds: Feeds, group: StopGroup, now: datetime
) -> list[_Departure]:
    """Static departures at the group's platforms on service days yesterday, today and
    tomorrow, scheduled between now - SCHEDULED_LOOKBACK and now + WINDOW_AHEAD."""
    zone = city.zoneinfo
    stop_pks_by_version: dict[int, list[int]] = {}
    for platform in group.platforms:
        resolved = feeds.resolve(platform.stop_id)
        if resolved is not None:
            stop_pks_by_version.setdefault(resolved[0], []).append(platform.pk)

    today = now.astimezone(zone).date()
    earliest, latest = now - SCHEDULED_LOOKBACK, now + WINDOW_AHEAD
    # (version, day) -> (services, origin, min seconds, max seconds)
    windows: dict[tuple[int, date], tuple[frozenset[str], datetime, int, int]] = {}
    condition = Q()
    for version_id, stop_pks in stop_pks_by_version.items():
        calendar = ServiceCalendar(version_id)
        for offset in (-1, 0, 1):
            day = today + timedelta(days=offset)
            services = calendar.services_on(day)
            if not services:
                continue
            origin = service_day_origin(day, zone)
            low = max(0, math.ceil((earliest - origin).total_seconds()))
            high = math.floor((latest - origin).total_seconds())
            if high < low:
                continue
            windows[(version_id, day)] = (services, origin, low, high)
            condition |= Q(
                stop_id__in=stop_pks,
                trip__service_id__in=services,
                departure_time__range=(low, high),
            )
    if not windows:
        return []

    has_later_stop = StopTime.objects.filter(
        trip_id=OuterRef("trip_id"), stop_sequence__gt=OuterRef("stop_sequence")
    )
    rows = (
        StopTime.objects.filter(condition)
        .exclude(pickup_type=PickupDropOff.NONE)
        .filter(Exists(has_later_stop))
        .values(*_STOP_TIME_FIELDS)
    )
    candidates = []
    for row in rows:
        version_id = row["feed_version_id"]
        for (window_version, day), (services, origin, low, high) in windows.items():
            if (
                window_version == version_id
                and row["trip__service_id"] in services
                and low <= row["departure_time"] <= high
            ):
                candidates.append(
                    _Departure(
                        row=row,
                        feed_id=feeds.feed_by_version[version_id],
                        service_date=day,
                        scheduled=origin + timedelta(seconds=row["departure_time"]),
                    )
                )
    return candidates


def _fresh_events(
    city: City, candidates: list[_Departure], now: datetime
) -> dict[tuple[str, date, str, str], list[dict]]:
    """Fresh stop events of the candidates' trips at their platforms, keyed by
    ``(static feed id, service date, trip gtfs id, stop gtfs id)``. One query."""
    static_by_realtime = {
        feed.id: feed.static_feed for feed in _trip_update_feeds(city) if feed.static_feed
    }
    trips_by_feed: dict[str, set[str]] = {}
    stops_by_feed: dict[str, set[str]] = {}
    for candidate in candidates:
        trips_by_feed.setdefault(candidate.feed_id, set()).add(candidate.row["trip__gtfs_id"])
        stops_by_feed.setdefault(candidate.feed_id, set()).add(candidate.row["stop__gtfs_id"])

    condition = Q()
    for realtime_id, static_id in static_by_realtime.items():
        if static_id in trips_by_feed:
            condition |= Q(
                feed_id=realtime_id,
                trip_id__in=trips_by_feed[static_id],
                stop_id__in=stops_by_feed[static_id],
            )
    if not condition:
        return {}

    rows = StopEvent.objects.filter(
        condition,
        city_id=city.id,
        service_date__in={candidate.service_date for candidate in candidates},
        last_seen__gte=now - REALTIME_FRESHNESS,
    ).values(*_EVENT_FIELDS)
    events: dict[tuple[str, date, str, str], list[dict]] = {}
    for row in rows:
        static_id = static_by_realtime[row["feed_id"]]
        key = (static_id, row["service_date"], row["trip_id"], row["stop_id"])
        events.setdefault(key, []).append(row)
    return events


def _match(events: list[dict], stop_sequence: int) -> dict | None:
    """The event of one trip call: same stop_sequence, else one without stop_sequence
    (feeds that do not send it). An event with a different stop_sequence belongs to another
    call of the same trip at this platform (loop trips) and is never used."""
    for event in events:
        if event["stop_sequence"] == stop_sequence:
            return event
    for event in events:
        if event["stop_sequence"] is None:
            return event
    return None


def _apply_event(departure: _Departure, event: dict) -> None:
    if event["schedule_relationship"] == ScheduleRelationship.SKIPPED:
        departure.status = CANCELED
        return
    if event["schedule_relationship"] == ScheduleRelationship.NO_DATA:
        return
    for time_field, delay_field in (
        ("departure_time", "departure_delay"),
        ("arrival_time", "arrival_delay"),
    ):
        expected, delay = event[time_field], event[delay_field]
        if expected is None and delay is None:
            continue
        if expected is None:
            expected = departure.scheduled + timedelta(seconds=delay)
        if delay is None:
            delay = round((expected - departure.scheduled).total_seconds())
        departure.status = LIVE
        departure.expected = expected
        departure.delay_seconds = delay
        return


def _last_stop_names(trip_pks: set[int]) -> dict[int, str]:
    """Name of the last stop of each trip, one query."""
    rows = (
        StopTime.objects.filter(trip_id__in=trip_pks)
        .order_by("trip_id", "-stop_sequence")
        .distinct("trip_id")
        .values_list("trip_id", "stop__name")
    )
    return {trip_pk: name or "" for trip_pk, name in rows}


def _timestamp(moment: datetime, city: City) -> str:
    return moment.astimezone(city.zoneinfo).replace(microsecond=0).isoformat()


def build_departures(
    city: City, feeds: Feeds, group: StopGroup, requested_stop_id: str, now: datetime, limit: int
) -> dict:
    """Response of GET /cities/{city}/stops/{stop_id}/departures/ for one stop group."""
    live = realtime_available(city, now)
    candidates = _scheduled_candidates(city, feeds, group, now)
    lines = lines_by_pk(city, feeds, {c.row["trip__route_id"] for c in candidates})
    candidates = [c for c in candidates if c.row["trip__route_id"] in lines]

    if live and candidates:
        events = _fresh_events(city, candidates, now)
        for candidate in candidates:
            key = (
                candidate.feed_id,
                candidate.service_date,
                candidate.row["trip__gtfs_id"],
                candidate.row["stop__gtfs_id"],
            )
            if key in events and (event := _match(events[key], candidate.row["stop_sequence"])):
                _apply_event(candidate, event)

    earliest, latest = now - WINDOW_BEHIND, now + WINDOW_AHEAD
    selected = sorted(
        (c for c in candidates if earliest <= c.effective <= latest),
        key=lambda c: (
            c.effective,
            c.scheduled,
            c.row["trip__gtfs_id"],
            c.row["stop__gtfs_id"],
        ),
    )[:limit]

    blank = {
        c.row["trip_id"]
        for c in selected
        if not (c.row["stop_headsign"] or c.row["trip__headsign"])
    }
    last_names = _last_stop_names(blank) if blank else {}

    departures = []
    for c in selected:
        row = c.row
        departures.append(
            {
                "line": lines[row["trip__route_id"]].summary(),
                "trip_id": make_id(c.feed_id, row["trip__gtfs_id"]),
                "headsign": row["stop_headsign"]
                or row["trip__headsign"]
                or last_names.get(row["trip_id"], ""),
                "platform_id": make_id(c.feed_id, row["stop__gtfs_id"]),
                "platform_code": row["stop__platform_code"] or row["stop__code"] or None,
                "scheduled": _timestamp(c.scheduled, city),
                "expected": _timestamp(c.expected, city) if c.expected else None,
                "delay_seconds": c.delay_seconds,
                "status": c.status,
            }
        )
    return {
        "stop": {
            "id": requested_stop_id,
            "name": group.name,
            "stop_ids": [platform.stop_id for platform in group.platforms],
        },
        "generated_at": _timestamp(now, city),
        "realtime_available": live,
        "departures": departures,
    }
