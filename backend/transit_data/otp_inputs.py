"""Assemble a ready-to-build OpenTripPlanner 2 input directory for one city.

OTP 2 serves one graph per instance, so every city gets its own directory
``<OTP_DATA_DIR>/<city>/``. ``prepare_city()`` fills it with:

- ``build-config.json``, ``router-config.json``, ``otp-config.json``: the shared defaults
  from ``<OTP_CONFIG_DIR>/config/``, deep-merged with optional per-city overrides from
  ``<OTP_CONFIG_DIR>/<city>/``, plus the city-specific parts generated from city config
  (feed list, OSM file, time zone);
- ``<feed id>.gtfs.zip`` for every static GTFS feed with a URL (feeds with ``url: null``
  are skipped); a feed with a ``filter`` in city config is downloaded to
  ``cache/<feed id>.source.gtfs.zip`` and cut down to the city's area first
  (``static_gtfs.area_filter``, the same filter as the database import);
- ``<city>.osm.pbf``: the regional OSM extract (``city.otp.osm_url``) clipped with
  osmium-tool to the area served by the feeds (bbox of all GTFS stops plus a buffer, or the
  ``city.otp.bbox`` override);
- ``prepare-report.json``: what was used (URLs, sha256, download times, bbox);
- ``cache/``: the unclipped regional extract and download metadata for conditional GETs.
  OTP only scans the top level of its base directory, so it never reads ``cache/``.

Downloads are conditional (ETag / Last-Modified) and atomic: a failed or invalid download
keeps the previous file, so a broken upstream never destroys a working input set.

Settings (all optional):
- ``OTP_DATA_DIR`` [<repo>/otp/data] where the per-city directories are written.
- ``OTP_CONFIG_DIR`` [<repo>/otp] the committed OTP config (``config/`` and ``<city>/``).
- ``OTP_OSMIUM_BIN`` ["osmium"] osmium-tool executable used for clipping.
- ``OTP_BBOX_BUFFER_KM`` [3] buffer around the GTFS stops bbox.
- ``OTP_OSM_MAX_BYTES`` [2 GB] upper bound for one OSM extract download.
- ``OTP_OSM_DOWNLOAD_MAX_SECONDS`` [1800] overall deadline for one OSM extract download.
  (GTFS downloads use the ``TRANSIT_GTFS_*`` limits of ``static_gtfs/download.py``.)

Only one run per city at a time: ``cache/prepare.lock`` is created exclusively and removed
when the run ends. A run killed hard (e.g. SIGKILL, container stop) can leave it behind;
the error message names the file, which can be deleted once no run is active.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import shutil
import socket
import subprocess
import zipfile
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.conf import settings

from cities.registry import City, get_city
from transit_data.static_gtfs.area_filter import (
    AreaFilter,
    AreaFilterError,
    feed_area_filter,
    filter_feed,
)
from transit_data.static_gtfs.download import DownloadError, download_feed
from transit_data.static_gtfs.reader import GtfsFormatError, GtfsSource

CONFIG_FILES = ("build-config.json", "router-config.json", "otp-config.json")
SHARED_CONFIG_SUBDIR = "config"
GTFS_SUFFIX = ".gtfs.zip"
CACHE_SUBDIR = "cache"
REGION_FILE = "region.osm.pbf"
REPORT_FILE = "prepare-report.json"
DEFAULT_BUFFER_KM = 3.0
OSMIUM_TIMEOUT_SECONDS = 1800
REQUIRED_GTFS_FILES = frozenset(
    {"agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}
)
KM_PER_DEGREE_LAT = 111.32
LOCK_FILE = "prepare.lock"
DEFAULT_OSM_MAX_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_OSM_DOWNLOAD_MAX_SECONDS = 1800
# A served area wider than this (degrees, either axis) usually means a misplaced stop.
MAX_BBOX_SPAN_DEGREES = 2.0


class PrepareError(Exception):
    """The input directory cannot be prepared (config problem or required data missing)."""


class OsmiumNotFound(PrepareError):
    """osmium-tool is not installed; ``command`` is what would have been run."""

    def __init__(self, message: str, command: list[str]):
        super().__init__(message)
        self.command = command


class InvalidDownload(ValueError):
    """A downloaded file is not what it claims to be."""


# --------------------------------------------------------------------------- paths


def otp_data_dir() -> Path:
    value = getattr(settings, "OTP_DATA_DIR", None)
    return Path(value) if value else Path(settings.BASE_DIR).parent / "otp" / "data"


def otp_config_dir() -> Path:
    value = getattr(settings, "OTP_CONFIG_DIR", None)
    return Path(value) if value else Path(settings.BASE_DIR).parent / "otp"


# ---------------------------------------------------------------------------- bbox


@dataclass(frozen=True)
class BBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    @classmethod
    def parse(cls, value: Any) -> BBox:
        """Build from a 4-sequence or a "min_lon,min_lat,max_lon,max_lat" string."""
        if isinstance(value, str):
            value = value.split(",")
        try:
            numbers = [float(v) for v in value]
        except (TypeError, ValueError) as exc:
            raise PrepareError(f"invalid bbox {value!r}: expected 4 numbers") from exc
        if len(numbers) != 4:
            raise PrepareError(f"invalid bbox {value!r}: expected 4 numbers")
        bbox = cls(*numbers)
        if not (
            -180 <= bbox.min_lon < bbox.max_lon <= 180 and -90 <= bbox.min_lat < bbox.max_lat <= 90
        ):
            raise PrepareError(
                f"invalid bbox {value!r}: expected min_lon,min_lat,max_lon,max_lat in degrees"
            )
        return bbox

    def buffered(self, km: float) -> BBox:
        """Grow by ``km`` on every side (longitude scaled at the bbox's widest latitude)."""
        widest_lat = max(abs(self.min_lat), abs(self.max_lat))
        d_lat = km / KM_PER_DEGREE_LAT
        d_lon = km / (KM_PER_DEGREE_LAT * max(math.cos(math.radians(widest_lat)), 0.01))
        return BBox(
            min_lon=max(self.min_lon - d_lon, -180.0),
            min_lat=max(self.min_lat - d_lat, -90.0),
            max_lon=min(self.max_lon + d_lon, 180.0),
            max_lat=min(self.max_lat + d_lat, 90.0),
        )

    def as_list(self) -> list[float]:
        return [round(v, 6) for v in (self.min_lon, self.min_lat, self.max_lon, self.max_lat)]

    def as_osmium(self) -> str:
        return ",".join(f"{v:.6f}" for v in self.as_list())


def gtfs_stops_bbox(zip_paths: list[Path]) -> BBox | None:
    """Bounding box of all stops with usable coordinates in the given GTFS zips."""
    lons: list[float] = []
    lats: list[float] = []
    for path in zip_paths:
        with zipfile.ZipFile(path) as archive, archive.open("stops.txt") as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))
            for row in reader:
                try:
                    lat = float(row.get("stop_lat") or "nan")
                    lon = float(row.get("stop_lon") or "nan")
                except ValueError:
                    continue
                # (0, 0) is the usual placeholder for a missing position.
                if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
                    continue
                lats.append(lat)
                lons.append(lon)
    if not lats:
        return None
    return BBox(min(lons), min(lats), max(lons), max(lats))


