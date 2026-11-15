"""Builds the timetable API responses from the static GTFS tables (active versions only).

Response shapes are documented in docs/api.md, section "Timetable (#10)".
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from django.core.cache import cache
from django.db import connection
from django.db.models import Count, Exists, Min, OuterRef, Q

from cities.registry import City
from transit_data.models import (
    Accessibility,
    Frequency,
    PickupDropOff,
    Shape,
    Stop,
    StopTime,
    Trip,
)

from .calendar import DAY_TYPES, ServiceCalendar, clock_time, gtfs_timestamp
from .lines import Feeds, Line, lines_by_pk, make_id
from .variants import MAIN, SHORT_TURN, Variant, build_variants, extend_variants, merge_stops
from .variants import trip_patterns as load_trip_patterns

# Route diagram: how far ahead to look for a day with service when `date` has none.
SERVICE_LOOKAHEAD_DAYS = 60
# Stop timetable: each column shows the first date >= `date` of its day type within this
# many days after `date`.
COLUMN_LOOKAHEAD_DAYS = 14
# Transfers: stops with the same name within this distance count as the same place.
TRANSFER_RADIUS_M = 300
# Bounding box margin (degrees) used to reach the spatial index before the exact
# distance check. One degree of longitude shrinks with latitude, so the margin covers
# TRANSFER_RADIUS_M up to _TRANSFER_MAX_LATITUDE (Kraków and Warsaw are at 50-52.5°N).
_TRANSFER_MAX_LATITUDE = 60
_METRES_PER_DEGREE = 111_320
_TRANSFER_BBOX_DEGREES = TRANSFER_RADIUS_M / (
    _METRES_PER_DEGREE * math.cos(math.radians(_TRANSFER_MAX_LATITUDE))
)
# Lines stopping at a stop never change for a given stop row (feed versions are immutable).
_STOP_ROUTES_CACHE_SECONDS = 24 * 3600


class DirectionNotFound(Exception):
    """The line has no trips in the requested direction."""


def _direction_q(direction: int, prefix: str = "") -> Q:
    """Trips of a direction; trips without direction_id count as direction 0."""
    field = f"{prefix}direction_id"
    q = Q(**{field: direction})
    if direction == 0:
        q |= Q(**{f"{field}__isnull": True})
    return q


def _wheelchair(value: int) -> bool | None:
    if value == Accessibility.YES:
        return True
    if value == Accessibility.NO:
        return False
    return None


def line_directions(line: Line) -> list[dict]:
    """Existing directions of a line with their most common headsign."""
    rows = (
        Trip.objects.filter(route_id=line.pk)
        .values("direction_id", "headsign")
        .annotate(trips=Count("id"))
    )
    counts: dict[int, Counter] = defaultdict(Counter)
    for row in rows:
        counts[row["direction_id"] or 0][row["headsign"]] += row["trips"]
    return [
        {
            "direction": direction,
            "headsign": _most_common_text(counts[direction])
            or _last_stop_name_of_direction(line, direction),
        }
        for direction in sorted(counts)
    ]


def _last_stop_name_of_direction(line: Line, direction: int) -> str:
    """Headsign fallback when no trip of the direction has one: the last stop of one of
    its trips."""
    trip_id = (
        Trip.objects.filter(_direction_q(direction), route_id=line.pk)
        .order_by("gtfs_id")
        .values_list("id", flat=True)
        .first()
    )
    if trip_id is None:
        return ""
    name = (
        StopTime.objects.filter(trip_id=trip_id)
        .order_by("-stop_sequence")
        .values_list("stop__name", flat=True)
        .first()
    )
    return name or ""


def _most_common_text(counter: Counter) -> str:
    for text, _count in counter.most_common():
        if text:
            return text
    return ""


@dataclass
class DirectionContext:
    """Trips and variants of one line and direction on one service date."""

    line: Line
    direction: int
    date: date
    calendar: ServiceCalendar
    directions: list[dict]
    variants: list[Variant]
    trips: dict[int, dict]  # trip pk -> {"headsign", "shape_id"}

    @property
    def main(self) -> Variant | None:
        return self.variants[0] if self.variants else None

    @property
    def headsign(self) -> str:
        for item in self.directions:
            if item["direction"] == self.direction:
                return item["headsign"]
        return ""


def direction_context(line: Line, direction: int | None, day: date) -> DirectionContext:
    """Trips of the line and direction that run on ``day`` or, if none run that day, on
    the nearest following day with service. ``direction=None`` means the lowest direction
    the line has. Raises DirectionNotFound."""
    directions = line_directions(line)
    existing = {item["direction"] for item in directions}
    if direction is None and existing:
        direction = min(existing)
    if direction not in existing:
        raise DirectionNotFound
    calendar = ServiceCalendar(line.feed_version_id)
    trips_qs = Trip.objects.filter(_direction_q(direction), route_id=line.pk)
    direction_services = set(trips_qs.values_list("service_id", flat=True).distinct())

    service_date, services = day, None
    for offset in range(SERVICE_LOOKAHEAD_DAYS + 1):
        try:
            candidate = day + timedelta(days=offset)
        except OverflowError:
            break
        active = calendar.services_on(candidate) & direction_services
        if active:
            service_date, services = candidate, active
            break
    if services is not None:
        trips_qs = trips_qs.filter(service_id__in=services)
    # Otherwise no service in the look-ahead window: use every trip of the direction.

    trips = {row["id"]: row for row in trips_qs.values("id", "headsign", "shape_id")}
    patterns = load_trip_patterns(trips)
    variants = build_variants(patterns, {pk: row["headsign"] for pk, row in trips.items()})
    return DirectionContext(
        line=line,
        direction=direction,
        date=service_date,
        calendar=calendar,
        directions=directions,
        variants=variants,
        trips=trips,
    )


# ---------------------------------------------------------------------------- stops


def _stops(pks) -> dict[int, dict]:
    rows = Stop.objects.filter(pk__in=list(pks)).values(
        "id", "gtfs_id", "name", "code", "point", "wheelchair_boarding"
    )
    return {row["id"]: row for row in rows}


def _stop_ref(stop: dict, feed_id: str) -> dict:
    return {"stop_id": make_id(feed_id, stop["gtfs_id"]), "name": stop["name"]}


def _variant_headsign(variant: Variant, stops: dict[int, dict]) -> str:
    if variant.headsign:
        return variant.headsign
    last = stops.get(variant.pattern[-1]) if variant.pattern else None
    return last["name"] if last else ""


def _routes_at_stops(stop_pks: set[int]) -> dict[int, set[int]]:
    """Route pks of the trips calling at each stop (cached per stop row)."""
    keys = {pk: f"timetable:stop_routes:{pk}" for pk in stop_pks}
    cached = cache.get_many(keys.values())
    result = {pk: set(cached[key]) for pk, key in keys.items() if key in cached}
    missing = [pk for pk in stop_pks if pk not in result]
    if missing:
        sql = (
            f"SELECT DISTINCT st.stop_id, t.route_id "  # noqa: S608
            f"FROM {StopTime._meta.db_table} st "
            f"JOIN {Trip._meta.db_table} t ON t.id = st.trip_id "
            f"WHERE st.stop_id = ANY(%s)"
        )
        found: dict[int, set[int]] = {pk: set() for pk in missing}
        with connection.cursor() as cursor:
            cursor.execute(sql, [missing])
            for stop_pk, route_pk in cursor.fetchall():
                found[stop_pk].add(route_pk)
        cache.set_many(
            {keys[pk]: sorted(routes) for pk, routes in found.items()},
            _STOP_ROUTES_CACHE_SECONDS,
        )
        result.update(found)
    return result


def _nearby_same_name(stop_pks: list[int], version_ids: list[int]) -> dict[int, set[int]]:
    """For each stop: stops of the active versions with the same name within the radius
    (including itself)."""
    table = Stop._meta.db_table
    sql = (
        f"SELECT s.id, n.id FROM {table} s "  # noqa: S608
        f"JOIN {table} n ON n.feed_version_id = ANY(%s) AND n.name = s.name "
        f"AND n.point && ST_Expand(s.point, %s) "
        f"AND ST_DWithin(n.point::geography, s.point::geography, %s) "
        f"WHERE s.id = ANY(%s)"
    )
    result: dict[int, set[int]] = {pk: {pk} for pk in stop_pks}
    with connection.cursor() as cursor:
        cursor.execute(sql, [version_ids, _TRANSFER_BBOX_DEGREES, TRANSFER_RADIUS_M, stop_pks])
        for stop_pk, near_pk in cursor.fetchall():
            result[stop_pk].add(near_pk)
    return result


def _transfers(city: City, feeds: Feeds, line: Line, stop_pks: list[int]) -> dict[int, list]:
    nearby = _nearby_same_name(stop_pks, feeds.version_ids)
    routes = _routes_at_stops(set().union(*nearby.values()) if nearby else set())
    route_pks_by_stop = {
        pk: set().union(*(routes.get(n, set()) for n in near)) - {line.pk}
        for pk, near in nearby.items()
    }
    lines = lines_by_pk(city, feeds, set().union(*route_pks_by_stop.values()))
    return {
        pk: [
            lines[route_pk].summary()
            for route_pk in sorted(
                (r for r in route_pks if r in lines), key=lambda r: lines[r].sort_key
            )
        ]
        for pk, route_pks in route_pks_by_stop.items()
    }


# ---------------------------------------------------------------------------- route


def _shape(context: DirectionContext, stops: dict[int, dict]) -> dict:
    main = context.main
    coordinates: list[list[float]] = []
    if main is not None:
        shape_ids = Counter(
            context.trips[trip]["shape_id"]
            for trip in main.trip_ids
            if context.trips[trip]["shape_id"] is not None
        )
        geometry = None
        if shape_ids:
            geometry = (
                Shape.objects.filter(pk=shape_ids.most_common(1)[0][0])
                .values_list("geometry", flat=True)
                .first()
            )
        if geometry is not None:
            coordinates = [[round(x, 6), round(y, 6)] for x, y in geometry.coords]
        else:
            for pk in main.pattern:
                point = stops.get(pk, {}).get("point")
                if point is not None:
                    coordinates.append([round(point.x, 6), round(point.y, 6)])
    return {"type": "LineString", "coordinates": coordinates}


def build_route(city: City, feeds: Feeds, context: DirectionContext) -> dict:
    line = context.line
    merged = merge_stops(context.variants)
    stop_pks = list(dict.fromkeys(pk for pk, _only in merged))
    stops = _stops(stop_pks)
    transfers = _transfers(city, feeds, line, stop_pks) if stop_pks else {}

    stop_items = []
    for pk, variant_only in merged:
        stop = stops.get(pk)
        if stop is None:
            continue
        point = stop["point"]
        stop_items.append(
            {
                "stop_id": make_id(line.feed_id, stop["gtfs_id"]),
                "name": stop["name"],
                "code": stop["code"] or None,
                "lat": round(point.y, 6) if point is not None else None,
                "lon": round(point.x, 6) if point is not None else None,
                "wheelchair_boarding": _wheelchair(stop["wheelchair_boarding"]),
                "variant_only": variant_only,
                "transfers": transfers.get(pk, []),
            }
        )
    return {
        "line": line.summary(),
        "direction": context.direction,
        "date": context.date,
        "directions": context.directions,
        "stops": stop_items,
        "variants": [
            {
                "id": variant.id,
                "kind": variant.kind,
                "headsign": _variant_headsign(variant, stops),
                "trip_count": variant.trip_count,
                "stop_ids": [
                    make_id(line.feed_id, stops[pk]["gtfs_id"])
                    for pk in variant.pattern
                    if pk in stops
                ],
            }
            for variant in context.variants
        ],
        "shape": _shape(context, stops),
    }


# ------------------------------------------------------------------------ timetable


def stop_served(line: Line, direction: int, stop: Stop) -> bool:
    return StopTime.objects.filter(
        _direction_q(direction, "trip__"), stop_id=stop.pk, trip__route_id=line.pk
    ).exists()


def _neighbours(context: DirectionContext, stop_pk: int) -> tuple[int | None, int | None]:
    """Previous and next stop on the main variant (or on the diagram, for stops that only
    other variants serve)."""
    main = context.main
    if main is None:
        return None, None
    sequence = list(main.pattern)
    if stop_pk not in sequence:
        sequence = [pk for pk, _only in merge_stops(context.variants)]
        if stop_pk not in sequence:
            return None, None
    index = sequence.index(stop_pk)
    previous = sequence[index - 1] if index > 0 else None
    following = sequence[index + 1] if index + 1 < len(sequence) else None
    return previous, following


def _expand_frequencies(rows: list[dict]) -> list[dict]:
    """Replace stop times of frequency-based trips (frequencies.txt, e.g. Warsaw metro) by
    one departure per headway; each keeps its offset from the trip's first departure."""
    trip_ids = {row["trip_id"] for row in rows}
    windows: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for trip_id, start, end, headway in Frequency.objects.filter(
        trip_id__in=trip_ids, headway_secs__gt=0
    ).values_list("trip_id", "start_time", "end_time", "headway_secs"):
        windows[trip_id].append((start, end, headway))
    if not windows:
        return rows
    first_departure = dict(
        StopTime.objects.filter(trip_id__in=list(windows))
        .values("trip_id")
        .annotate(first=Min("departure_time"))
        .values_list("trip_id", "first")
    )
    expanded = []
    for row in rows:
        trip_windows = windows.get(row["trip_id"])
        first = first_departure.get(row["trip_id"])
        if not trip_windows or first is None:
            expanded.append(row)
            continue
        offset = row["departure_time"] - first
        for start, end, headway in trip_windows:
            for trip_start in range(start, end, headway):
                expanded.append({**row, "departure_time": trip_start + offset})
    expanded.sort(key=lambda r: (r["departure_time"], r["trip__gtfs_id"]))
    return expanded


