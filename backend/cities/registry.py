"""City configuration loader and registry.

Each city is one YAML file in ``settings.CITY_CONFIG_DIR`` named ``<id>.yaml``.
Adding a city means adding a file; no code changes. Files are validated strictly
(unknown keys are rejected) and any problem raises ``CityConfigError`` with the
file name and the path of the offending field. The parsed registry is cached
until ``clear_cache()`` is called or ``CITY_CONFIG_DIR`` changes.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed
from django.dispatch import receiver
from django.utils import translation

VEHICLE_TYPES = ("tram", "bus", "metro", "rail")
GTFS_RT_ENTITIES = ("vehicle_positions", "trip_updates", "service_alerts")

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_COLOUR_RE = re.compile(r"^#[0-9a-f]{6}$")
_URL_RE = re.compile(r"^https?://\S+$")
_HTTPS_URL_RE = re.compile(r"^https://\S+$")


class CityConfigError(ImproperlyConfigured):
    """A city configuration file is missing, unreadable or invalid."""


# --------------------------------------------------------------------------- data


@dataclass(frozen=True)
class Translated:
    """A text with one value per language in ``settings.LANGUAGES``."""

    values: dict[str, str]

    def get(self, language: str | None = None) -> str:
        code = (language or translation.get_language() or settings.LANGUAGE_CODE).lower()
        for candidate in (code, code.split("-")[0], settings.LANGUAGE_CODE):
            if candidate in self.values:
                return self.values[candidate]
        return next(iter(self.values.values()))


@dataclass(frozen=True)
class MapView:
    lat: float
    lon: float
    zoom: int


@dataclass(frozen=True)
class LineGroup:
    id: str
    names: Translated
    colour: str


@dataclass(frozen=True)
class Realtime:
    departures: bool
    vehicles: bool


@dataclass(frozen=True)
class Feed:
    id: str
    url: str | None
    kind: str  # "gtfs_static", "gtfs_rt" or a free-form kind for other sources
    entity: str | None = None  # GTFS-RT entity type, only for kind "gtfs_rt"


@dataclass(frozen=True)
class TicketZone:
    id: str
    names: Translated


@dataclass(frozen=True)
class Attribution:
    name: str
    url: str
    licence: str | None
    licence_url: str | None = None  # link to the licence or terms of use


@dataclass(frozen=True)
class OtpConfig:
    """OpenTripPlanner graph build settings (internal)."""

    osm_url: str  # OpenStreetMap extract (.osm.pbf)
    bbox: tuple[float, float, float, float] | None  # (min_lon, min_lat, max_lon, max_lat)


@dataclass(frozen=True)
class City:
    id: str
    names: Translated
    timezone: str
    map: MapView
    vehicle_types: tuple[str, ...]
    line_groups: tuple[LineGroup, ...]
    realtime: Realtime
    # Internal: never exposed by the public API.
    feeds: tuple[Feed, ...]
    ticket_zones: tuple[TicketZone, ...]
    attributions: tuple[Attribution, ...]
    otp: OtpConfig | None = None  # None when the city has no `otp` section

    @property
    def name(self) -> str:
        """Name in the active language."""
        return self.names.get()

    @property
    def zoneinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


# --------------------------------------------------------------------- validation


class _Validator:
    """Helpers that check one value and raise CityConfigError with the field path."""

    def __init__(self, source: str):
        self.source = source

    def fail(self, path: str, message: str) -> NoReturn:
        raise CityConfigError(f"Invalid city config {self.source}: {path}: {message}")

    def mapping(self, value: Any, path: str, required: set[str], optional: set[str] = frozenset()):
        if not isinstance(value, dict):
            self.fail(path, "expected a mapping")
        keys = set(value)
        missing = required - keys
        if missing:
            self.fail(path, f"missing keys: {', '.join(sorted(missing))}")
        unknown = keys - required - optional
        if unknown:
            self.fail(path, f"unknown keys: {', '.join(sorted(map(str, unknown)))}")
        return value

    def sequence(self, value: Any, path: str, allow_empty: bool = True) -> list:
        if not isinstance(value, list):
            self.fail(path, "expected a list")
        if not allow_empty and not value:
            self.fail(path, "must not be empty")
        return value

    def text(self, value: Any, path: str) -> str:
        if not isinstance(value, str) or not value.strip():
            self.fail(path, "expected a non-empty string")
        return value

    def identifier(self, value: Any, path: str) -> str:
        if not isinstance(value, str) or not _ID_RE.match(value):
            self.fail(path, "expected an id of lowercase letters, digits, '-' or '_'")
        return value

    def boolean(self, value: Any, path: str) -> bool:
        if not isinstance(value, bool):
            self.fail(path, "expected true or false")
        return value

    def number(self, value: Any, path: str, low: float, high: float) -> float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            self.fail(path, "expected a number")
        if not low <= value <= high:
            self.fail(path, f"must be between {low} and {high}")
        return float(value)

    def integer(self, value: Any, path: str, low: int, high: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            self.fail(path, "expected an integer")
        if not low <= value <= high:
            self.fail(path, f"must be between {low} and {high}")
        return value

    def url(self, value: Any, path: str, nullable: bool = False) -> str | None:
        if value is None and nullable:
            return None
        if not isinstance(value, str) or not _URL_RE.match(value):
            self.fail(path, "expected an http(s) URL" + (" or null" if nullable else ""))
        return value

    def translated(self, value: Any, path: str) -> Translated:
        languages = {code for code, _name in settings.LANGUAGES}
        self.mapping(value, path, required=languages)
        return Translated({code: self.text(value[code], f"{path}.{code}") for code in value})

    def unique_ids(self, items: list, path: str) -> None:
        ids = [item.id for item in items]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            self.fail(path, f"duplicate ids: {', '.join(duplicates)}")


_TOP_LEVEL_KEYS = {
    "id",
    "names",
    "timezone",
    "map",
    "vehicle_types",
    "line_groups",
    "realtime",
    "feeds",
    "ticket_zones",
    "attributions",
}
_OPTIONAL_TOP_LEVEL_KEYS = {"otp"}


def parse_city(data: Any, source: str, expected_id: str | None = None) -> City:
    """Validate raw config data and build a City. Raises CityConfigError."""
    v = _Validator(source)
    v.mapping(data, "<root>", required=_TOP_LEVEL_KEYS, optional=_OPTIONAL_TOP_LEVEL_KEYS)

    city_id = v.identifier(data["id"], "id")
    if expected_id is not None and city_id != expected_id:
        v.fail("id", f"must match the file name ({expected_id!r})")

    timezone = v.text(data["timezone"], "timezone")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        v.fail("timezone", f"unknown time zone {timezone!r}")

    v.mapping(data["map"], "map", required={"center", "zoom"})
    v.mapping(data["map"]["center"], "map.center", required={"lat", "lon"})
    map_view = MapView(
        lat=v.number(data["map"]["center"]["lat"], "map.center.lat", -90, 90),
        lon=v.number(data["map"]["center"]["lon"], "map.center.lon", -180, 180),
        zoom=v.integer(data["map"]["zoom"], "map.zoom", 0, 22),
    )

    vehicle_types = v.sequence(data["vehicle_types"], "vehicle_types", allow_empty=False)
    for i, vehicle_type in enumerate(vehicle_types):
        if vehicle_type not in VEHICLE_TYPES:
            v.fail(f"vehicle_types[{i}]", f"must be one of {', '.join(VEHICLE_TYPES)}")
    if len(set(vehicle_types)) != len(vehicle_types):
        v.fail("vehicle_types", "duplicate values")

    line_groups = []
    for i, raw in enumerate(v.sequence(data["line_groups"], "line_groups", allow_empty=False)):
        path = f"line_groups[{i}]"
        v.mapping(raw, path, required={"id", "names", "colour"})
        colour = raw["colour"]
        if not isinstance(colour, str) or not _COLOUR_RE.match(colour):
            v.fail(f"{path}.colour", "expected a lowercase #rrggbb colour")
        line_groups.append(
            LineGroup(
                id=v.identifier(raw["id"], f"{path}.id"),
                names=v.translated(raw["names"], f"{path}.names"),
                colour=colour,
            )
        )
    v.unique_ids(line_groups, "line_groups")

    v.mapping(data["realtime"], "realtime", required={"departures", "vehicles"})
    realtime = Realtime(
        departures=v.boolean(data["realtime"]["departures"], "realtime.departures"),
        vehicles=v.boolean(data["realtime"]["vehicles"], "realtime.vehicles"),
    )

    feeds = _parse_feeds(v, data["feeds"])

    ticket_zones = []
    for i, raw in enumerate(v.sequence(data["ticket_zones"], "ticket_zones")):
        path = f"ticket_zones[{i}]"
        v.mapping(raw, path, required={"id", "names"})
        ticket_zones.append(
            TicketZone(
                id=v.identifier(raw["id"], f"{path}.id"),
                names=v.translated(raw["names"], f"{path}.names"),
            )
        )
    v.unique_ids(ticket_zones, "ticket_zones")

    attributions = []
    for i, raw in enumerate(v.sequence(data["attributions"], "attributions", allow_empty=False)):
        path = f"attributions[{i}]"
        v.mapping(raw, path, required={"name", "url", "licence"}, optional={"licence_url"})
        licence = raw["licence"]
        if licence is not None:
            v.text(licence, f"{path}.licence")
        attributions.append(
            Attribution(
                name=v.text(raw["name"], f"{path}.name"),
                url=v.url(raw["url"], f"{path}.url"),
                licence=licence,
                licence_url=v.url(raw.get("licence_url"), f"{path}.licence_url", nullable=True),
            )
        )

    return City(
        id=city_id,
        names=v.translated(data["names"], "names"),
        timezone=timezone,
        map=map_view,
        vehicle_types=tuple(vehicle_types),
        line_groups=tuple(line_groups),
        realtime=realtime,
        feeds=tuple(feeds),
        ticket_zones=tuple(ticket_zones),
        attributions=tuple(attributions),
        otp=_parse_otp(v, data["otp"]) if "otp" in data else None,
    )


def _parse_otp(v: _Validator, raw: Any) -> OtpConfig:
    v.mapping(raw, "otp", required={"osm_url"}, optional={"bbox"})
    osm_url = raw["osm_url"]
    if not isinstance(osm_url, str) or not _HTTPS_URL_RE.match(osm_url):
        v.fail("otp.osm_url", "expected an https URL")

    bbox = None
    if raw.get("bbox") is not None:
        values = v.sequence(raw["bbox"], "otp.bbox")
        if len(values) != 4:
            v.fail("otp.bbox", "expected [min_lon, min_lat, max_lon, max_lat]")
        min_lon = v.number(values[0], "otp.bbox[0]", -180, 180)
        min_lat = v.number(values[1], "otp.bbox[1]", -90, 90)
        max_lon = v.number(values[2], "otp.bbox[2]", -180, 180)
        max_lat = v.number(values[3], "otp.bbox[3]", -90, 90)
        if min_lon >= max_lon:
            v.fail("otp.bbox", "min_lon must be less than max_lon")
        if min_lat >= max_lat:
            v.fail("otp.bbox", "min_lat must be less than max_lat")
        bbox = (min_lon, min_lat, max_lon, max_lat)

    return OtpConfig(osm_url=osm_url, bbox=bbox)


def _parse_feeds(v: _Validator, raw: Any) -> list[Feed]:
    v.mapping(raw, "feeds", required={"gtfs_static", "gtfs_rt", "other"})
    feeds: list[Feed] = []
    for i, item in enumerate(v.sequence(raw["gtfs_static"], "feeds.gtfs_static")):
        path = f"feeds.gtfs_static[{i}]"
        v.mapping(item, path, required={"id", "url"})
        feeds.append(
            Feed(
                id=v.identifier(item["id"], f"{path}.id"),
                url=v.url(item["url"], f"{path}.url", nullable=True),
                kind="gtfs_static",
            )
        )
    for i, item in enumerate(v.sequence(raw["gtfs_rt"], "feeds.gtfs_rt")):
        path = f"feeds.gtfs_rt[{i}]"
        v.mapping(item, path, required={"id", "entity", "url"})
        if item["entity"] not in GTFS_RT_ENTITIES:
            v.fail(f"{path}.entity", f"must be one of {', '.join(GTFS_RT_ENTITIES)}")
        feeds.append(
            Feed(
                id=v.identifier(item["id"], f"{path}.id"),
                url=v.url(item["url"], f"{path}.url", nullable=True),
                kind="gtfs_rt",
                entity=item["entity"],
            )
        )
    for i, item in enumerate(v.sequence(raw["other"], "feeds.other")):
        path = f"feeds.other[{i}]"
        v.mapping(item, path, required={"id", "kind", "url"})
        feeds.append(
            Feed(
                id=v.identifier(item["id"], f"{path}.id"),
                url=v.url(item["url"], f"{path}.url", nullable=True),
                kind=v.identifier(item["kind"], f"{path}.kind"),
            )
        )
    v.unique_ids(feeds, "feeds")
    return feeds


def load_city_file(path: Path) -> City:
    source = path.name
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CityConfigError(f"Cannot read city config {source}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise CityConfigError(f"Invalid YAML in city config {source}: {exc}") from exc
    return parse_city(data, source, expected_id=path.stem)


def load_cities(config_dir: Path) -> dict[str, City]:
    """Load every ``*.yaml`` file in ``config_dir``, ordered by city id."""
    config_dir = Path(config_dir)
    if not config_dir.is_dir():
        raise CityConfigError(f"City config directory does not exist: {config_dir}")
    paths = sorted(config_dir.glob("*.yaml"))
    if not paths:
        raise CityConfigError(f"No city config files (*.yaml) in {config_dir}")
    cities = [load_city_file(path) for path in paths]
    return {city.id: city for city in sorted(cities, key=lambda c: c.id)}


# ----------------------------------------------------------------------- registry

_lock = threading.Lock()
_cache: dict[str, City] | None = None


def _registry() -> dict[str, City]:
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                _cache = load_cities(settings.CITY_CONFIG_DIR)
    return _cache


def clear_cache() -> None:
    global _cache
    with _lock:
        _cache = None


def all_cities() -> list[City]:
    """All configured cities, ordered by id."""
    return list(_registry().values())


def get_city(city_id: str) -> City | None:
    return _registry().get(city_id)


def get_otp_url(city_id: str) -> str | None:
    """Base URL of the city's OpenTripPlanner instance, or None if it is not configured.

    Read from the environment variable ``OTP_URL_<CITY_ID>``: the city id upper-cased, with
    ``-`` replaced by ``_`` (e.g. ``OTP_URL_KRAKOW``). Unset or blank means None.
    """
    name = "OTP_URL_" + city_id.upper().replace("-", "_")
    return os.environ.get(name, "").strip() or None


@receiver(setting_changed)
def _reset_on_setting_change(setting, **kwargs):
    if setting in {"CITY_CONFIG_DIR", "LANGUAGES"}:
        clear_cache()