# ------------------------------------------------------------------- city config


@dataclass(frozen=True)
class OtpCityConfig:
    osm_url: str | None
    bbox: BBox | None


def city_otp_config(city: City) -> OtpCityConfig:
    """Read the optional ``otp`` section of city config (absent on older registries)."""
    otp = getattr(city, "otp", None)
    if otp is None:
        return OtpCityConfig(osm_url=None, bbox=None)
    raw_bbox = getattr(otp, "bbox", None)
    return OtpCityConfig(
        osm_url=getattr(otp, "osm_url", None) or None,
        bbox=BBox.parse(raw_bbox) if raw_bbox else None,
    )


def static_feeds_with_url(city: City) -> tuple[list, list[str]]:
    """(feeds to use, ids of static feeds skipped because their URL is null)."""
    feeds = [feed for feed in city.feeds if feed.kind == "gtfs_static"]
    return [f for f in feeds if f.url], [f.id for f in feeds if not f.url]


# ------------------------------------------------------------------- OTP configs


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` into a copy of ``base``; lists are replaced."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PrepareError(f"cannot read OTP config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PrepareError(f"OTP config {path} must contain a JSON object")
    return data


def build_otp_configs(
    city: City, feed_ids: list[str], osm_file: str, config_dir: Path | None = None
) -> dict[str, dict]:
    """The three OTP config documents for ``city``, keyed by file name."""
    config_dir = config_dir or otp_config_dir()
    shared_dir = config_dir / SHARED_CONFIG_SUBDIR
    if not shared_dir.is_dir():
        raise PrepareError(f"OTP shared config directory not found: {shared_dir}")
    configs: dict[str, dict] = {}
    for name in CONFIG_FILES:
        shared = shared_dir / name
        config = _read_json(shared) if shared.exists() else {}
        override = config_dir / city.id / name
        if override.exists():
            config = deep_merge(config, _read_json(override))
        configs[name] = config

    build = configs["build-config.json"]
    # City-specific parts always come from city config, never from the committed files.
    build["transitModelTimeZone"] = city.timezone
    build["osmDefaults"] = {**build.get("osmDefaults", {}), "timeZone": city.timezone}
    build["transitFeeds"] = [
        {"type": "gtfs", "feedId": feed_id, "source": f"{feed_id}{GTFS_SUFFIX}"}
        for feed_id in feed_ids
    ]
    build["osm"] = [{"source": osm_file}]
    return configs


# ---------------------------------------------------------------------- downloads


def validate_gtfs_zip(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise InvalidDownload("not a zip file")
    with zipfile.ZipFile(path) as archive:
        names = {Path(name).name for name in archive.namelist() if "/" not in name.strip("/")}
    missing = REQUIRED_GTFS_FILES - names
    if missing:
        raise InvalidDownload(f"missing GTFS files: {', '.join(sorted(missing))}")


def validate_osm_pbf(path: Path) -> None:
    with open(path, "rb") as handle:
        head = handle.read(64)
    if b"OSMHeader" not in head:
        raise InvalidDownload("not an OSM PBF file")


@dataclass
class FetchResult:
    status: str  # "downloaded", "unchanged" or "kept_previous"
    meta: dict
    error: str = ""


def fetch(
    url: str,
    target: Path,
    meta_path: Path,
    validate: Callable[[Path], None],
    force: bool = False,
    *,
    label: str = "feed",
    max_bytes: int | None = None,
    max_seconds: float | None = None,
) -> FetchResult:
    """Conditionally download ``url`` to ``target``; keep the previous file on failure.

    ``label`` names the file in error messages; ``max_bytes`` / ``max_seconds`` override
    the GTFS download limits.
    """
    meta = {}
    if target.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        if meta.get("url") != url:
            meta = {}
    part = target.with_name(target.name + ".part")
    try:
        fetched = download_feed(
            url,
            part,
            etag="" if force else meta.get("etag", ""),
            last_modified="" if force else meta.get("last_modified", ""),
            max_bytes=max_bytes,
            max_seconds=max_seconds,
            label=label,
        )
        if fetched.not_modified:
            return FetchResult("unchanged", meta)
        validate(part)
    except (DownloadError, InvalidDownload, OSError) as exc:
        part.unlink(missing_ok=True)
        if target.exists():
            return FetchResult("kept_previous", meta, error=str(exc))
        raise PrepareError(f"cannot download {label} {url}: {exc}") from exc
    os.replace(part, target)
    meta = {
        "url": url,
        "etag": fetched.etag,
        "last_modified": fetched.last_modified,
        "sha256": fetched.sha256,
        "size_bytes": fetched.size_bytes,
        "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return FetchResult("downloaded", meta)


# ------------------------------------------------------------------------ clipping


def osmium_command(osmium: str, source: Path, target: Path, bbox: BBox) -> list[str]:
    # complete_ways keeps every way that crosses the bbox edge whole, so streets at the
    # border are not cut into dangling stubs; relations are kept with the members inside.
    return [
        osmium,
        "extract",
        "--bbox",
        bbox.as_osmium(),
        "--strategy",
        "complete_ways",
        "--set-bounds",
        "--overwrite",
        "--output-format",
        "pbf",
        "--output",
        # Absolute paths: a relative name starting with "-" would be read as an option.
        str(Path(target).resolve()),
        str(Path(source).resolve()),
    ]


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if pos >= len(data) or shift > 63:
            raise ValueError("truncated varint")
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def _protobuf_fields(data: bytes):
    """Yield (field number, wire type, value) of a protobuf message (no nesting)."""
    pos = 0
    while pos < len(data):
        key, pos = _read_varint(data, pos)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _read_varint(data, pos)
        elif wire == 2:
            length, pos = _read_varint(data, pos)
            value, pos = data[pos : pos + length], pos + length
        elif wire == 1:
            value, pos = data[pos : pos + 8], pos + 8
        elif wire == 5:
            value, pos = data[pos : pos + 4], pos + 4
        else:
            raise ValueError(f"unsupported wire type {wire}")
        yield number, wire, value


def pbf_header_bbox(path: Path) -> BBox | None:
    """Bounds stored in the OSMHeader block of a PBF file, or None if absent/unreadable.

    Reads only the first block (a few hundred bytes); never raises.
    """
    try:
        with open(path, "rb") as handle:
            header_len = int.from_bytes(handle.read(4), "big")
            if not 0 < header_len < 64 * 1024:
                return None
            blob_header = handle.read(header_len)
            fields = {n: v for n, _w, v in _protobuf_fields(blob_header)}
            if fields.get(1) != b"OSMHeader" or not 0 < fields.get(3, 0) < 1024 * 1024:
                return None
            blob = {n: v for n, _w, v in _protobuf_fields(handle.read(fields[3]))}
        if 1 in blob:
            header_block = blob[1]
        elif 3 in blob:
            header_block = zlib.decompress(blob[3])
        else:
            return None
        raw_bbox = next((v for n, w, v in _protobuf_fields(header_block) if n == 1), None)
        if raw_bbox is None:
            return None
        # HeaderBBox: sint64 left=1, right=2, top=3, bottom=4 in nanodegrees (zigzag).
        coords = {
            n: ((v >> 1) ^ -(v & 1)) / 1e9 for n, w, v in _protobuf_fields(raw_bbox) if w == 0
        }
        return BBox(coords[1], coords[4], coords[2], coords[3])
    except (OSError, ValueError, KeyError, zlib.error):
        return None


def bbox_warnings(area: BBox, extract: BBox | None) -> list[str]:
    """Sanity warnings for the clip area (never errors)."""
    warnings = []
    width, height = area.max_lon - area.min_lon, area.max_lat - area.min_lat
    if width > MAX_BBOX_SPAN_DEGREES or height > MAX_BBOX_SPAN_DEGREES:
        warnings.append(
            f"clip bbox {area.as_list()} spans {width:.2f} x {height:.2f} degrees (more than"
            f" {MAX_BBOX_SPAN_DEGREES:g}); check for misplaced stops or set otp.bbox"
        )
    if extract is not None and (
        area.min_lon < extract.min_lon
        or area.min_lat < extract.min_lat
        or area.max_lon > extract.max_lon
        or area.max_lat > extract.max_lat
    ):
        warnings.append(
            f"clip bbox {area.as_list()} extends beyond the OSM extract bounds"
            f" {extract.as_list()}; streets outside the extract will be missing"
        )
    return warnings


def clip_osm(source: Path, target: Path, bbox: BBox) -> None:
    osmium = getattr(settings, "OTP_OSMIUM_BIN", None) or "osmium"
    executable = shutil.which(osmium)
    if executable is None:
        command = osmium_command("osmium", source, target, bbox)
        raise OsmiumNotFound(
            f"osmium-tool ({osmium!r}) is not installed; cannot clip the OSM extract", command
        )
    part = target.with_name(target.name + ".part")
    try:
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            osmium_command(executable, source, part, bbox),
            check=True,
            capture_output=True,
            text=True,
            timeout=OSMIUM_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        part.unlink(missing_ok=True)
        raise PrepareError(f"osmium extract failed: {exc.stderr.strip()[-500:]}") from exc
    except subprocess.TimeoutExpired as exc:
        part.unlink(missing_ok=True)
        raise PrepareError("osmium extract timed out") from exc
    os.replace(part, target)


# ------------------------------------------------------------------------- prepare


@dataclass
class PrepareReport:
    city_id: str
    directory: Path
    feeds: list[dict] = field(default_factory=list)
    skipped_feeds: list[str] = field(default_factory=list)
    removed_files: list[str] = field(default_factory=list)
    osm: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    prepared_at: str = ""

    def as_dict(self) -> dict:
        return {
            "city": self.city_id,
            "prepared_at": self.prepared_at,
            "feeds": self.feeds,
            "skipped_feeds": self.skipped_feeds,
            "removed_files": self.removed_files,
            "osm": self.osm,
            "warnings": self.warnings,
        }


def prepare_city(
    city_id: str,
    *,
    force: bool = False,
    clip: bool = True,
    buffer_km: float | None = None,
    osm_url: str | None = None,
    osm_file: Path | None = None,
    bbox: BBox | None = None,
    data_dir: Path | None = None,
) -> PrepareReport:
    """Fill ``<data_dir>/<city_id>/`` with everything ``otp --build`` needs.

    ``osm_url``, ``osm_file`` and ``bbox`` override city config (``osm_file`` uses a local
    regional extract instead of downloading one). Raises PrepareError.
    """
    city = get_city(city_id)
    if city is None:
        raise PrepareError(f"unknown city {city_id!r}")
    otp = city_otp_config(city)
    feeds, skipped = static_feeds_with_url(city)
    if not feeds:
        raise PrepareError(f"city {city_id!r} has no static GTFS feed with a URL")

    directory = (data_dir or otp_data_dir()) / city.id
    cache = directory / CACHE_SUBDIR
    cache.mkdir(parents=True, exist_ok=True)
    osm_target = directory / f"{city.id}.osm.pbf"
    if osm_file is not None and Path(osm_file).resolve() == osm_target.resolve():
        raise PrepareError(
            f"--osm-file must not be the prepared output {osm_target}; pass the regional extract"
        )
    with CityLock(cache / LOCK_FILE, city.id):
        return _prepare_locked(
            city,
            otp,
            feeds,
            skipped,
            directory,
            cache,
            osm_target,
            force=force,
            clip=clip,
            buffer_km=buffer_km,
            osm_url=osm_url,
            osm_file=osm_file,
            bbox=bbox,
        )


class CityLock:
    """Exclusive per-city lock file (O_EXCL); fails fast if another run holds it."""

    def __init__(self, path: Path, city_id: str):
        self.path = path
        self.city_id = city_id

    def __enter__(self):
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            try:
                holder = self.path.read_text(encoding="utf-8").strip()
            except OSError:
                holder = "unknown"
            raise PrepareError(
                f"another prepare_otp_inputs run for {self.city_id!r} is active ({holder})."
                f" If none is running (e.g. a killed run), delete {self.path}"
            ) from None
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(
                f"pid {os.getpid()} on {socket.gethostname()}"
                f" since {datetime.now(UTC).isoformat(timespec='seconds')}\n"
            )
        return self

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)
        return False


def _prepare_locked(
    city: City,
    otp: OtpCityConfig,
    feeds: list,
    skipped: list[str],
    directory: Path,
    cache: Path,
    osm_target: Path,
    *,
    force: bool,
    clip: bool,
    buffer_km: float | None,
    osm_url: str | None,
    osm_file: Path | None,
    bbox: BBox | None,
) -> PrepareReport:
    city_id = city.id
    report = PrepareReport(city_id=city.id, directory=directory, skipped_feeds=skipped)

    # 1. GTFS feeds (they also define the area to clip).
    for feed in feeds:
        target = directory / f"{feed.id}{GTFS_SUFFIX}"
        try:
            area = feed_area_filter(feed)
        except AreaFilterError as exc:
            raise PrepareError(f"{feed.id}: invalid filter in city config: {exc}") from exc
        # A filtered feed is downloaded into the cache and cut down to the city's area
        # (the same filter as the database import), so OTP never sees the whole feed.
        # The two paths keep separate download metadata, so neither trusts the other's
        # ETag for a file it did not write.
        plain_meta = cache / f"{feed.id}.json"
        source_zip = cache / f"{feed.id}.source{GTFS_SUFFIX}"
        source_meta = cache / f"{feed.id}.source.json"
        filter_stamp = cache / f"{feed.id}.filter.json"
        if area is None:
            if filter_stamp.exists():
                # The filter was removed: the current file is a filtered one, not the feed.
                for stale in (target, filter_stamp, source_zip, source_meta, plain_meta):
                    stale.unlink(missing_ok=True)
            download_target, meta_path = target, plain_meta
        else:
            plain_meta.unlink(missing_ok=True)
            download_target, meta_path = source_zip, source_meta
        result = fetch(feed.url, download_target, meta_path, validate_gtfs_zip, force)
        if result.error:
            report.warnings.append(
                f"{feed.id}: download failed, kept previous file: {result.error}"
            )
        entry = {"id": feed.id, "file": target.name, "status": result.status, **result.meta}
        if area is not None:
            entry["area_filter"] = _filter_if_changed(download_target, target, area, filter_stamp)
        report.feeds.append(entry | ({"error": result.error} if result.error else {}))
    wanted = {f"{feed.id}{GTFS_SUFFIX}" for feed in feeds}
    for stale in sorted(directory.glob(f"*{GTFS_SUFFIX}")):
        if stale.name not in wanted:
            stale.unlink()
            report.removed_files.append(stale.name)

    # 2. Regional OSM extract.
    region = cache / REGION_FILE
    if osm_file is not None:
        osm_file = Path(osm_file)
        if not osm_file.is_file():
            raise PrepareError(f"OSM file not found: {osm_file}")
        try:
            validate_osm_pbf(osm_file)
        except InvalidDownload as exc:
            raise PrepareError(f"{osm_file}: {exc}") from exc
        region = osm_file
        report.osm = {"source": "file", "file": str(osm_file)}
    else:
        url = osm_url or otp.osm_url
        if not url:
            raise PrepareError(
                f"city {city_id!r} has no otp.osm_url in city config; pass --osm-url or --osm-file"
            )
        result = fetch(
            url,
            region,
            cache / "region.json",
            validate_osm_pbf,
            force,
            label="OSM extract",
            max_bytes=getattr(settings, "OTP_OSM_MAX_BYTES", DEFAULT_OSM_MAX_BYTES),
            max_seconds=getattr(
                settings, "OTP_OSM_DOWNLOAD_MAX_SECONDS", DEFAULT_OSM_DOWNLOAD_MAX_SECONDS
            ),
        )
        if result.error:
            report.warnings.append(f"OSM: download failed, kept previous file: {result.error}")
        report.osm = {"source": "url", "status": result.status, **result.meta}

    # 3. Clip to the served area.
    if clip:
        if bbox is not None or otp.bbox is not None:
            area, area_source = bbox or otp.bbox, "config"
        else:
            stops = gtfs_stops_bbox([directory / name for name in sorted(wanted)])
            if stops is None:
                raise PrepareError("no stop coordinates in the GTFS feeds; set otp.bbox")
            km = float(
                buffer_km
                if buffer_km is not None
                else getattr(settings, "OTP_BBOX_BUFFER_KM", DEFAULT_BUFFER_KM)
            )
            area, area_source = stops.buffered(km), f"gtfs_stops+{km:g}km"
        report.warnings.extend(bbox_warnings(area, pbf_header_bbox(region)))
        _clip_if_changed(region, osm_target, area, cache / "clip.json")
        report.osm |= {"bbox": area.as_list(), "bbox_source": area_source, "clipped": True}
    else:
        (cache / "clip.json").unlink(missing_ok=True)
        _copy_if_changed(region, osm_target)
        report.osm |= {"clipped": False}
    report.osm |= {"file": osm_target.name, "file_size_bytes": osm_target.stat().st_size}

    # 4. OTP config files (last, so they always describe the files that are present).
    configs = build_otp_configs(city, [feed.id for feed in feeds], osm_target.name)
    for name, document in configs.items():
        (directory / name).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    report.prepared_at = datetime.now(UTC).isoformat(timespec="seconds")
    (directory / REPORT_FILE).write_text(
        json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def _source_stamp(path: Path) -> dict:
    stat = path.stat()
    return {"source": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _clip_if_changed(source: Path, target: Path, bbox: BBox, stamp_path: Path) -> None:
    """Clip unless the same source was already clipped to the same bbox."""
    stamp = _source_stamp(source) | {"bbox": bbox.as_list()}
    if target.exists() and stamp_path.exists():
        try:
            if json.loads(stamp_path.read_text(encoding="utf-8")) == stamp:
                return
        except (OSError, ValueError):
            pass
    clip_osm(source, target, bbox)
    stamp_path.write_text(json.dumps(stamp), encoding="utf-8")


def _filter_if_changed(source: Path, target: Path, area: AreaFilter, stamp_path: Path) -> dict:
    """Write the area-filtered feed unless the same source was already filtered with the
    same filter. Returns the filter statistics (stored in the stamp file)."""
    stamp = _source_stamp(source) | {"filter": area.as_dict()}
    if target.exists() and stamp_path.exists():
        try:
            stored = json.loads(stamp_path.read_text(encoding="utf-8"))
            if stored.get("stamp") == stamp:
                return stored.get("stats") or {}
        except (OSError, ValueError, AttributeError):
            pass
    part = target.with_name(target.name + ".part")
    try:
        # Same unpacked-size limit as the database import, checked before filtering.
        GtfsSource(
            source,
            max_uncompressed_bytes=getattr(
                settings, "TRANSIT_GTFS_MAX_UNCOMPRESSED_BYTES", 5 * 1024 * 1024 * 1024
            ),
        ).close()
        stats = filter_feed(source, part, area).as_dict()
    except (AreaFilterError, GtfsFormatError, OSError, zipfile.BadZipFile) as exc:
        part.unlink(missing_ok=True)
        raise PrepareError(f"cannot filter {source.name}: {exc}") from exc
    os.replace(part, target)
    stamp_path.write_text(json.dumps({"stamp": stamp, "stats": stats}), encoding="utf-8")
    return stats


def _copy_if_changed(source: Path, target: Path) -> None:
    if (
        target.exists()
        and target.stat().st_size == source.stat().st_size
        and target.stat().st_mtime_ns >= source.stat().st_mtime_ns
    ):
        return
    part = target.with_name(target.name + ".part")
    shutil.copyfile(source, part)
    os.replace(part, target)