def build_timetable(
    city: City, feeds: Feeds, context: DirectionContext, stop: Stop, day: date
) -> dict:
    line = context.line
    calendar = context.calendar

    # The first date >= day of each day type, within the look-ahead window.
    column_dates: dict[str, date | None] = dict.fromkeys(DAY_TYPES)
    for offset in range(COLUMN_LOOKAHEAD_DAYS + 1):
        try:
            candidate = day + timedelta(days=offset)
        except OverflowError:
            break
        day_type = calendar.day_type(candidate)
        if column_dates[day_type] is None:
            column_dates[day_type] = candidate
        if all(column_dates.values()):
            break
    services_by_column = {
        day_type: calendar.services_on(column_date) if column_date else frozenset()
        for day_type, column_date in column_dates.items()
    }
    all_services = set().union(*services_by_column.values())

    has_later_stop = StopTime.objects.filter(
        trip_id=OuterRef("trip_id"), stop_sequence__gt=OuterRef("stop_sequence")
    )
    rows = (
        list(
            StopTime.objects.filter(
                _direction_q(context.direction, "trip__"),
                stop_id=stop.pk,
                trip__route_id=line.pk,
                trip__service_id__in=all_services,
                departure_time__isnull=False,
            )
            .exclude(pickup_type=PickupDropOff.NONE)
            # The last stop of a trip is an arrival, not a departure.
            .filter(Exists(has_later_stop))
            .values(
                "trip_id",
                "departure_time",
                "stop_headsign",
                "trip__gtfs_id",
                "trip__headsign",
                "trip__service_id",
                "trip__wheelchair_accessible",
            )
            .order_by("departure_time", "trip__gtfs_id")
        )
        if all_services
        else []
    )
    rows = _expand_frequencies(rows)

    trip_ids = {row["trip_id"] for row in rows}
    patterns = load_trip_patterns(trip_ids - set(context.trips))
    for variant in context.variants:
        for trip in variant.trip_ids:
            if trip in trip_ids:
                patterns[trip] = variant.pattern
    trip_headsigns = {row["trip_id"]: row["trip__headsign"] for row in rows}
    variant_of = extend_variants(context.variants, patterns, trip_headsigns)

    # Headsign fallback for trips without stop or trip headsign: their last stop's name.
    blank_last_stops = {
        row["trip_id"]: variant_of[row["trip_id"]].pattern[-1]
        for row in rows
        if not (row["stop_headsign"] or row["trip__headsign"])
        and row["trip_id"] in variant_of
        and variant_of[row["trip_id"]].pattern
    }
    last_stop_names = (
        {pk: stop["name"] for pk, stop in _stops(set(blank_last_stops.values())).items()}
        if blank_last_stops
        else {}
    )

    def departure_headsign(row: dict) -> str:
        return (
            row["stop_headsign"]
            or row["trip__headsign"]
            or last_stop_names.get(blank_last_stops.get(row["trip_id"]), "")
        )

    used_variants: dict[str, Variant] = {}
    columns = []
    for day_type in DAY_TYPES:
        services = services_by_column[day_type]
        hours: dict[int, list] = {}
        for row in rows:
            if row["trip__service_id"] not in services:
                continue
            variant = variant_of.get(row["trip_id"])
            markers = []
            if row["trip__wheelchair_accessible"] == Accessibility.YES:
                markers.append("low_floor")
            if variant is not None and variant.kind != MAIN:
                used_variants[variant.id] = variant
                markers.append("short_turn" if variant.kind == SHORT_TURN else "variant")
            seconds = row["departure_time"]
            time_text, next_day = clock_time(seconds)
            hours.setdefault(seconds // 3600, []).append(
                {
                    "minute": (seconds // 60) % 60,
                    "time": time_text,
                    "next_day": next_day,
                    "trip_id": make_id(line.feed_id, row["trip__gtfs_id"]),
                    "headsign": departure_headsign(row),
                    "markers": markers,
                    "variant": variant.id if variant is not None else None,
                }
            )
        columns.append(
            {
                "day_type": day_type,
                # Never None in practice: within 15 consecutive days every day type occurs
                # (days without service keep their weekday type); `or day` only guards
                # against the overflow break above.
                "date": column_dates[day_type] or day,
                "hours": [
                    {"hour": hour % 24, "departures": departures}
                    for hour, departures in sorted(hours.items())
                ],
            }
        )

    previous_pk, next_pk = _neighbours(context, stop.pk)
    neighbour_stops = _stops(
        {pk for pk in (previous_pk, next_pk) if pk is not None}
        | {pk for variant in used_variants.values() for pk in variant.pattern[-1:]}
    )

    def neighbour(pk: int | None) -> dict | None:
        found = neighbour_stops.get(pk) if pk is not None else None
        return _stop_ref(found, line.feed_id) if found else None

    return {
        "line": line.summary(),
        "stop": {
            "stop_id": make_id(line.feed_id, stop.gtfs_id),
            "name": stop.name,
            "code": stop.code or None,
        },
        "direction": context.direction,
        "headsign": context.headsign,
        "date": day,
        "day_type": calendar.day_type(day),
        "previous_stop": neighbour(previous_pk),
        "next_stop": neighbour(next_pk),
        "columns": columns,
        "variants": [
            {
                "id": variant.id,
                "kind": variant.kind,
                "headsign": _variant_headsign(variant, neighbour_stops),
            }
            for variant in sorted(used_variants.values(), key=lambda v: int(v.id[1:]))
        ],
    }


# ----------------------------------------------------------------------------- trip


def trip_runs_on(trip: Trip, day: date) -> bool:
    return trip.service_id in ServiceCalendar(trip.feed_version_id).services_on(day)


def build_trip(city: City, line: Line, trip: Trip, day: date) -> dict:
    tz = city.zoneinfo
    rows = (
        StopTime.objects.filter(trip_id=trip.pk)
        .order_by("stop_sequence")
        .values("stop__gtfs_id", "stop__name", "arrival_time", "departure_time")
    )
    stops = [
        {
            "stop_id": make_id(line.feed_id, row["stop__gtfs_id"]),
            "name": row["stop__name"],
            "arrival": gtfs_timestamp(day, row["arrival_time"], tz),
            "departure": gtfs_timestamp(day, row["departure_time"], tz),
        }
        for row in rows
        if row["stop__gtfs_id"] is not None
    ]
    headsign = trip.headsign or (stops[-1]["name"] if stops else "")
    return {
        "trip_id": make_id(line.feed_id, trip.gtfs_id),
        "date": day,
        "line": line.summary(),
        "direction": trip.direction_id or 0,
        "headsign": headsign,
        "wheelchair_accessible": _wheelchair(trip.wheelchair_accessible),
        "stops": stops,
    }
