"""Cut a large GTFS feed down to the area one city needs (e.g. the national rail feed).

A feed in city config may carry a ``filter`` (see ``AreaFilter.from_config``)::

    - id: rail
      url: https://...
      filter:
        bbox: [min_lon, min_lat, max_lon, max_lat]
        exclude_agencies: [SKM]   # optional: agency_ids already served by another feed

``filter_feed`` streams the source archive and writes a smaller, self-consistent GTFS zip:

- a stop is *in the area* when its own position (or, without one, its parent station's)
  lies inside ``bbox``;
- a trip is kept when its route's agency is not excluded and it has at least
  ``MIN_STOPS_IN_AREA`` *timed* calls (arrival or departure time given) inside the area;
  only its inside calls from the first to the last timed one are kept (the trip is
  clipped to the area and starts and ends with a timed call, as GTFS requires;
  ``trip_headsign`` still names the real destination);
- a trip that leaves the bbox and comes back keeps only its inside calls, so it appears to
  run directly between the last call before it leaves and the first call after it returns;
- agencies are kept when a kept route names them; all of them are kept when the feed has
  one agency or a kept route leaves ``agency_id`` blank;
- routes, services (calendar, calendar_dates), frequencies and shapes are kept
  only when a kept trip uses them; stops when a kept stop time uses them, plus their parent
  stations; transfers only between kept stops (and kept trips, when given);
- a shape is clipped to the ``shape_dist_traveled`` range of the kept stop times of its
  trips (plus one point on each side), when both files give distances; otherwise it is
  kept whole;
- ``feed_info.txt`` and ``attributions.txt`` are copied unchanged; other files are dropped.

The result is deterministic for the same input and filter, so re-imports are idempotent.
Memory stays proportional to stops, trips and shapes, never to stop times or shape points
(those are streamed twice).
"""

from __future__ import annotations

import csv
import io
import math
import zipfile
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .reader import GtfsSource, Table

# A trip needs at least two calls inside the area to be ridden there.
MIN_STOPS_IN_AREA = 2

COPIED_FILES = ("feed_info.txt", "attributions.txt")


class AreaFilterError(Exception):
    """The filter config is invalid, or the filtered feed would be empty."""


@dataclass(frozen=True)
class AreaFilter:
    bbox: tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)
    exclude_agencies: frozenset[str] = frozenset()

    @classmethod
    def from_config(cls, raw: Any) -> AreaFilter | None:
        """Build from a feed's ``filter``: a mapping or an object with the same attributes
        (the parsed city config). None stays None. Raises AreaFilterError."""
        if raw is None:
            return None
        get = raw.get if isinstance(raw, dict) else lambda key: getattr(raw, key, None)
        bbox_raw = get("bbox")
        try:
            bbox = tuple(float(value) for value in bbox_raw)
        except (TypeError, ValueError) as exc:
            raise AreaFilterError(f"invalid filter bbox {bbox_raw!r}") from exc
        if len(bbox) != 4 or not all(math.isfinite(value) for value in bbox):
            raise AreaFilterError(f"invalid filter bbox {bbox_raw!r}: expected 4 numbers")
        min_lon, min_lat, max_lon, max_lat = bbox
        if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
            raise AreaFilterError(
                f"invalid filter bbox {bbox_raw!r}: expected min_lon, min_lat, max_lon, max_lat"
            )
        agencies = get("exclude_agencies") or ()
        if isinstance(agencies, str) or not all(isinstance(a, str) for a in agencies):
            raise AreaFilterError(f"invalid filter exclude_agencies {agencies!r}")
        return cls(bbox=bbox, exclude_agencies=frozenset(a.strip() for a in agencies))

    def contains(self, lat: float, lon: float) -> bool:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat

    def as_dict(self) -> dict:
        """Stable, JSON-friendly form; equal filters give equal dicts."""
        return {
            "bbox": [round(value, 6) for value in self.bbox],
            "exclude_agencies": sorted(self.exclude_agencies),
            "min_stops_in_area": MIN_STOPS_IN_AREA,
        }


