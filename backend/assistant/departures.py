"""Next scheduled departures at a group of platforms, derived from the static timetable
(active GTFS feed versions only, no live data).

Looks at the service days yesterday (trips running past midnight), today and tomorrow in
the city time zone, so a late-evening question still gets departures after midnight.
Known limitation: frequency-based trips (``frequencies.txt``, e.g. Warsaw metro) are not
expanded here; only their template run is seen.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime, timedelta

from django.db.models import Exists, OuterRef

from cities.registry import City
from timetable.calendar import ServiceCalendar, clock_time, service_day_origin
from timetable.lines import Feeds, lines_by_pk, make_id
from transit_data.models import PickupDropOff, Stop, StopTime

MAX_DEPARTURES = 10

_FIELDS = (
    "trip_id",
    "departure_time",
    "stop_headsign",
    "trip__gtfs_id",
    "trip__headsign",
    "trip__route_id",
    "trip__direction_id",
)


def _last_stop_names(trip_pks: Iterable[int]) -> dict[int, str]:
    names: dict[int, str] = {}
    for trip_pk in set(trip_pks):
        name = (
            StopTime.objects.filter(trip_id=trip_pk)
            .order_by("-stop_sequence")
            .values_list("stop__name", flat=True)
            .first()
        )
        names[trip_pk] = name or ""
    return names


def upcoming_departures(
    city: City,
    feeds: Feeds,
    stop_pks: Iterable[int],
    now: datetime,
    limit: int = MAX_DEPARTURES,
    route_pks: set[int] | None = None,
) -> list[dict]:
    """Up to ``limit`` departures at the given stops (Stop pks) from ``now`` on, ascending.

    Items: ``line`` (summary), ``direction``, ``headsign``, ``time``, ``next_day``,
    ``date`` (service date), ``trip_id``, ``stop_id`` (platform).
    """
    zone = city.zoneinfo
    now = now.astimezone(zone)
    stops_by_version: dict[int, list[int]] = {}
    for pk, version_id in Stop.objects.filter(
        pk__in=list(stop_pks), feed_version_id__in=feeds.version_ids
    ).values_list("id", "feed_version_id"):
        stops_by_version.setdefault(version_id, []).append(pk)

    has_later_stop = StopTime.objects.filter(
        trip_id=OuterRef("trip_id"), stop_sequence__gt=OuterRef("stop_sequence")
    )
    today = now.date()
    # (instant, service date, row, feed version id)
    candidates: list[tuple[datetime, str, dict, int]] = []
    for version_id, pks in stops_by_version.items():
        calendar = ServiceCalendar(version_id)
        for offset in (-1, 0, 1):
            day = today + timedelta(days=offset)
            services = calendar.services_on(day)
            if not services:
                continue
            origin = service_day_origin(day, zone)
            min_seconds = max(0, math.ceil((now - origin).total_seconds()))
            rows = (
                StopTime.objects.filter(
                    stop_id__in=pks,
                    trip__service_id__in=services,
                    departure_time__isnull=False,
                    departure_time__gte=min_seconds,
                )
                .exclude(pickup_type=PickupDropOff.NONE)
                .filter(Exists(has_later_stop))
            )
            if route_pks is not None:
                rows = rows.filter(trip__route_id__in=route_pks)
            for row in rows.values(*_FIELDS, "stop__gtfs_id").order_by(
                "departure_time", "trip__gtfs_id"
            )[:limit]:
                instant = origin + timedelta(seconds=row["departure_time"])
                candidates.append((instant, day.isoformat(), row, version_id))

    candidates.sort(key=lambda item: (item[0], item[2]["trip__gtfs_id"]))
    lines = lines_by_pk(city, feeds, {row["trip__route_id"] for _, _, row, _ in candidates})
    candidates = [item for item in candidates if item[2]["trip__route_id"] in lines][:limit]
    blank = [
        row["trip_id"]
        for _, _, row, _ in candidates
        if not (row["stop_headsign"] or row["trip__headsign"])
    ]
    last_names = _last_stop_names(blank) if blank else {}

    departures = []
    for _instant, service_date, row, version_id in candidates:
        line = lines[row["trip__route_id"]]
        time_text, next_day = clock_time(row["departure_time"])
        feed_id = feeds.feed_by_version[version_id]
        departures.append(
            {
                "line": line.summary(),
                "direction": row["trip__direction_id"] or 0,
                "headsign": row["stop_headsign"]
                or row["trip__headsign"]
                or last_names.get(row["trip_id"], ""),
                "time": time_text,
                "next_day": next_day,
                "date": service_date,
                "trip_id": make_id(feed_id, row["trip__gtfs_id"]),
                "stop_id": make_id(feed_id, row["stop__gtfs_id"]),
            }
        )
    return departures
