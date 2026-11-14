"""OTP input preparation with an area-filtered feed (issue #43). HTTP is always mocked."""

from __future__ import annotations

import csv
import io
import json
import shutil
import urllib.error
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from transit_data import otp_inputs
from transit_data.otp_inputs import PrepareError, prepare_city
from transit_data.static_gtfs import download

from .gtfs_support import FakeResponse, zip_directory

RAIL_AREA = Path(__file__).resolve().parent.parent / "fixtures" / "gtfs" / "rail_area"
REPO_OTP = Path(__file__).resolve().parents[3] / "otp"

CITY_ID = "railville"
URL_RAIL = "http://railville.invalid/rail.zip"
URL_PLAIN = "http://railville.invalid/plain.zip"
URL_OSM = "http://railville.invalid/region.osm.pbf"
OSM_FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "osm" / "krakow-main-square.osm.pbf"
)
BBOX = (19.80, 49.95, 20.10, 50.15)


class Server:
    """urlopen replacement serving url -> bytes, with ETag support."""

    def __init__(self):
        self.bodies: dict = {}
        self.requests: list = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        body = self.bodies[request.full_url]
        if isinstance(body, Exception):
            raise body
        etag = f'"{hash(body) & 0xFFFF}"'
        if request.get_header("If-none-match") == etag:
            raise urllib.error.HTTPError(request.full_url, 304, "Not Modified", {}, None)
        return FakeResponse(body, headers={"ETag": etag})


def make_city(filter_config):
    def feed(feed_id, url, filt=None):
        return SimpleNamespace(id=feed_id, url=url, kind="gtfs_static", entity=None, filter=filt)

    return SimpleNamespace(
        id=CITY_ID,
        timezone="Europe/Warsaw",
        otp=SimpleNamespace(osm_url=URL_OSM, bbox=None),
        feeds=(feed("rail", URL_RAIL, filter_config), feed("plain", URL_PLAIN)),
    )


def rail_filter(bbox=BBOX, exclude=("SKM",)):
    return SimpleNamespace(bbox=bbox, exclude_agencies=exclude)


@pytest.fixture
def server(monkeypatch):
    srv = Server()
    body = zip_directory(RAIL_AREA)
    srv.bodies = {URL_RAIL: body, URL_PLAIN: body, URL_OSM: OSM_FIXTURE.read_bytes()}
    monkeypatch.setattr(download.urllib.request, "urlopen", srv)
    return srv


@pytest.fixture
def env(tmp_path, settings, monkeypatch):
    config_dir = tmp_path / "otpconf"
    shutil.copytree(REPO_OTP / "config", config_dir / "config")
    settings.OTP_DATA_DIR = tmp_path / "data"
    settings.OTP_CONFIG_DIR = config_dir
    monkeypatch.setattr(otp_inputs, "clip_osm", lambda s, t, b: shutil.copyfile(s, t))
    city = {"value": make_city(rail_filter())}
    monkeypatch.setattr(otp_inputs, "get_city", lambda cid: city["value"])
    calls = []
    real_filter = otp_inputs.filter_feed

    def counting_filter(source, target, area):
        calls.append((Path(source).name, Path(target).name, area))
        return real_filter(source, target, area)

    monkeypatch.setattr(otp_inputs, "filter_feed", counting_filter)
    return SimpleNamespace(
        dir=tmp_path / "data" / CITY_ID,
        calls=calls,
        set_city=lambda c: city.update(value=c),
    )


