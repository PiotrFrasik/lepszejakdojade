"""Lines (GTFS routes) of a city: ids, line groups, colours, ordering."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from cities.registry import City, LineGroup
from transit_data.models import FeedVersion, Route, Stop, Trip, vehicle_type_for_route_type

ID_SEPARATOR = ":"

_ROUTE_FIELDS = (
    "id",
    "feed_version_id",
    "gtfs_id",
    "short_name",
    "long_name",
    "route_type",
    "color",
    "text_color",
)
# GTFS route colours treated as "not set": some feeds (e.g. ZTP Kraków buses) give every
# route plain white or black, which would hide the line group colours.
_UNSET_ROUTE_COLOURS = frozenset({"FFFFFF", "000000"})
_NATURAL_RE = re.compile(r"\d+|\D+")
# Separators are ignored when sorting ("L-1" sorts like "L1", before "L10").
_SEPARATORS_RE = re.compile(r"[\s\-_./]+")


def make_id(feed_id: str, gtfs_id: str) -> str:
    return f"{feed_id}{ID_SEPARATOR}{gtfs_id}"


def parse_id(value: str) -> tuple[str, str] | None:
    """Split a public id ``{feed_id}:{gtfs_id}``; None when malformed."""
    feed_id, separator, gtfs_id = value.partition(ID_SEPARATOR)
    if not separator or not feed_id or not gtfs_id:
        return None
    return feed_id, gtfs_id


class Feeds:
    """Active static feed versions of one city (only feeds listed in its config)."""

    def __init__(self, city: City):
        self.city = city
        configured = {feed.id for feed in city.feeds if feed.kind == "gtfs_static"}
        rows = FeedVersion.objects.filter(
            city_id=city.id, status=FeedVersion.Status.ACTIVE, feed_id__in=configured
        ).values_list("id", "feed_id")
        self.feed_by_version: dict[int, str] = dict(rows)
        self.version_by_feed: dict[str, int] = {f: v for v, f in self.feed_by_version.items()}

    @property
    def version_ids(self) -> list[int]:
        return list(self.feed_by_version)

    def resolve(self, public_id: str) -> tuple[int, str, str] | None:
        """``(feed_version_id, feed_id, gtfs_id)`` of a public id, or None."""
        parsed = parse_id(public_id)
        if parsed is None or parsed[0] not in self.version_by_feed:
            return None
        return self.version_by_feed[parsed[0]], parsed[0], parsed[1]


def readable_text_colour(colour: str) -> str:
    """``#ffffff`` or ``#000000``, whichever reads better on ``colour`` (``#rrggbb``)."""
    channels = []
    for i in (1, 3, 5):
        value = int(colour[i : i + 2], 16) / 255
        channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    return "#000000" if luminance > 0.179 else "#ffffff"


def natural_key(text: str) -> tuple:
    """Sort key where digit runs compare as numbers, numbers sort before letters and
    separators are ignored."""
    return tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part.casefold())
        for part in _NATURAL_RE.findall(_SEPARATORS_RE.sub("", text))
    )


@dataclass(frozen=True)
class Line:
    pk: int
    feed_version_id: int
    feed_id: str
    gtfs_id: str
    short_name: str
    long_name: str
    vehicle_type: str
    group: LineGroup
    group_index: int
    colour: str
    text_colour: str

    @property
    def id(self) -> str:
        return make_id(self.feed_id, self.gtfs_id)

    @property
    def sort_key(self) -> tuple:
        return (self.group_index, natural_key(self.short_name), self.id)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "short_name": self.short_name,
            "vehicle_type": self.vehicle_type,
            "group": self.group.id,
            "colour": self.colour,
            "text_colour": self.text_colour,
        }

    def list_item(self) -> dict:
        return {**self.summary(), "long_name": self.long_name, "notice": None}


def _line_from_row(city: City, feeds: Feeds, row: dict) -> Line | None:
    """A Line from Route values, or None for vehicle types the city does not show."""
    vehicle_type = str(vehicle_type_for_route_type(row["route_type"]))
    if vehicle_type not in city.vehicle_types:
        return None
    feed_id = feeds.feed_by_version[row["feed_version_id"]]
    short_name = row["short_name"] or row["long_name"] or row["gtfs_id"]
    group = city.line_group_for(vehicle_type, feed_id, short_name)
    if row["color"] and row["color"].upper() not in _UNSET_ROUTE_COLOURS:
        colour = f"#{row['color'].lower()}"
        text_colour = (
            f"#{row['text_color'].lower()}" if row["text_color"] else readable_text_colour(colour)
        )
    else:
        colour = group.colour
        text_colour = readable_text_colour(colour)
    return Line(
        pk=row["id"],
        feed_version_id=row["feed_version_id"],
        feed_id=feed_id,
        gtfs_id=row["gtfs_id"],
        short_name=short_name,
        long_name=row["long_name"],
        vehicle_type=vehicle_type,
        group=group,
        group_index=city.line_groups.index(group),
        colour=colour,
        text_colour=text_colour,
    )


def _lines(city: City, feeds: Feeds, rows: Iterable[dict]) -> list[Line]:
    lines = [line for row in rows if (line := _line_from_row(city, feeds, row)) is not None]
    return sorted(lines, key=lambda line: line.sort_key)


def list_lines(city: City, feeds: Feeds, vehicle_type: str | None = None) -> list[Line]:
    """All lines of the city, sorted by group order and natural short name."""
    rows = Route.objects.filter(feed_version_id__in=feeds.version_ids).values(*_ROUTE_FIELDS)
    lines = _lines(city, feeds, rows)
    if vehicle_type:
        lines = [line for line in lines if line.vehicle_type == vehicle_type]
    return lines


def lines_by_pk(city: City, feeds: Feeds, pks: Iterable[int]) -> dict[int, Line]:
    rows = Route.objects.filter(pk__in=list(pks), feed_version_id__in=feeds.version_ids).values(
        *_ROUTE_FIELDS
    )
    return {line.pk: line for line in _lines(city, feeds, rows)}


def get_line(city: City, feeds: Feeds, line_id: str) -> Line | None:
    resolved = feeds.resolve(line_id)
    if resolved is None:
        return None
    version_id, _feed_id, gtfs_id = resolved
    row = (
        Route.objects.filter(feed_version_id=version_id, gtfs_id=gtfs_id)
        .values(*_ROUTE_FIELDS)
        .first()
    )
    return None if row is None else _line_from_row(city, feeds, row)


def get_stop(feeds: Feeds, line: Line, stop_id: str) -> Stop | None:
    """A stop of the line's feed version by public id."""
    resolved = feeds.resolve(stop_id)
    if resolved is None or resolved[0] != line.feed_version_id:
        return None
    return Stop.objects.filter(feed_version_id=resolved[0], gtfs_id=resolved[2]).first()


def get_trip(feeds: Feeds, trip_id: str) -> Trip | None:
    resolved = feeds.resolve(trip_id)
    if resolved is None:
        return None
    return Trip.objects.filter(feed_version_id=resolved[0], gtfs_id=resolved[2]).first()
