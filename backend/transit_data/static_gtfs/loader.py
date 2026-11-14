"""Parse, validate and bulk load one GTFS feed into the tables of one FeedVersion.

Every table is written with PostgreSQL ``COPY ... FROM STDIN`` (psycopg 3). Rows are
streamed from the archive, validated one by one and skipped with a reason when they
cannot be stored; references between tables (trip -> route, stop_time -> trip/stop) are
resolved through ``gtfs_id -> database id`` maps read back after each parent table is
loaded. Shapes are aggregated into lines by PostGIS from a temporary table, so their
points never have to be held in Python memory.

``load_feed`` must run inside a transaction: on any exception the caller rolls back and
nothing of the new version remains.

Settings (optional, defaults in brackets):
- ``TRANSIT_GTFS_MAX_SKIPPED_RATIO`` [0.05] reject the feed when a larger share of the
  rows of stops, routes, trips or stop_times had to be skipped.
- ``TRANSIT_GTFS_EXPIRY_WARNING_DAYS`` [14] warn when service ends within this many days.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Iterable
from datetime import date

from django.conf import settings
from django.db import connection
from psycopg import sql

from ..models import (
    Agency,
    Calendar,
    CalendarDate,
    FeedVersion,
    Frequency,
    LocationType,
    Route,
    Shape,
    Stop,
    StopTime,
    Trip,
)
from .reader import GtfsSource
from .report import FileStats, ImportReport

logger = logging.getLogger(__name__)

# Hours above this in a GTFS time are treated as invalid (times past 24:00 are normal
# for trips after midnight; several days are not).
MAX_TIME_HOURS = 72
_COLOR_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
# Files whose skipped-row ratio decides whether the whole feed is rejected.
CHECKED_FILES = ("stops.txt", "routes.txt", "trips.txt", "stop_times.txt")


class FeedRejected(Exception):
    """The feed was read but is not good enough to replace the active version."""


# ------------------------------------------------------------------ value parsing


def parse_date(value: str) -> date:
    """GTFS date ``YYYYMMDD``. Raises ValueError."""
    value = value.strip()
    if len(value) != 8 or not value.isdigit():
        raise ValueError(value)
    return date(int(value[:4]), int(value[4:6]), int(value[6:]))


def parse_time(value: str) -> int | None:
    """GTFS time ``H:MM:SS`` (hours may exceed 23) as seconds; None when empty.

    Raises ValueError for malformed values.
    """
    value = value.strip()
    if not value:
        return None
    parts = value.split(":")
    if len(parts) != 3 or len(parts[1]) != 2 or len(parts[2]) != 2:
        raise ValueError(value)
    hours, minutes, seconds = (int(part) for part in parts)
    if not (0 <= hours <= MAX_TIME_HOURS and 0 <= minutes < 60 and 0 <= seconds < 60):
        raise ValueError(value)
    return hours * 3600 + minutes * 60 + seconds


class _TimeParser:
    """``parse_time`` with a cache: a feed uses far fewer distinct times than rows."""

    def __init__(self):
        self.cache: dict[str, int | None] = {}

    def __call__(self, value: str) -> int | None:
        try:
            return self.cache[value]
        except KeyError:
            result = self.cache[value] = parse_time(value)  # ValueError is not cached
            return result


def _enum(value: str, allowed: range, default, stats: FileStats, column: str):
    """Small integer enum; empty gives ``default``, invalid gives ``default`` + a note."""
    value = value.strip()
    if not value:
        return default
    try:
        number = int(value)
    except ValueError:
        number = None
    if number is None or number not in allowed:
        stats.correct(f"invalid {column}, used {default}")
        return default
    return number


def _color(value: str, stats: FileStats, column: str) -> str:
    value = value.strip().lstrip("#")
    if not value:
        return ""
    if not _COLOR_RE.match(value):
        stats.correct(f"invalid {column}, cleared")
        return ""
    return value.upper()


# ------------------------------------------------------------------------ loader


class _Loader:
    def __init__(self, feed_version: FeedVersion, source: GtfsSource, report: ImportReport):
        self.fv = feed_version
        self.fv_id = feed_version.pk
        self.city_id = feed_version.city_id
        self.source = source
        self.report = report
        self.times = _TimeParser()
        self.agency_ids: dict[str, int] = {}
        self.stop_ids: dict[str, int] = {}
        self.stop_types: dict[str, int] = {}  # gtfs stop_id -> location_type
        self.route_ids: dict[str, int] = {}
        self.service_ids: set[str] = set()
        self.shape_ids: dict[str, int] = {}
        self.trip_ids: dict[str, int] = {}

    # ---------------------------------------------------------------- helpers

    def cursor(self):
        # The psycopg cursor behind Django's wrapper; COPY is not wrapped by Django.
        return self._cursor.cursor

    def copy(self, model, columns: list[str], rows: Iterable[tuple]) -> int:
        statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
            sql.Identifier(model._meta.db_table),
            sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        )
        count = 0
        with self.cursor().copy(statement) as copy:
            write = copy.write_row
            for row in rows:
                write(row)
                count += 1
        return count

    def id_map(self, model, key: str = "gtfs_id") -> dict[str, int]:
        cursor = self.cursor()
        cursor.execute(
            sql.SQL("SELECT {}, id FROM {} WHERE feed_version_id = %s").format(
                sql.Identifier(key), sql.Identifier(model._meta.db_table)
            ),
            (self.fv_id,),
        )
        return dict(cursor.fetchall())

    # ------------------------------------------------------------------- run

    def run(self) -> None:
        with connection.cursor() as cursor:
            self._cursor = cursor
            self.report.ignored_files = self.source.ignored_files()
            self.load_feed_info()
            self.report.counts["agencies"] = self.load_agencies()
            self.report.counts["stops"] = self.load_stops()
            self.report.counts["routes"] = self.load_routes()
            self.report.counts["calendars"] = self.load_calendar()
            self.report.counts["calendar_dates"] = self.load_calendar_dates()
            self.report.counts["shapes"] = self.load_shapes()
            self.report.counts["trips"] = self.load_trips()
            self.report.counts["stop_times"] = self.load_stop_times()
            self.report.counts["frequencies"] = self.load_frequencies()
            self.check_trips_without_stop_times()
            self.compute_service_range()
        self.check_thresholds()

    # -------------------------------------------------------------- feed_info

    def load_feed_info(self) -> None:
        if not self.source.has("feed_info.txt"):
            return
        stats = self.report.file("feed_info.txt")
        with self.source.table("feed_info.txt") as table:
            for number, row in table.rows:
                stats.rows += 1
                if stats.rows > 1:
                    stats.skip(number, "more than one row")
                    continue
                fv = self.fv
                fv.publisher_name = row[table.col("feed_publisher_name")].strip()
                fv.publisher_url = row[table.col("feed_publisher_url")].strip()
                fv.feed_lang = row[table.col("feed_lang")].strip()[:35]
                fv.feed_info_version = row[table.col("feed_version")].strip()
                for column, attr in (
                    ("feed_start_date", "feed_start_date"),
                    ("feed_end_date", "feed_end_date"),
                ):
                    value = row[table.col(column)].strip()
                    if value:
                        try:
                            setattr(fv, attr, parse_date(value))
                        except ValueError:
                            stats.correct(f"invalid {column}, cleared")
                stats.imported += 1

    # ----------------------------------------------------------------- agency

    def load_agencies(self) -> int:
        stats = self.report.file("agency.txt")
        seen: set[str] = set()

        def rows():
            with self.source.table("agency.txt") as t:
                c_id, c_name, c_url, c_tz, c_lang, c_phone = (
                    t.col(c)
                    for c in (
                        "agency_id",
                        "agency_name",
                        "agency_url",
                        "agency_timezone",
                        "agency_lang",
                        "agency_phone",
                    )
                )
                for number, row in t.rows:
                    stats.rows += 1
                    agency_id = row[c_id].strip()
                    if agency_id in seen:
                        stats.skip(number, "duplicate agency_id", agency_id)
                        continue
                    seen.add(agency_id)
                    yield (
                        self.fv_id,
                        agency_id,
                        row[c_name].strip(),
                        row[c_url].strip(),
                        row[c_tz].strip()[:64],
                        row[c_lang].strip()[:35],
                        row[c_phone].strip(),
                    )

        count = self.copy(
            Agency,
            ["feed_version_id", "gtfs_id", "name", "url", "timezone", "lang", "phone"],
            rows(),
        )
        stats.imported = count
        self.agency_ids = self.id_map(Agency)
        return count

    # ------------------------------------------------------------------ stops

    def load_stops(self) -> int:
        stats = self.report.file("stops.txt")
        seen: set[str] = set()
        parents: dict[str, str] = {}

        def rows():
            with self.source.table("stops.txt") as t:
                c = {
                    name: t.col(name)
                    for name in (
                        "stop_id",
                        "stop_code",
                        "stop_name",
                        "stop_desc",
                        "stop_lat",
                        "stop_lon",
                        "location_type",
                        "parent_station",
                        "wheelchair_boarding",
                        "platform_code",
                        "zone_id",
                    )
                }
                for number, row in t.rows:
                    stats.rows += 1
                    stop_id = row[c["stop_id"]].strip()
                    if not stop_id:
                        stats.skip(number, "missing stop_id")
                        continue
                    if stop_id in seen:
                        stats.skip(number, "duplicate stop_id", stop_id)
                        continue
                    location_type = _enum(
                        row[c["location_type"]], range(5), 0, stats, "location_type"
                    )
                    point = None
                    lat_text, lon_text = row[c["stop_lat"]].strip(), row[c["stop_lon"]].strip()
                    if lat_text or lon_text:
                        try:
                            lat, lon = float(lat_text), float(lon_text)
                        except ValueError:
                            lat = lon = math.nan
                        if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0, 0):
                            point = f"SRID=4326;POINT({lon!r} {lat!r})"
                    if point is None and location_type <= 2:
                        stats.skip(number, "missing or invalid coordinates", stop_id)
                        continue
                    seen.add(stop_id)
                    self.stop_types[stop_id] = location_type
                    parent = row[c["parent_station"]].strip()
                    if parent:
                        parents[stop_id] = parent
                    yield (
                        self.fv_id,
                        self.city_id,
                        stop_id,
                        row[c["stop_code"]].strip(),
                        row[c["stop_name"]].strip(),
                        row[c["stop_desc"]].strip(),
                        point,
                        location_type,
                        _enum(
                            row[c["wheelchair_boarding"]],
                            range(3),
                            0,
                            stats,
                            "wheelchair_boarding",
                        ),
                        row[c["platform_code"]].strip(),
                        row[c["zone_id"]].strip(),
                    )

        count = self.copy(
            Stop,
            [
                "feed_version_id",
                "city_id",
                "gtfs_id",
                "code",
                "name",
                "desc",
                "point",
                "location_type",
                "wheelchair_boarding",
                "platform_code",
                "zone_id",
            ],
            rows(),
        )
        stats.imported = count
        self.stop_ids = self.id_map(Stop)
        self._link_parent_stations(parents, stats)
        return count

    def _link_parent_stations(self, parents: dict[str, str], stats: FileStats) -> None:
        """Set parent_station following the GTFS hierarchy; invalid links are cleared.

        Stops, entrances and generic nodes (0, 2, 3) belong to a station (1); boarding
        areas (4) belong to a platform (0); stations have no parent.
        """
        pairs = []
        for child, parent in parents.items():
            parent_pk = self.stop_ids.get(parent)
            if parent_pk is None or parent == child:
                stats.correct("unknown parent_station, cleared")
                continue
            child_type = self.stop_types[child]
            if child_type == LocationType.STATION:
                stats.correct("parent_station on a station, cleared")
                continue
            expected = (
                LocationType.STOP
                if child_type == LocationType.BOARDING_AREA
                else LocationType.STATION
            )
            if self.stop_types[parent] != expected:
                stats.correct(
                    f"parent_station has location_type {self.stop_types[parent]}"
                    f" instead of {int(expected)}, cleared"
                )
                continue
            pairs.append((self.stop_ids[child], parent_pk))
        if not pairs:
            return
        cursor = self.cursor()
        # pg_temp-qualified so that a regular table with the same name is never touched.
        cursor.execute("DROP TABLE IF EXISTS pg_temp.gtfs_import_parent")
        cursor.execute("CREATE TEMP TABLE gtfs_import_parent (child bigint, parent bigint)")
        with cursor.copy("COPY pg_temp.gtfs_import_parent (child, parent) FROM STDIN") as copy:
            for pair in pairs:
                copy.write_row(pair)
        cursor.execute(
            sql.SQL(
                "UPDATE {} AS s SET parent_station_id = p.parent"
                " FROM pg_temp.gtfs_import_parent AS p WHERE s.id = p.child"
            ).format(sql.Identifier(Stop._meta.db_table))
        )
        cursor.execute("DROP TABLE pg_temp.gtfs_import_parent")

    # ----------------------------------------------------------------- routes

    def load_routes(self) -> int:
        stats = self.report.file("routes.txt")
        seen: set[str] = set()
        single_agency = next(iter(self.agency_ids.values())) if len(self.agency_ids) == 1 else None

        def rows():
            with self.source.table("routes.txt") as t:
                c = {
                    name: t.col(name)
                    for name in (
                        "route_id",
                        "agency_id",
                        "route_short_name",
                        "route_long_name",
                        "route_desc",
                        "route_type",
                        "route_color",
                        "route_text_color",
                        "route_sort_order",
                    )
                }
                for number, row in t.rows:
                    stats.rows += 1
                    route_id = row[c["route_id"]].strip()
                    if not route_id:
                        stats.skip(number, "missing route_id")
                        continue
                    if route_id in seen:
                        stats.skip(number, "duplicate route_id", route_id)
                        continue
                    try:
                        route_type = int(row[c["route_type"]].strip())
                        if not 0 <= route_type <= 32767:
                            raise ValueError
                    except ValueError:
                        stats.skip(number, "invalid route_type", row[c["route_type"]])
                        continue
                    agency_id = row[c["agency_id"]].strip()
                    agency_pk = self.agency_ids.get(agency_id) if agency_id else single_agency
                    if agency_pk is None:
                        stats.correct("unknown agency_id, cleared")
                    sort_text = row[c["route_sort_order"]].strip()
                    try:
                        sort_order = int(sort_text) if sort_text else None
                    except ValueError:
                        sort_order = None
                        stats.correct("invalid route_sort_order, cleared")
                    seen.add(route_id)
                    yield (
                        self.fv_id,
                        self.city_id,
                        route_id,
                        agency_pk,
                        row[c["route_short_name"]].strip(),
                        row[c["route_long_name"]].strip(),
                        row[c["route_desc"]].strip(),
                        route_type,
                        _color(row[c["route_color"]], stats, "route_color"),
                        _color(row[c["route_text_color"]], stats, "route_text_color"),
                        sort_order,
                    )

        count = self.copy(
            Route,
            [
                "feed_version_id",
                "city_id",
                "gtfs_id",
                "agency_id",
                "short_name",
                "long_name",
                "desc",
                "route_type",
                "color",
                "text_color",
                "sort_order",
            ],
            rows(),
        )
        stats.imported = count
        self.route_ids = self.id_map(Route)
        return count

    # --------------------------------------------------------------- calendar

    def load_calendar(self) -> int:
        if not self.source.has("calendar.txt"):
            return 0
        stats = self.report.file("calendar.txt")
        days = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

        def rows():
            with self.source.table("calendar.txt") as t:
                c_service = t.col("service_id")
                c_days = [t.col(day) for day in days]
                c_start, c_end = t.col("start_date"), t.col("end_date")
                for number, row in t.rows:
                    stats.rows += 1
                    service_id = row[c_service].strip()
                    if not service_id:
                        stats.skip(number, "missing service_id")
                        continue
                    if service_id in self.service_ids:
                        stats.skip(number, "duplicate service_id", service_id)
                        continue
                    flags = [row[i].strip() for i in c_days]
                    if any(flag not in ("0", "1") for flag in flags):
                        stats.skip(number, "invalid weekday flag", service_id)
                        continue
                    try:
                        start, end = parse_date(row[c_start]), parse_date(row[c_end])
                    except ValueError:
                        stats.skip(number, "invalid start_date or end_date", service_id)
                        continue
                    self.service_ids.add(service_id)
                    yield (self.fv_id, service_id, *(flag == "1" for flag in flags), start, end)

        count = self.copy(
            Calendar, ["feed_version_id", "service_id", *days, "start_date", "end_date"], rows()
        )
        stats.imported = count
        return count

    def load_calendar_dates(self) -> int:
        if not self.source.has("calendar_dates.txt"):
            return 0
        stats = self.report.file("calendar_dates.txt")
        seen: set[tuple[str, date]] = set()
        services: set[str] = set()

        def rows():
            with self.source.table("calendar_dates.txt") as t:
                c_service, c_date, c_type = (
                    t.col("service_id"),
                    t.col("date"),
                    t.col("exception_type"),
                )
                for number, row in t.rows:
                    stats.rows += 1
                    service_id = row[c_service].strip()
                    if not service_id:
                        stats.skip(number, "missing service_id")
                        continue
                    try:
                        day = parse_date(row[c_date])
                    except ValueError:
                        stats.skip(number, "invalid date", row[c_date])
                        continue
                    exception_type = row[c_type].strip()
                    if exception_type not in ("1", "2"):
                        stats.skip(number, "invalid exception_type", exception_type)
                        continue
                    key = (service_id, day)
                    if key in seen:
                        stats.skip(number, "duplicate service_id and date", service_id)
                        continue
                    seen.add(key)
                    services.add(service_id)
                    yield (self.fv_id, service_id, day, int(exception_type))

        count = self.copy(
            CalendarDate, ["feed_version_id", "service_id", "date", "exception_type"], rows()
        )
        stats.imported = count
        self.service_ids |= services
        return count

    # ----------------------------------------------------------------- shapes

    def load_shapes(self) -> int:
        if not self.source.has("shapes.txt"):
            return 0
        stats = self.report.file("shapes.txt")
        cursor = self.cursor()
        cursor.execute("DROP TABLE IF EXISTS pg_temp.gtfs_import_shape_point")
        cursor.execute(
            "CREATE TEMP TABLE pg_temp.gtfs_import_shape_point"
            " (shape_id text, seq bigint, lon double precision, lat double precision)"
        )

        def rows():
            with self.source.table("shapes.txt") as t:
                c_id, c_lat, c_lon, c_seq = (
                    t.col("shape_id"),
                    t.col("shape_pt_lat"),
                    t.col("shape_pt_lon"),
                    t.col("shape_pt_sequence"),
                )
                for number, row in t.rows:
                    stats.rows += 1
                    shape_id = row[c_id].strip()
                    if not shape_id:
                        stats.skip(number, "missing shape_id")
                        continue
                    try:
                        lat, lon = float(row[c_lat]), float(row[c_lon])
                        seq = int(row[c_seq])
                    except ValueError:
                        stats.skip(number, "invalid coordinates or sequence", shape_id)
                        continue
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= seq < 2**62):
                        stats.skip(number, "invalid coordinates or sequence", shape_id)
                        continue
                    yield (shape_id, seq, lon, lat)

        points = 0
        with cursor.copy(
            "COPY pg_temp.gtfs_import_shape_point (shape_id, seq, lon, lat) FROM STDIN"
        ) as copy:
            for row in rows():
                copy.write_row(row)
                points += 1
        stats.imported = points
        cursor.execute(
            "SELECT count(*) FROM (SELECT 1 FROM pg_temp.gtfs_import_shape_point"
            " GROUP BY shape_id HAVING count(*) < 2) AS short"
        )
        too_short = cursor.fetchone()[0]
        if too_short:
            stats.correct(f"{too_short} shapes with fewer than 2 points not stored")
        cursor.execute(
            sql.SQL(
                "INSERT INTO {} (feed_version_id, gtfs_id, geometry)"
                " SELECT %s, shape_id,"
                " ST_SetSRID(ST_MakeLine(ST_MakePoint(lon, lat) ORDER BY seq), 4326)"
                " FROM pg_temp.gtfs_import_shape_point GROUP BY shape_id HAVING count(*) >= 2"
            ).format(sql.Identifier(Shape._meta.db_table)),
            (self.fv_id,),
        )
        count = cursor.rowcount
        cursor.execute("DROP TABLE pg_temp.gtfs_import_shape_point")
        self.shape_ids = self.id_map(Shape)
        return count

    # ------------------------------------------------------------------ trips

    def load_trips(self) -> int:
        stats = self.report.file("trips.txt")
        seen: set[str] = set()

        def rows():
            with self.source.table("trips.txt") as t:
                c = {
                    name: t.col(name)
                    for name in (
                        "trip_id",
                        "route_id",
                        "service_id",
                        "trip_headsign",
                        "trip_short_name",
                        "direction_id",
                        "block_id",
                        "shape_id",
                        "wheelchair_accessible",
                        "bikes_allowed",
                    )
                }
                for number, row in t.rows:
                    stats.rows += 1
                    trip_id = row[c["trip_id"]].strip()
                    if not trip_id:
                        stats.skip(number, "missing trip_id")
                        continue
                    if trip_id in seen:
                        stats.skip(number, "duplicate trip_id", trip_id)
                        continue
                    route_pk = self.route_ids.get(row[c["route_id"]].strip())
                    if route_pk is None:
                        stats.skip(number, "unknown route_id", row[c["route_id"]])
                        continue
                    service_id = row[c["service_id"]].strip()
                    if service_id not in self.service_ids:
                        stats.skip(number, "unknown service_id", service_id)
                        continue
                    shape_id = row[c["shape_id"]].strip()
                    shape_pk = self.shape_ids.get(shape_id) if shape_id else None
                    if shape_id and shape_pk is None:
                        stats.correct("unknown shape_id, cleared")
                    seen.add(trip_id)
                    yield (
                        self.fv_id,
                        trip_id,
                        route_pk,
                        service_id,
                        row[c["trip_headsign"]].strip(),
                        row[c["trip_short_name"]].strip(),
                        _enum(row[c["direction_id"]], range(2), None, stats, "direction_id"),
                        row[c["block_id"]].strip(),
                        shape_pk,
                        _enum(
                            row[c["wheelchair_accessible"]],
                            range(3),
                            0,
                            stats,
                            "wheelchair_accessible",
                        ),
                        _enum(row[c["bikes_allowed"]], range(3), 0, stats, "bikes_allowed"),
                    )

        count = self.copy(
            Trip,
            [
                "feed_version_id",
                "gtfs_id",
                "route_id",
                "service_id",
                "headsign",
                "short_name",
                "direction_id",
                "block_id",
                "shape_id",
                "wheelchair_accessible",
                "bikes_allowed",
            ],
            rows(),
        )
        stats.imported = count
        self.trip_ids = self.id_map(Trip)
        return count

    # ------------------------------------------------------------- stop_times

    def load_stop_times(self) -> int:
        """The hot loop (millions of rows for big feeds): plain locals, no helper calls on
        the common path."""
        stats = self.report.file("stop_times.txt")
        trip_ids, times, fv_id = self.trip_ids, self.times, self.fv_id
        # Only stops / platforms (location_type 0) may be served; stations, entrances,
        # nodes and boarding areas are looked up separately for the skip reason.
        stop_ids = {
            gtfs_id: pk
            for gtfs_id, pk in self.stop_ids.items()
            if self.stop_types.get(gtfs_id) == LocationType.STOP
        }
        stop_types = self.stop_types
        pickup_values = {"": 0, "0": 0, "1": 1, "2": 2, "3": 3}
        timepoint_values = {"": None, "0": 0, "1": 1}
        read = 0

        def rows():
            nonlocal read
            with self.source.table("stop_times.txt") as t:
                c_trip, c_stop, c_seq = t.col("trip_id"), t.col("stop_id"), t.col("stop_sequence")
                c_arr, c_dep = t.col("arrival_time"), t.col("departure_time")
                c_headsign, c_pickup, c_drop = (
                    t.col("stop_headsign"),
                    t.col("pickup_type"),
                    t.col("drop_off_type"),
                )
                c_dist, c_timepoint = t.col("shape_dist_traveled"), t.col("timepoint")
                for number, row in t.rows:
                    read += 1
                    trip_pk = trip_ids.get(row[c_trip]) or trip_ids.get(row[c_trip].strip())
                    if trip_pk is None:
                        stats.skip(number, "unknown trip_id", row[c_trip])
                        continue
                    stop_pk = stop_ids.get(row[c_stop]) or stop_ids.get(row[c_stop].strip())
                    if stop_pk is None:
                        location_type = stop_types.get(row[c_stop].strip())
                        if location_type is None:
                            reason = "unknown stop_id"
                        else:
                            reason = (
                                f"stop_id is not a stop or platform (location_type {location_type})"
                            )
                        stats.skip(number, reason, row[c_stop])
                        continue
                    try:
                        seq = int(row[c_seq])
                        if not 0 <= seq <= 2147483647:
                            raise ValueError
                    except ValueError:
                        stats.skip(number, "invalid stop_sequence", row[c_seq])
                        continue
                    try:
                        arrival = times(row[c_arr])
                        departure = times(row[c_dep])
                    except ValueError:
                        stats.skip(number, "invalid arrival_time or departure_time")
                        continue
                    if arrival is None:
                        arrival = departure
                    elif departure is None:
                        departure = arrival
                    pickup = pickup_values.get(row[c_pickup])
                    if pickup is None:
                        pickup = _enum(row[c_pickup], range(4), 0, stats, "pickup_type")
                    drop_off = pickup_values.get(row[c_drop])
                    if drop_off is None:
                        drop_off = _enum(row[c_drop], range(4), 0, stats, "drop_off_type")
                    dist_text = row[c_dist]
                    if dist_text:
                        try:
                            dist = float(dist_text)
                            if not math.isfinite(dist):
                                raise ValueError
                        except ValueError:
                            dist = None
                            stats.correct("invalid shape_dist_traveled, cleared")
                    else:
                        dist = None
                    timepoint_text = row[c_timepoint]
                    if timepoint_text in timepoint_values:
                        timepoint = timepoint_values[timepoint_text]
                    else:
                        timepoint = _enum(timepoint_text, range(2), None, stats, "timepoint")
                    yield (
                        fv_id,
                        trip_pk,
                        stop_pk,
                        seq,
                        arrival,
                        departure,
                        row[c_headsign],
                        pickup,
                        drop_off,
                        dist,
                        timepoint,
                    )

        count = self.copy(
            StopTime,
            [
                "feed_version_id",
                "trip_id",
                "stop_id",
                "stop_sequence",
                "arrival_time",
                "departure_time",
                "stop_headsign",
                "pickup_type",
                "drop_off_type",
                "shape_dist_traveled",
                "timepoint",
            ],
            rows(),
        )
        stats.rows = read
        stats.imported = count
        return count

    # ------------------------------------------------------------ frequencies

    def load_frequencies(self) -> int:
        if not self.source.has("frequencies.txt"):
            return 0
        stats = self.report.file("frequencies.txt")

        def rows():
            with self.source.table("frequencies.txt") as t:
                c_trip, c_start, c_end, c_headway, c_exact = (
                    t.col("trip_id"),
                    t.col("start_time"),
                    t.col("end_time"),
                    t.col("headway_secs"),
                    t.col("exact_times"),
                )
                for number, row in t.rows:
                    stats.rows += 1
                    trip_pk = self.trip_ids.get(row[c_trip].strip())
                    if trip_pk is None:
                        stats.skip(number, "unknown trip_id", row[c_trip])
                        continue
                    try:
                        start, end = parse_time(row[c_start]), parse_time(row[c_end])
                        headway = int(row[c_headway])
                        if start is None or end is None or headway <= 0:
                            raise ValueError
                    except ValueError:
                        stats.skip(number, "invalid start_time, end_time or headway_secs")
                        continue
                    exact = _enum(row[c_exact], range(2), 0, stats, "exact_times")
                    yield (self.fv_id, trip_pk, start, end, headway, exact == 1)

        count = self.copy(
            Frequency,
            ["feed_version_id", "trip_id", "start_time", "end_time", "headway_secs", "exact_times"],
            rows(),
        )
        stats.imported = count
        return count

    # ------------------------------------------------------------ post checks

    def check_trips_without_stop_times(self) -> None:
        cursor = self.cursor()
        cursor.execute(
            sql.SQL(
                "SELECT count(*) FROM {trip} AS t WHERE t.feed_version_id = %s"
                " AND NOT EXISTS (SELECT 1 FROM {stop_time} AS st WHERE st.trip_id = t.id)"
            ).format(
                trip=sql.Identifier(Trip._meta.db_table),
                stop_time=sql.Identifier(StopTime._meta.db_table),
            ),
            (self.fv_id,),
        )
        empty = cursor.fetchone()[0]
        if empty:
            self.report.warn(f"{empty} trips have no stop times")

    def compute_service_range(self) -> None:
        cursor = self.cursor()
        # Only calendars with at least one weekday add service days.
        cursor.execute(
            sql.SQL(
                "SELECT min(start_date), max(end_date) FROM {} WHERE feed_version_id = %s"
                " AND (monday OR tuesday OR wednesday OR thursday OR friday"
                " OR saturday OR sunday)"
            ).format(sql.Identifier(Calendar._meta.db_table)),
            (self.fv_id,),
        )
        candidates = [cursor.fetchone()]
        cursor.execute(
            sql.SQL(
                "SELECT min(date), max(date) FROM {}"
                " WHERE feed_version_id = %s AND exception_type = 1"
            ).format(sql.Identifier(CalendarDate._meta.db_table)),
            (self.fv_id,),
        )
        candidates.append(cursor.fetchone())
        starts = [row[0] for row in candidates if row[0] is not None]
        ends = [row[1] for row in candidates if row[1] is not None]
        self.fv.service_start_date = min(starts) if starts else None
        self.fv.service_end_date = max(ends) if ends else None
        if not ends:
            self.report.warn("no service days in calendar.txt or calendar_dates.txt")

    def check_thresholds(self) -> None:
        max_ratio = getattr(settings, "TRANSIT_GTFS_MAX_SKIPPED_RATIO", 0.05)
        problems = []
        for name in CHECKED_FILES:
            stats = self.report.file(name)
            if stats.imported == 0:
                problems.append(f"no valid rows in {name}")
            elif stats.skipped_ratio > max_ratio:
                problems.append(
                    f"{stats.skipped} of {stats.rows} rows skipped in {name}"
                    f" (limit {max_ratio:.0%})"
                )
        if problems:
            raise FeedRejected("; ".join(problems))


def load_feed(feed_version: FeedVersion, source: GtfsSource, report: ImportReport) -> None:
    """Load ``source`` into ``feed_version`` (which must already be saved).

    Must be called inside ``transaction.atomic()``. Fills ``report`` and the feed_info /
    service-range fields of ``feed_version`` (not saved here). Raises FeedRejected when the
    feed is not acceptable; any exception means the caller must roll back.
    """
    _Loader(feed_version, source, report).run()


def expiry_warning(service_end: date | None, today: date) -> str | None:
    """Warning text when service ends soon or has ended, else None."""
    if service_end is None:
        return None
    days = (service_end - today).days
    if days < 0:
        return f"service ended on {service_end.isoformat()} ({-days} days ago)"
    if days <= getattr(settings, "TRANSIT_GTFS_EXPIRY_WARNING_DAYS", 14):
        return f"service ends on {service_end.isoformat()} (in {days} days)"
    return None