def trips_of(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        text = archive.read("trips.txt").decode("utf-8")
    return sorted(row["trip_id"] for row in csv.DictReader(io.StringIO(text)))


def test_filtered_feed_is_downloaded_to_cache_and_filtered_to_the_output(env, server):
    prepare_city(CITY_ID, clip=False)
    source = env.dir / "cache" / "rail.source.gtfs.zip"
    assert source.is_file()
    assert trips_of(source) == ["T_BUS_1", "T_IC_1", "T_IC_2", "T_S1_1", "T_SKM_1"]
    assert trips_of(env.dir / "rail.gtfs.zip") == ["T_IC_1", "T_S1_1"]


def test_filtered_output_is_a_valid_gtfs_zip(env, server):
    prepare_city(CITY_ID, clip=False)
    otp_inputs.validate_gtfs_zip(env.dir / "rail.gtfs.zip")


def test_unfiltered_feed_is_written_as_downloaded(env, server):
    prepare_city(CITY_ID, clip=False)
    assert (env.dir / "plain.gtfs.zip").read_bytes() == server.bodies[URL_PLAIN]
    assert not (env.dir / "cache" / "plain.source.gtfs.zip").exists()
    assert [name for name, _t, _a in env.calls] == ["rail.source.gtfs.zip"]


def test_source_file_never_appears_at_the_top_level_where_otp_scans(env, server):
    prepare_city(CITY_ID, clip=False)
    assert sorted(p.name for p in env.dir.glob("*.gtfs.zip")) == ["plain.gtfs.zip", "rail.gtfs.zip"]


def test_build_config_references_the_filtered_file(env, server):
    prepare_city(CITY_ID, clip=False)
    build = json.loads((env.dir / "build-config.json").read_text())
    sources = {feed["feedId"]: feed["source"] for feed in build["transitFeeds"]}
    assert sources == {"rail": "rail.gtfs.zip", "plain": "plain.gtfs.zip"}


def test_prepare_report_records_filter_statistics(env, server):
    report = prepare_city(CITY_ID, clip=False)
    entry = next(f for f in report.feeds if f["id"] == "rail")
    assert entry["file"] == "rail.gtfs.zip"
    assert entry["area_filter"]["files"]["trips.txt"] == {"read": 5, "kept": 2}
    assert "area_filter" not in next(f for f in report.feeds if f["id"] == "plain")
    saved = json.loads((env.dir / "prepare-report.json").read_text())
    assert any("area_filter" in f for f in saved["feeds"])


def test_filter_arguments_are_passed_through(env, server):
    prepare_city(CITY_ID, clip=False)
    ((_, target, area),) = env.calls
    assert target == "rail.gtfs.zip.part"
    assert area.bbox == BBOX
    assert area.exclude_agencies == frozenset({"SKM"})


def test_no_part_file_is_left_behind(env, server):
    prepare_city(CITY_ID, clip=False)
    assert not list(env.dir.glob("*.part"))


def test_second_run_with_unchanged_source_and_filter_does_not_refilter(env, server):
    prepare_city(CITY_ID, clip=False)
    before = (env.dir / "rail.gtfs.zip").read_bytes()
    mtime = (env.dir / "rail.gtfs.zip").stat().st_mtime_ns
    prepare_city(CITY_ID, clip=False)
    assert len(env.calls) == 1
    assert (env.dir / "rail.gtfs.zip").read_bytes() == before
    assert (env.dir / "rail.gtfs.zip").stat().st_mtime_ns == mtime
    # the second download was conditional
    assert server.requests[-1].get_header("If-none-match") or any(
        r.get_header("If-none-match") for r in server.requests
    )


def test_unchanged_run_still_reports_statistics(env, server):
    prepare_city(CITY_ID, clip=False)
    report = prepare_city(CITY_ID, clip=False)
    entry = next(f for f in report.feeds if f["id"] == "rail")
    assert entry["area_filter"]["files"]["trips.txt"]["kept"] == 2


def test_changed_filter_refilters_without_new_download(env, server):
    prepare_city(CITY_ID, clip=False)
    env.set_city(make_city(rail_filter(exclude=())))
    prepare_city(CITY_ID, clip=False)
    assert len(env.calls) == 2
    assert trips_of(env.dir / "rail.gtfs.zip") == ["T_IC_1", "T_S1_1", "T_SKM_1"]


def test_changed_bbox_refilters(env, server):
    prepare_city(CITY_ID, clip=False)
    env.set_city(make_city(rail_filter(bbox=(19.0, 49.0, 21.5, 52.5))))
    prepare_city(CITY_ID, clip=False)
    assert len(env.calls) == 2
    assert "T_BUS_1" in trips_of(env.dir / "rail.gtfs.zip")


def test_changed_source_refilters(env, server):
    prepare_city(CITY_ID, clip=False)
    # The upstream feed now lacks the T_S1_1 trip's service... simplest change: new bytes.
    new_body = zip_directory(RAIL_AREA) + b""  # same content, different archive below
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(RAIL_AREA.iterdir()):
            text = path.read_text(encoding="utf-8")
            if path.name == "trips.txt":
                text = "\n".join(line for line in text.splitlines() if "T_S1_1" not in line) + "\n"
            archive.writestr(path.name, text)
    assert new_body != buffer.getvalue()
    server.bodies[URL_RAIL] = buffer.getvalue()
    prepare_city(CITY_ID, clip=False)
    assert len(env.calls) == 2
    assert trips_of(env.dir / "rail.gtfs.zip") == ["T_IC_1"]


def test_forced_run_refilters(env, server):
    prepare_city(CITY_ID, clip=False)
    prepare_city(CITY_ID, clip=False, force=True)
    assert len(env.calls) == 2


def test_missing_stamp_file_refilters(env, server):
    prepare_city(CITY_ID, clip=False)
    (env.dir / "cache" / "rail.filter.json").unlink()
    prepare_city(CITY_ID, clip=False)
    assert len(env.calls) == 2


def test_corrupt_stamp_file_refilters(env, server):
    prepare_city(CITY_ID, clip=False)
    (env.dir / "cache" / "rail.filter.json").write_text("{not json", encoding="utf-8")
    prepare_city(CITY_ID, clip=False)
    assert len(env.calls) == 2


def test_missing_output_refilters(env, server):
    prepare_city(CITY_ID, clip=False)
    (env.dir / "rail.gtfs.zip").unlink()
    prepare_city(CITY_ID, clip=False)
    assert len(env.calls) == 2
    assert (env.dir / "rail.gtfs.zip").is_file()


def test_empty_filter_result_raises_prepare_error(env, server):
    env.set_city(make_city(rail_filter(bbox=(0.0, 0.0, 1.0, 1.0))))
    with pytest.raises(PrepareError, match="cannot filter"):
        prepare_city(CITY_ID, clip=False)
    assert not (env.dir / "rail.gtfs.zip").exists()
    assert not list(env.dir.glob("*.part"))


def test_failed_refilter_keeps_the_previous_output(env, server):
    prepare_city(CITY_ID, clip=False)
    before = (env.dir / "rail.gtfs.zip").read_bytes()
    env.set_city(make_city(rail_filter(bbox=(0.0, 0.0, 1.0, 1.0))))
    with pytest.raises(PrepareError):
        prepare_city(CITY_ID, clip=False)
    assert (env.dir / "rail.gtfs.zip").read_bytes() == before


def test_invalid_filter_raises_prepare_error(env, server):
    env.set_city(make_city(rail_filter(bbox=(20.0, 50.0, 19.0, 51.0))))
    with pytest.raises(PrepareError, match="rail: invalid filter"):
        prepare_city(CITY_ID, clip=False)


def test_gtfs_stops_bbox_for_osm_clipping_uses_the_filtered_feed(env, server, monkeypatch):
    seen = {}
    real = otp_inputs.gtfs_stops_bbox

    def spy(paths):
        seen["paths"] = [Path(p).name for p in paths]
        return real(paths)

    monkeypatch.setattr(otp_inputs, "gtfs_stops_bbox", spy)
    prepare_city(CITY_ID, clip=True)
    assert "rail.gtfs.zip" in seen["paths"]
    assert "rail.source.gtfs.zip" not in seen["paths"]


# ------------------------------------------------- download metadata and filter removal


def test_filtered_feed_keeps_its_download_metadata_in_the_source_meta_file(env, server):
    prepare_city(CITY_ID, clip=False)
    cache = env.dir / "cache"
    assert json.loads((cache / "rail.source.json").read_text())["url"] == URL_RAIL
    assert not (cache / "rail.json").exists()
    assert (cache / "plain.json").exists()


def test_filtered_run_deletes_the_plain_download_metadata(env, server):
    cache = env.dir / "cache"
    cache.mkdir(parents=True)
    (cache / "rail.json").write_text('{"url": "x", "etag": "\\"old\\""}', encoding="utf-8")
    prepare_city(CITY_ID, clip=False)
    assert not (cache / "rail.json").exists()


def test_second_filtered_run_downloads_conditionally_using_the_source_meta(env, server):
    prepare_city(CITY_ID, clip=False)
    prepare_city(CITY_ID, clip=False)
    rail_requests = [r for r in server.requests if r.full_url == URL_RAIL]
    assert rail_requests[-1].get_header("If-none-match")


def test_removing_the_filter_replaces_the_filtered_file_with_the_full_feed(env, server):
    prepare_city(CITY_ID, clip=False)
    assert trips_of(env.dir / "rail.gtfs.zip") == ["T_IC_1", "T_S1_1"]
    env.set_city(make_city(None))
    prepare_city(CITY_ID, clip=False)
    cache = env.dir / "cache"
    assert trips_of(env.dir / "rail.gtfs.zip") == [
        "T_BUS_1",
        "T_IC_1",
        "T_IC_2",
        "T_S1_1",
        "T_SKM_1",
    ]
    for leftover in ("rail.filter.json", "rail.source.gtfs.zip", "rail.source.json"):
        assert not (cache / leftover).exists(), leftover
    assert (cache / "rail.json").exists()


def test_removing_the_filter_downloads_unconditionally(env, server):
    prepare_city(CITY_ID, clip=False)
    env.set_city(make_city(None))
    prepare_city(CITY_ID, clip=False)
    last_rail_request = [r for r in server.requests if r.full_url == URL_RAIL][-1]
    assert last_rail_request.get_header("If-none-match") is None


def test_failed_download_after_removing_the_filter_raises_and_keeps_no_stale_file(env, server):
    prepare_city(CITY_ID, clip=False)
    env.set_city(make_city(None))
    server.bodies[URL_RAIL] = urllib.error.URLError("down")
    with pytest.raises(PrepareError):
        prepare_city(CITY_ID, clip=False)
    assert not (env.dir / "rail.gtfs.zip").exists()


def test_unfiltered_feed_without_filter_history_is_not_touched(env, server):
    prepare_city(CITY_ID, clip=False)
    before = (env.dir / "plain.gtfs.zip").stat().st_mtime_ns
    prepare_city(CITY_ID, clip=False)
    assert (env.dir / "plain.gtfs.zip").stat().st_mtime_ns == before


def test_oversized_source_raises_prepare_error_and_leaves_no_output(env, server, settings):
    settings.TRANSIT_GTFS_MAX_UNCOMPRESSED_BYTES = 10
    with pytest.raises(PrepareError, match="cannot filter"):
        prepare_city(CITY_ID, clip=False)
    assert not (env.dir / "rail.gtfs.zip").exists()
    assert not list(env.dir.glob("*.part"))