def feed_area_filter(feed: Any) -> AreaFilter | None:
    """The AreaFilter of a city config feed, or None (also for registries without it)."""
    return AreaFilter.from_config(getattr(feed, "filter", None))


@dataclass
class FilterStats:
    config: dict
    rows_read: Counter = field(default_factory=Counter)
    rows_kept: Counter = field(default_factory=Counter)
    dropped_files: list[str] = field(default_factory=list)
    trips_excluded_agency: int = 0
    trips_outside_area: int = 0
    shapes_clipped: int = 0

    def as_dict(self) -> dict:
        return {
            "config": self.config,
            "files": {
                name: {"read": self.rows_read[name], "kept": self.rows_kept[name]}
                for name in sorted(self.rows_read)
            },
            "dropped_files": list(self.dropped_files),
            "trips_excluded_agency": self.trips_excluded_agency,
            "trips_outside_area": self.trips_outside_area,
            "shapes_clipped": self.shapes_clipped,
        }


def _float(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _header(table: Table) -> list[str]:
    names = [""] * table.width
    for name, index in table.columns.items():
        names[index] = name
    # Duplicate column names keep only their first index in ``columns``; give the others
    # a placeholder so every row keeps its width.
    return [name or f"unnamed_{index}" for index, name in enumerate(names)]


class _Writer:
    """Writes filtered tables into the output zip, counting rows."""

    def __init__(self, archive: zipfile.ZipFile, stats: FilterStats):
        self.archive = archive
        self.stats = stats

    def write(self, name: str, header: list[str], rows: Iterable[list[str]]) -> None:
        # A fixed timestamp keeps the archive byte-identical for the same input.
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        with self.archive.open(info, "w") as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            writer = csv.writer(text, lineterminator="\n")
            writer.writerow(header)
            width = len(header)
            kept = 0
            for row in rows:
                writer.writerow(row[:width])
                kept += 1
            text.flush()
            text.detach()
        self.stats.rows_kept[name] += kept


def _counted(stats: FilterStats, name: str, rows: Iterator[tuple[int, list[str]]]):
    for _number, row in rows:
        stats.rows_read[name] += 1
        yield row


def filter_feed(
    source_path: Path,
    target_path: Path,
    area: AreaFilter,
    max_uncompressed_bytes: int | None = None,
) -> FilterStats:
    """Write the part of the GTFS feed at ``source_path`` inside ``area`` to the zip file
    ``target_path``. Raises AreaFilterError when no trip is left, GtfsFormatError (from the
    reader) for an unreadable archive or one larger than ``max_uncompressed_bytes``
    unpacked."""
    stats = FilterStats(config=area.as_dict())
    with GtfsSource(source_path, max_uncompressed_bytes=max_uncompressed_bytes) as source:
        missing = [
            name
            for name in ("stops.txt", "routes.txt", "trips.txt", "stop_times.txt")
            if not source.has(name)
        ]
        if missing:
            raise AreaFilterError(f"cannot filter feed: missing {', '.join(missing)}")

        # ------------------------------------------------------------ stops in area
        positions: dict[str, tuple[float, float] | None] = {}
        parents: dict[str, str] = {}
        with source.table("stops.txt") as t:
            c_id, c_lat, c_lon = t.col("stop_id"), t.col("stop_lat"), t.col("stop_lon")
            c_parent = t.col("parent_station")
            for _number, row in t.rows:
                stop_id = row[c_id].strip()
                if stop_id in positions:
                    continue  # duplicate: the loader keeps only the first row
                lat, lon = _float(row[c_lat]), _float(row[c_lon])
                # Same rule as the loader (loader._point): a stop without usable
                # coordinates takes its nearest ancestor's position.
                usable = (
                    lat is not None
                    and lon is not None
                    and -90 <= lat <= 90
                    and -180 <= lon <= 180
                    and (lat, lon) != (0, 0)
                )
                positions[stop_id] = (lat, lon) if usable else None
                if row[c_parent].strip():
                    parents[stop_id] = row[c_parent].strip()

        def position(stop_id: str) -> tuple[float, float] | None:
            seen = set()
            while stop_id and stop_id not in seen:
                seen.add(stop_id)
                found = positions.get(stop_id)
                if found is not None:
                    return found
                stop_id = parents.get(stop_id, "")
            return None

        in_area = set()
        for stop_id in positions:
            found = position(stop_id)
            if found is not None and area.contains(*found):
                in_area.add(stop_id)

        # ------------------------------------------------- candidate trips by agency
        route_agency: dict[str, str] = {}
        with source.table("routes.txt") as t:
            c_route, c_agency = t.col("route_id"), t.col("agency_id")
            for _number, row in t.rows:
                route_agency[row[c_route].strip()] = row[c_agency].strip()
        excluded_routes = {
            route for route, agency in route_agency.items() if agency in area.exclude_agencies
        }

        candidate_trips: set[str] = set()
        with source.table("trips.txt") as t:
            c_trip, c_route = t.col("trip_id"), t.col("route_id")
            for _number, row in t.rows:
                if row[c_route].strip() in excluded_routes:
                    stats.trips_excluded_agency += 1
                else:
                    candidate_trips.add(row[c_trip].strip())

        # ------------------------------------- stop_times pass 1: calls in the area
        # trip_id -> [timed calls inside, lowest and highest stop_sequence of those calls].
        # A clipped trip must start and end with a timed call (GTFS requires times on the
        # first and last stop time), so untimed calls before the first / after the last
        # timed inside call are dropped and only timed calls count towards the minimum.
        calls: dict[str, list[int]] = {}
        with source.table("stop_times.txt") as t:
            c_trip, c_stop, c_seq = t.col("trip_id"), t.col("stop_id"), t.col("stop_sequence")
            c_arr, c_dep = t.col("arrival_time"), t.col("departure_time")
            for _number, row in t.rows:
                trip_id = row[c_trip].strip()
                if trip_id not in candidate_trips or row[c_stop].strip() not in in_area:
                    continue
                if not (row[c_arr].strip() or row[c_dep].strip()):
                    continue
                seq = _int(row[c_seq].strip())
                if seq is None:
                    continue
                entry = calls.get(trip_id)
                if entry is None:
                    calls[trip_id] = [1, seq, seq]
                else:
                    entry[0] += 1
                    entry[1] = min(entry[1], seq)
                    entry[2] = max(entry[2], seq)
        kept_range = {
            trip: (low, high)
            for trip, (count, low, high) in calls.items()
            if count >= MIN_STOPS_IN_AREA
        }
        kept_trips = set(kept_range)
        stats.trips_outside_area = len(candidate_trips) - len(kept_trips)
        if not kept_trips:
            raise AreaFilterError(
                f"no trip has at least {MIN_STOPS_IN_AREA} timed calls inside bbox"
                f" {list(area.bbox)}"
            )

        # Shape of every kept trip (needed for the distance ranges below).
        trip_shape: dict[str, str] = {}
        with source.table("trips.txt") as t:
            c_trip, c_shape = t.col("trip_id"), t.col("shape_id")
            for _number, row in t.rows:
                trip_id = row[c_trip].strip()
                if trip_id in kept_trips and row[c_shape].strip():
                    trip_shape[trip_id] = row[c_shape].strip()

        target_path = Path(target_path)
        with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            out = _Writer(archive, stats)

            # ------------------------------------- stop_times pass 2: write the calls
            used_stops: set[str] = set()
            # shape_id -> [min, max] distance of kept calls, or None (keep the shape whole).
            shape_ranges: dict[str, list[float] | None] = {}
            with source.table("stop_times.txt") as t:
                c_trip, c_stop = t.col("trip_id"), t.col("stop_id")
                c_seq, c_dist = t.col("stop_sequence"), t.col("shape_dist_traveled")

                def stop_time_rows():
                    for row in _counted(stats, "stop_times.txt", t.rows):
                        trip_id = row[c_trip].strip()
                        limits = kept_range.get(trip_id)
                        if limits is None:
                            continue
                        stop_id = row[c_stop].strip()
                        if stop_id not in in_area:
                            continue
                        seq = _int(row[c_seq].strip())
                        if seq is None or not limits[0] <= seq <= limits[1]:
                            continue
                        used_stops.add(stop_id)
                        shape_id = trip_shape.get(trip_id)
                        if shape_id is not None:
                            dist = _float(row[c_dist]) if row[c_dist] else None
                            current = shape_ranges.get(shape_id, [math.inf, -math.inf])
                            if dist is None or current is None:
                                shape_ranges[shape_id] = None
                            else:
                                current[0] = min(current[0], dist)
                                current[1] = max(current[1], dist)
                                shape_ranges[shape_id] = current
                        yield row

                out.write("stop_times.txt", _header(t), stop_time_rows())

            # ---------------------------------------------------------------- trips
            used_routes: set[str] = set()
            used_services: set[str] = set()
            with source.table("trips.txt") as t:
                c_trip, c_route = t.col("trip_id"), t.col("route_id")
                c_service = t.col("service_id")

                def trip_rows():
                    for row in _counted(stats, "trips.txt", t.rows):
                        if row[c_trip].strip() in kept_trips:
                            used_routes.add(row[c_route].strip())
                            used_services.add(row[c_service].strip())
                            yield row

                out.write("trips.txt", _header(t), trip_rows())

            # ------------------------------------------------------- routes, agency
            used_agencies: set[str] = set()
            with source.table("routes.txt") as t:
                c_route, c_agency = t.col("route_id"), t.col("agency_id")

                def route_rows():
                    for row in _counted(stats, "routes.txt", t.rows):
                        if row[c_route].strip() in used_routes:
                            used_agencies.add(row[c_agency].strip())
                            yield row

                out.write("routes.txt", _header(t), route_rows())

            if source.has("agency.txt"):
                with source.table("agency.txt") as t:
                    agency_rows = sum(1 for _row in t.rows)
                with source.table("agency.txt") as t:
                    c_agency = t.col("agency_id")
                    # A blank routes.agency_id means "the only agency": keep them all then.
                    keep_all = not t.has("agency_id") or agency_rows == 1 or "" in used_agencies
                    out.write(
                        "agency.txt",
                        _header(t),
                        (
                            row
                            for row in _counted(stats, "agency.txt", t.rows)
                            if keep_all or row[c_agency].strip() in used_agencies
                        ),
                    )

            # ---------------------------------------------------------------- stops
            wanted_stops = set(used_stops)
            for stop_id in used_stops:
                parent = parents.get(stop_id)
                while parent and parent not in wanted_stops:
                    wanted_stops.add(parent)
                    parent = parents.get(parent)
            with source.table("stops.txt") as t:
                c_id = t.col("stop_id")
                out.write(
                    "stops.txt",
                    _header(t),
                    (
                        row
                        for row in _counted(stats, "stops.txt", t.rows)
                        if row[c_id].strip() in wanted_stops
                    ),
                )

            # ------------------------------------------------------------- services
            for name in ("calendar.txt", "calendar_dates.txt"):
                if not source.has(name):
                    continue
                with source.table(name) as t:
                    c_service = t.col("service_id")
                    out.write(
                        name,
                        _header(t),
                        (
                            row
                            for row in _counted(stats, name, t.rows)
                            if row[c_service].strip() in used_services
                        ),
                    )

            if source.has("frequencies.txt"):
                with source.table("frequencies.txt") as t:
                    c_trip = t.col("trip_id")
                    out.write(
                        "frequencies.txt",
                        _header(t),
                        (
                            row
                            for row in _counted(stats, "frequencies.txt", t.rows)
                            if row[c_trip].strip() in kept_trips
                        ),
                    )

            if source.has("shapes.txt"):
                _write_shapes(source, out, stats, set(trip_shape.values()), shape_ranges)

            if source.has("transfers.txt"):
                with source.table("transfers.txt") as t:
                    c_from, c_to = t.col("from_stop_id"), t.col("to_stop_id")
                    c_from_trip, c_to_trip = t.col("from_trip_id"), t.col("to_trip_id")

                    def transfer_rows():
                        for row in _counted(stats, "transfers.txt", t.rows):
                            stops_ok = all(
                                not row[c].strip() or row[c].strip() in wanted_stops
                                for c in (c_from, c_to)
                            )
                            trips_ok = all(
                                not row[c].strip() or row[c].strip() in kept_trips
                                for c in (c_from_trip, c_to_trip)
                            )
                            if stops_ok and trips_ok:
                                yield row

                    out.write("transfers.txt", _header(t), transfer_rows())

            for name in COPIED_FILES:
                if source.has(name):
                    with source.table(name) as t:
                        out.write(name, _header(t), _counted(stats, name, t.rows))

            handled = {
                "agency.txt",
                "stops.txt",
                "routes.txt",
                "trips.txt",
                "stop_times.txt",
                "calendar.txt",
                "calendar_dates.txt",
                "frequencies.txt",
                "shapes.txt",
                "transfers.txt",
                *COPIED_FILES,
            }
            stats.dropped_files = sorted(source.names() - handled)
    return stats


def _write_shapes(
    source: GtfsSource,
    out: _Writer,
    stats: FilterStats,
    used_shapes: set[str],
    ranges: dict[str, list[float] | None],
) -> None:
    """Write used shapes, each clipped to its distance range plus one point either side."""
    clip = {shape: r for shape, r in ranges.items() if r is not None and r[0] <= r[1]}
    # Pass 1: per clipped shape, the sequence numbers of the nearest point before the
    # range and after it, so the drawn line reaches the first and last kept stop.
    before: dict[str, tuple[float, int]] = {}
    after: dict[str, tuple[float, int]] = {}
    unclippable: set[str] = set()
    with source.table("shapes.txt") as t:
        c_shape, c_seq = t.col("shape_id"), t.col("shape_pt_sequence")
        c_dist = t.col("shape_dist_traveled")
        for _number, row in t.rows:
            shape_id = row[c_shape].strip()
            if shape_id not in clip:
                continue
            dist, seq = _float(row[c_dist]) if row[c_dist] else None, _int(row[c_seq])
            if dist is None or seq is None:
                unclippable.add(shape_id)
                continue
            low, high = clip[shape_id]
            if dist < low and (shape_id not in before or dist > before[shape_id][0]):
                before[shape_id] = (dist, seq)
            elif dist > high and (shape_id not in after or dist < after[shape_id][0]):
                after[shape_id] = (dist, seq)
    for shape_id in unclippable:
        clip.pop(shape_id, None)
    stats.shapes_clipped = len(clip)
    edges = {(shape, seq) for shape, (_d, seq) in before.items()} | {
        (shape, seq) for shape, (_d, seq) in after.items()
    }

    with source.table("shapes.txt") as t:
        c_shape, c_seq = t.col("shape_id"), t.col("shape_pt_sequence")
        c_dist = t.col("shape_dist_traveled")

        def shape_rows():
            for row in _counted(stats, "shapes.txt", t.rows):
                shape_id = row[c_shape].strip()
                if shape_id not in used_shapes:
                    continue
                limits = clip.get(shape_id)
                if limits is not None:
                    dist = _float(row[c_dist])
                    if not (limits[0] <= dist <= limits[1]) and (
                        (shape_id, _int(row[c_seq])) not in edges
                    ):
                        continue
                yield row

        out.write("shapes.txt", _header(t), shape_rows())


def _int(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        return None
