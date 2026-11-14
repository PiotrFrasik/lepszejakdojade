"""Read GTFS tables from a zip file or a directory, one row at a time (no pandas).

Rows are lists of strings. ``Table.col(name)`` gives the index of a column; a column
missing from the file maps to an extra, always empty, cell appended to every row, so
callers never need to check whether an optional column exists.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO

# Files and columns the importer cannot work without (GTFS "required" / "conditionally
# required" in the form this importer needs). calendar.txt and calendar_dates.txt are
# each optional, but at least one of them must be present.
REQUIRED_FILES = ("agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt")
CALENDAR_FILES = ("calendar.txt", "calendar_dates.txt")

REQUIRED_COLUMNS = {
    "agency.txt": ("agency_name",),
    "stops.txt": ("stop_id",),
    "routes.txt": ("route_id", "route_type"),
    "trips.txt": ("route_id", "service_id", "trip_id"),
    "stop_times.txt": ("trip_id", "stop_id", "stop_sequence"),
    "calendar.txt": (
        "service_id",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "start_date",
        "end_date",
    ),
    "calendar_dates.txt": ("service_id", "date", "exception_type"),
    "shapes.txt": ("shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"),
    "frequencies.txt": ("trip_id", "start_time", "end_time", "headway_secs"),
    "feed_info.txt": (),
}

# Files the importer reads. Anything else in the archive is listed as ignored.
KNOWN_FILES = frozenset(REQUIRED_COLUMNS)


class GtfsFormatError(Exception):
    """The archive is not a usable GTFS feed (missing files or columns, bad zip)."""


@dataclass
class Table:
    name: str
    columns: dict[str, int]
    rows: Iterator[tuple[int, list[str]]]  # (row number starting at 1, cells)

    @property
    def width(self) -> int:
        return len(self.columns)

    def col(self, name: str) -> int:
        """Index of a column; a missing column maps to the always-empty extra cell."""
        return self.columns.get(name, self.width)

    def has(self, name: str) -> bool:
        return name in self.columns


class GtfsSource:
    """A GTFS feed as a zip file or as a directory of .txt files.

    Members are matched by base name, so feeds packed inside a top-level folder work.
    """

    def __init__(self, path: Path, max_uncompressed_bytes: int | None = None):
        self.path = Path(path)
        self._zip: zipfile.ZipFile | None = None
        self._members: dict[str, str] = {}
        if self.path.is_dir():
            for child in sorted(self.path.iterdir()):
                if child.is_file():
                    self._members[child.name.lower()] = child.name
            return
        try:
            self._zip = zipfile.ZipFile(self.path)
        except (zipfile.BadZipFile, OSError) as exc:
            raise GtfsFormatError(f"not a valid zip file: {exc}") from exc
        total = 0
        for info in self._zip.infolist():
            if info.is_dir() or info.filename.startswith("__MACOSX/"):
                continue
            total += info.file_size
            base = info.filename.rsplit("/", 1)[-1].lower()
            # Prefer the shallowest member when a name occurs twice.
            current = self._members.get(base)
            if current is None or current.count("/") > info.filename.count("/"):
                self._members[base] = info.filename
        if max_uncompressed_bytes is not None and total > max_uncompressed_bytes:
            raise GtfsFormatError(
                f"uncompressed size {total} bytes exceeds the limit of {max_uncompressed_bytes}"
            )

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()

    def __enter__(self) -> GtfsSource:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def names(self) -> set[str]:
        return set(self._members)

    def has(self, name: str) -> bool:
        return name in self._members

    def ignored_files(self) -> list[str]:
        return sorted(name for name in self._members if name not in KNOWN_FILES)

    def _open_binary(self, name: str) -> IO[bytes]:
        member = self._members[name]
        if self._zip is not None:
            return self._zip.open(member)
        return open(self.path / member, "rb")  # noqa: SIM115 - closed by the caller

    @contextmanager
    def table(self, name: str) -> Iterator[Table]:
        """Open one file as a Table. The header is read eagerly, rows lazily."""
        with self._open_binary(name) as raw:
            # utf-8-sig drops a BOM; undecodable bytes become U+FFFD instead of failing.
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
            reader = csv.reader(_strip_nul(text))
            header = next(reader, None) or []
            columns = {}
            for index, column in enumerate(header):
                columns.setdefault(column.strip().lower(), index)
            width = len(header)
            yield Table(name=name, columns=columns, rows=_rows(reader, width))

    def header(self, name: str) -> list[str]:
        with self.table(name) as table:
            return list(table.columns)


def _strip_nul(lines):
    # PostgreSQL text cannot hold NUL characters; drop them before parsing.
    for line in lines:
        yield line.replace("\x00", "") if "\x00" in line else line


def _rows(reader, width: int) -> Iterator[tuple[int, list[str]]]:
    target = width + 1
    for number, row in enumerate(reader, start=1):
        if not row:
            continue  # blank line
        missing = target - len(row)
        if missing > 0:
            row.extend([""] * missing)
        elif missing < 0:
            # More cells than header columns: the extra cells are ignored, but the
            # always-empty cell at index ``width`` must stay empty.
            del row[target:]
            row[width] = ""
        yield number, row


def validate_structure(source: GtfsSource) -> None:
    """Check required files and columns. Raises GtfsFormatError listing every problem."""
    problems = []
    for name in REQUIRED_FILES:
        if not source.has(name):
            problems.append(f"missing {name}")
    if not any(source.has(name) for name in CALENDAR_FILES):
        problems.append("missing both calendar.txt and calendar_dates.txt")
    for name, required in REQUIRED_COLUMNS.items():
        if not source.has(name) or not required:
            continue
        header = source.header(name)
        missing = [column for column in required if column not in header]
        if missing:
            problems.append(f"{name}: missing columns {', '.join(missing)}")
    if problems:
        raise GtfsFormatError("; ".join(problems))
