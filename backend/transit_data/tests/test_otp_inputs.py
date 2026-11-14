"""OTP input preparation (issue #8): downloads, clipping, generated and committed configs.

HTTP is always mocked; cities are fictional. Real clipping tests need osmium-tool and are
skipped when it is not installed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management import CommandError, call_command

from transit_data import otp_inputs
from transit_data.otp_inputs import (
    BBox,
    OsmiumNotFound,
    PrepareError,
    build_otp_configs,
    clip_osm,
    fetch,
    gtfs_stops_bbox,
    prepare_city,
)
from transit_data.static_gtfs import download

from .gtfs_support import FIXTURE_FEED, FakeResponse, copy_feed, zip_directory

OSM_FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "osm" / "krakow-main-square.osm.pbf"
)
REPO_OTP = Path(__file__).resolve().parents[3] / "otp"

CITY_ID = "otpville"
URL_A = "http://otpville.invalid/a.zip"
URL_B = "http://otpville.invalid/b.zip"
URL_OSM = "http://otpville.invalid/region.osm.pbf"
HAS_OSMIUM = shutil.which("osmium") is not None
STOPS_BBOX = BBox(19.9380, 50.0400, 19.9800, 50.0615)


class Server:
    """urlopen replacement serving url -> bytes | Exception, with ETag support."""

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

    def urls(self) -> list[str]:
        return [r.full_url for r in self.requests]


def make_city(feeds=None, otp=None, timezone="Europe/Warsaw"):
    feeds = feeds if feeds is not None else [("fa", URL_A), ("fb", URL_B)]
    return SimpleNamespace(
        id=CITY_ID,
        timezone=timezone,
        otp=otp,
        feeds=tuple(
            SimpleNamespace(id=i, url=u, kind="gtfs_static", entity=None) for i, u in feeds
        ),
    )


def otp_section(bbox=None):
    return SimpleNamespace(osm_url=URL_OSM, bbox=bbox)


def use_city(monkeypatch, city):
    monkeypatch.setattr(otp_inputs, "get_city", lambda cid: city if cid == city.id else None)


@pytest.fixture
def gtfs_zip(tmp_path) -> bytes:
    return zip_directory(copy_feed(tmp_path / "feed_src"))


@pytest.fixture
def server(monkeypatch, gtfs_zip):
    srv = Server()
    srv.bodies = {URL_A: gtfs_zip, URL_B: gtfs_zip, URL_OSM: OSM_FIXTURE.read_bytes()}
    monkeypatch.setattr(download.urllib.request, "urlopen", srv)
    return srv


@pytest.fixture
def env(tmp_path, settings, monkeypatch):
    """Temp data dir, temp copy of the committed config, fake city, recording fake clip."""
    config_dir = tmp_path / "otpconf"
    shutil.copytree(REPO_OTP / "config", config_dir / "config")
    settings.OTP_DATA_DIR = tmp_path / "data"
    settings.OTP_CONFIG_DIR = config_dir
    settings.OTP_OSMIUM_BIN = "osmium"
    clips: list = []

    def fake_clip(source, target, bbox):
        clips.append((source, target, bbox))
        shutil.copyfile(source, target)

    monkeypatch.setattr(otp_inputs, "clip_osm", fake_clip)
    use_city(monkeypatch, make_city(otp=otp_section()))
    return SimpleNamespace(data=tmp_path / "data", config=config_dir, clips=clips)


# ------------------------------------------------------------------------------- BBox


class TestBBox:
    def test_parse_string_and_sequence(self):
        assert BBox.parse("19,50,20,51") == BBox(19, 50, 20, 51)
        assert BBox.parse([19, 50, 20, 51]) == BBox(19, 50, 20, 51)

    @pytest.mark.parametrize(
        "value",
        ["1,2,3", "a,b,c,d", "20,50,19,51", "19,51,20,50", "0,0,200,10", "0,-95,1,1", None],
    )
    def test_parse_rejects_invalid(self, value):
        with pytest.raises(PrepareError):
            BBox.parse(value)

    def test_buffer_grows_every_side_by_roughly_the_distance(self):
        box = BBox(19.9, 50.0, 20.0, 50.1).buffered(3)
        assert box.min_lat == pytest.approx(50.0 - 3 / 111.32, abs=1e-4)
        assert box.max_lat == pytest.approx(50.1 + 3 / 111.32, abs=1e-4)
        # at 50 degrees north a degree of longitude is shorter, so the lon margin is larger
        assert 19.9 - box.min_lon > 3 / 111.32
        assert box.max_lon - 20.0 == pytest.approx(19.9 - box.min_lon)

    def test_buffer_is_clamped_to_the_globe(self):
        box = BBox(-179.99, -89.99, 179.99, 89.99).buffered(50)
        assert (box.min_lon, box.min_lat, box.max_lon, box.max_lat) == (-180, -90, 180, 90)

    def test_osmium_string_has_four_comma_separated_numbers(self):
        assert len(BBox(19.9, 50.0, 20.0, 50.1).as_osmium().split(",")) == 4


class TestGtfsStopsBbox:
    def test_bbox_of_fixture_feed_stops(self, tmp_path):
        path = tmp_path / "f.zip"
        path.write_bytes(zip_directory(FIXTURE_FEED))
        assert gtfs_stops_bbox([path]) == STOPS_BBOX

    def test_ignores_missing_and_invalid_coordinates(self, tmp_path):
        extra = "Z0,,Zero,0,0,0,,,\nZE,,Empty,,,0,,,\nZB,,Bad,x,y,0,,,\nZR,,Range,99,19,0,,,\n"
        feed = copy_feed(tmp_path / "f", {"stops.txt": lambda t: t + extra})
        path = tmp_path / "f.zip"
        path.write_bytes(zip_directory(feed))
        assert gtfs_stops_bbox([path]) == STOPS_BBOX

    def test_none_when_no_usable_stops(self, tmp_path):
        feed = copy_feed(
            tmp_path / "f", {"stops.txt": lambda t: t.splitlines()[0] + "\nZ,,Z,0,0,0,,,\n"}
        )
        path = tmp_path / "f.zip"
        path.write_bytes(zip_directory(feed))
        assert gtfs_stops_bbox([path]) is None


# ------------------------------------------------------------------------------ fetch


def valid_zip(path: Path) -> None:
    otp_inputs.validate_gtfs_zip(path)


class TestFetch:
    def test_downloads_atomically_and_stores_metadata(self, tmp_path, server):
        target = tmp_path / "x.gtfs.zip"
        result = fetch(URL_A, target, tmp_path / "x.json", valid_zip)
        assert result.status == "downloaded"
        assert target.exists() and not (tmp_path / "x.gtfs.zip.part").exists()
        meta = json.loads((tmp_path / "x.json").read_text())
        assert meta["url"] == URL_A and len(meta["sha256"]) == 64 and meta["etag"]

    def test_second_call_is_conditional_and_unchanged(self, tmp_path, server):
        target = tmp_path / "x.gtfs.zip"
        fetch(URL_A, target, tmp_path / "x.json", valid_zip)
        before = target.read_bytes()
        result = fetch(URL_A, target, tmp_path / "x.json", valid_zip)
        assert result.status == "unchanged"
        assert server.requests[-1].get_header("If-none-match")
        assert target.read_bytes() == before

    def test_force_skips_conditional_headers(self, tmp_path, server):
        target = tmp_path / "x.gtfs.zip"
        fetch(URL_A, target, tmp_path / "x.json", valid_zip)
        result = fetch(URL_A, target, tmp_path / "x.json", valid_zip, force=True)
        assert result.status == "downloaded"
        assert server.requests[-1].get_header("If-none-match") is None

    def test_changed_url_ignores_old_metadata(self, tmp_path, server):
        target = tmp_path / "x.gtfs.zip"
        fetch(URL_A, target, tmp_path / "x.json", valid_zip)
        fetch(URL_B, target, tmp_path / "x.json", valid_zip)
        assert server.requests[-1].get_header("If-none-match") is None

    def test_failure_keeps_previous_file(self, tmp_path, server):
        target = tmp_path / "x.gtfs.zip"
        fetch(URL_A, target, tmp_path / "x.json", valid_zip)
        before = target.read_bytes()
        server.bodies[URL_A] = urllib.error.URLError("boom")
        result = fetch(URL_A, target, tmp_path / "x.json", valid_zip, force=True)
        assert result.status == "kept_previous" and result.error
        assert target.read_bytes() == before
        assert not (tmp_path / "x.gtfs.zip.part").exists()

    def test_invalid_zip_keeps_previous_file(self, tmp_path, server):
        target = tmp_path / "x.gtfs.zip"
        fetch(URL_A, target, tmp_path / "x.json", valid_zip)
        before = target.read_bytes()
        server.bodies[URL_A] = b"<html>not a zip</html>"
        result = fetch(URL_A, target, tmp_path / "x.json", valid_zip, force=True)
        assert result.status == "kept_previous"
        assert target.read_bytes() == before
        assert not (tmp_path / "x.gtfs.zip.part").exists()

    def test_failure_without_previous_file_raises(self, tmp_path, server):
        server.bodies[URL_A] = urllib.error.URLError("boom")
        with pytest.raises(PrepareError):
            fetch(URL_A, tmp_path / "x.gtfs.zip", tmp_path / "x.json", valid_zip)
        assert not (tmp_path / "x.gtfs.zip").exists()
        assert not (tmp_path / "x.gtfs.zip.part").exists()

    def test_zip_missing_required_gtfs_files_is_rejected(self, tmp_path, server):
        feed = copy_feed(tmp_path / "f", {"stop_times.txt": None})
        server.bodies[URL_A] = zip_directory(feed)
        with pytest.raises(PrepareError, match="stop_times"):
            fetch(URL_A, tmp_path / "x.gtfs.zip", tmp_path / "x.json", valid_zip)


# ------------------------------------------------------------------------ prepare_city


class TestPrepareCity:
    def test_creates_complete_directory(self, env, server):
        report = prepare_city(CITY_ID, clip=False)
        d = env.data / CITY_ID
        for name in (
            "fa.gtfs.zip",
            "fb.gtfs.zip",
            f"{CITY_ID}.osm.pbf",
            "build-config.json",
            "router-config.json",
            "otp-config.json",
            "prepare-report.json",
        ):
            assert (d / name).is_file(), name
        assert [f["id"] for f in report.feeds] == ["fa", "fb"]
        saved = json.loads((d / "prepare-report.json").read_text())
        assert saved["city"] == CITY_ID and saved["osm"]["clipped"] is False

    def test_build_config_lists_feeds_osm_and_timezone(self, env, server):
        prepare_city(CITY_ID, clip=False)
        build = json.loads((env.data / CITY_ID / "build-config.json").read_text())
        assert build["transitFeeds"] == [
            {"type": "gtfs", "feedId": "fa", "source": "fa.gtfs.zip"},
            {"type": "gtfs", "feedId": "fb", "source": "fb.gtfs.zip"},
        ]
        assert build["osm"] == [{"source": f"{CITY_ID}.osm.pbf"}]
        assert build["transitModelTimeZone"] == "Europe/Warsaw"
        assert build["osmDefaults"]["timeZone"] == "Europe/Warsaw"
        assert build["osmDefaults"]["osmTagMapping"] == "default"  # shared defaults survive

    def test_feed_without_url_is_skipped(self, env, server, monkeypatch):
        use_city(
            monkeypatch,
            make_city(feeds=[("fa", URL_A), ("fnull", None)], otp=otp_section()),
        )
        report = prepare_city(CITY_ID, clip=False)
        assert report.skipped_feeds == ["fnull"]
        assert not (env.data / CITY_ID / "fnull.gtfs.zip").exists()
        assert server.urls().count(URL_A) == 1

    def test_stale_gtfs_files_are_removed(self, env, server):
        d = env.data / CITY_ID
        d.mkdir(parents=True)
        (d / "old.gtfs.zip").write_bytes(b"x")
        (d / "keep.txt").write_text("k")
        report = prepare_city(CITY_ID, clip=False)
        assert not (d / "old.gtfs.zip").exists()
        assert report.removed_files == ["old.gtfs.zip"]
        assert (d / "keep.txt").exists()

    def test_failed_feed_download_keeps_previous_and_warns(self, env, server):
        prepare_city(CITY_ID, clip=False)
        path = env.data / CITY_ID / "fa.gtfs.zip"
        before = path.read_bytes()
        server.bodies[URL_A] = urllib.error.URLError("down")
        report = prepare_city(CITY_ID, clip=False, force=True)
        assert path.read_bytes() == before
        assert any("fa" in w for w in report.warnings)

    def test_failed_feed_download_without_previous_is_an_error(self, env, server):
        server.bodies[URL_A] = urllib.error.URLError("down")
        with pytest.raises(PrepareError):
            prepare_city(CITY_ID, clip=False)

    def test_second_run_is_unchanged(self, env, server):
        prepare_city(CITY_ID, clip=False)
        report = prepare_city(CITY_ID, clip=False)
        assert {f["status"] for f in report.feeds} == {"unchanged"}
        assert report.osm["status"] == "unchanged"

    def test_unknown_city(self, env):
        with pytest.raises(PrepareError, match="unknown city"):
            prepare_city("nowhere")

    def test_city_without_downloadable_feed(self, env, monkeypatch):
        use_city(monkeypatch, make_city(feeds=[("fnull", None)]))
        with pytest.raises(PrepareError, match="no static GTFS feed"):
            prepare_city(CITY_ID)

    def test_missing_osm_url_is_an_instructive_error(self, env, server, monkeypatch):
        use_city(monkeypatch, make_city(otp=None))
        with pytest.raises(PrepareError, match="osm-url"):
            prepare_city(CITY_ID, clip=False)

    def test_osm_url_override_is_used(self, env, server, monkeypatch):
        use_city(monkeypatch, make_city(otp=None))
        other = "http://otpville.invalid/other.osm.pbf"
        server.bodies[other] = OSM_FIXTURE.read_bytes()
        prepare_city(CITY_ID, clip=False, osm_url=other)
        assert other in server.urls() and URL_OSM not in server.urls()

    def test_osm_file_is_used_without_download(self, env, server):
        report = prepare_city(CITY_ID, clip=False, osm_file=OSM_FIXTURE)
        assert URL_OSM not in server.urls()
        assert report.osm["source"] == "file"

    def test_osm_file_missing_or_invalid(self, env, server, tmp_path):
        with pytest.raises(PrepareError, match="not found"):
            prepare_city(CITY_ID, clip=False, osm_file=tmp_path / "nope.pbf")
        bad = tmp_path / "bad.pbf"
        bad.write_bytes(b"this is not pbf")
        with pytest.raises(PrepareError, match="PBF"):
            prepare_city(CITY_ID, clip=False, osm_file=bad)

    def test_invalid_osm_download_is_rejected(self, env, server):
        server.bodies[URL_OSM] = b"<html>error page</html>"
        with pytest.raises(PrepareError):
            prepare_city(CITY_ID, clip=False)

    def test_no_clip_copies_whole_extract(self, env, server):
        prepare_city(CITY_ID, clip=False)
        target = env.data / CITY_ID / f"{CITY_ID}.osm.pbf"
        assert target.read_bytes() == OSM_FIXTURE.read_bytes()
        assert env.clips == []


class TestClippingArea:
    def test_default_area_is_stops_bbox_plus_default_buffer(self, env, server):
        report = prepare_city(CITY_ID)
        assert report.osm["bbox"] == STOPS_BBOX.buffered(3).as_list()
        assert report.osm["bbox_source"] == "gtfs_stops+3km"
        assert len(env.clips) == 1

    def test_buffer_km_argument_and_setting(self, env, server, settings):
        assert prepare_city(CITY_ID, buffer_km=1).osm["bbox"] == STOPS_BBOX.buffered(1).as_list()
        settings.OTP_BBOX_BUFFER_KM = 5
        assert prepare_city(CITY_ID).osm["bbox"] == STOPS_BBOX.buffered(5).as_list()

    def test_city_config_bbox_overrides_stops(self, env, server, monkeypatch):
        use_city(monkeypatch, make_city(otp=otp_section([19.0, 50.0, 20.0, 51.0])))
        report = prepare_city(CITY_ID)
        assert report.osm["bbox"] == [19.0, 50.0, 20.0, 51.0]
        assert report.osm["bbox_source"] == "config"

    def test_argument_bbox_overrides_city_config(self, env, server, monkeypatch):
        use_city(monkeypatch, make_city(otp=otp_section([19.0, 50.0, 20.0, 51.0])))
        report = prepare_city(CITY_ID, bbox=BBox(19.5, 50.5, 19.6, 50.6))
        assert report.osm["bbox"] == [19.5, 50.5, 19.6, 50.6]

    def test_clip_skipped_when_source_and_bbox_unchanged(self, env, server):
        prepare_city(CITY_ID)
        prepare_city(CITY_ID)
        assert len(env.clips) == 1

    def test_clip_repeated_when_bbox_changes(self, env, server):
        prepare_city(CITY_ID)
        prepare_city(CITY_ID, buffer_km=1)
        assert len(env.clips) == 2

    def test_clip_repeated_when_source_changes(self, env, server):
        prepare_city(CITY_ID)
        region = env.data / CITY_ID / "cache" / "region.osm.pbf"
        region.write_bytes(region.read_bytes() + b"\0")
        prepare_city(CITY_ID, osm_file=region)
        assert len(env.clips) == 2

    def test_error_when_no_stop_coordinates(self, env, server, tmp_path):
        feed = copy_feed(tmp_path / "empty", {"stops.txt": lambda t: t.splitlines()[0] + "\n"})
        server.bodies[URL_A] = server.bodies[URL_B] = zip_directory(feed)
        with pytest.raises(PrepareError, match="bbox"):
            prepare_city(CITY_ID)


# ------------------------------------------------------------------ OTP config merging


class TestBuildConfigs:
    def test_city_specific_values_come_from_city_config_not_files(self, env):
        shared = env.config / "config" / "build-config.json"
        data = json.loads(shared.read_text())
        data["transitModelTimeZone"] = "Asia/Tokyo"
        data["transitFeeds"] = [{"type": "gtfs", "feedId": "evil", "source": "evil.zip"}]
        data["osm"] = [{"source": "evil.pbf"}]
        shared.write_text(json.dumps(data))
        configs = build_otp_configs(make_city(timezone="Europe/Berlin"), ["fa"], "x.osm.pbf")
        build = configs["build-config.json"]
        assert build["transitModelTimeZone"] == "Europe/Berlin"
        assert [f["feedId"] for f in build["transitFeeds"]] == ["fa"]
        assert build["osm"] == [{"source": "x.osm.pbf"}]

    def test_per_city_override_is_deep_merged(self, env):
        override_dir = env.config / CITY_ID
        override_dir.mkdir()
        (override_dir / "router-config.json").write_text(
            json.dumps({"routingDefaults": {"walk": {"speed": 1.0}}, "transit": None})
        )
        router = build_otp_configs(make_city(), ["fa"], "x.osm.pbf")["router-config.json"]
        assert router["routingDefaults"]["walk"]["speed"] == 1.0
        assert router["routingDefaults"]["walk"]["reluctance"] == 2.0  # sibling kept
        assert router["routingDefaults"]["numItineraries"] == 5
        assert router["transit"] is None

    def test_override_of_other_city_is_ignored(self, env):
        other = env.config / "othercity"
        other.mkdir()
        (other / "router-config.json").write_text('{"server": {"apiProcessingTimeout": "PT1S"}}')
        router = build_otp_configs(make_city(), ["fa"], "x")["router-config.json"]
        assert router["server"]["apiProcessingTimeout"] == "PT10S"

    def test_missing_shared_dir(self, tmp_path):
        with pytest.raises(PrepareError, match="shared config"):
            build_otp_configs(make_city(), ["fa"], "x", config_dir=tmp_path)

    def test_invalid_json_override(self, env):
        (env.config / CITY_ID).mkdir()
        (env.config / CITY_ID / "build-config.json").write_text("{not json")
        with pytest.raises(PrepareError, match="cannot read"):
            build_otp_configs(make_city(), ["fa"], "x")

    def test_non_object_override(self, env):
        (env.config / CITY_ID).mkdir()
        (env.config / CITY_ID / "build-config.json").write_text("[1]")
        with pytest.raises(PrepareError, match="JSON object"):
            build_otp_configs(make_city(), ["fa"], "x")

    def test_generated_build_config_has_only_known_keys(self, env):
        build = build_otp_configs(make_city(), ["fa"], "x")["build-config.json"]
        known = {
            "transitServiceStart", "transitServiceEnd", "osmDefaults", "areaVisibility",
            "staticParkAndRide", "staticBikeParkAndRide", "maxTransferDuration",
            "transferRequests", "transitModelTimeZone", "transitFeeds", "osm",
        }  # fmt: skip
        assert set(build) <= known
        assert {"transitFeeds", "osm", "transitModelTimeZone"} <= set(build)


class TestCommittedConfig:
    @pytest.mark.parametrize("name", ["build-config", "router-config", "otp-config"])
    def test_committed_config_is_a_json_object(self, name):
        data = json.loads((REPO_OTP / "config" / f"{name}.json").read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_committed_build_config_has_no_city_specific_parts(self):
        data = json.loads((REPO_OTP / "config" / "build-config.json").read_text())
        assert not {"transitFeeds", "osm", "transitModelTimeZone"} & set(data)

    @pytest.mark.parametrize("city", ["krakow", "warszawa"])
    def test_sample_queries_exist(self, city):
        assert (REPO_OTP / "queries" / f"{city}-sample.graphql").read_text().strip()


# -------------------------------------------------------------------------- osmium


class TestClipOsm:
    def test_missing_osmium_raises_with_command(self, settings, tmp_path):
        settings.OTP_OSMIUM_BIN = "definitely-not-osmium-xyz"
        with pytest.raises(OsmiumNotFound) as err:
            clip_osm(OSM_FIXTURE, tmp_path / "o.pbf", BBox(19.9, 50.0, 20.0, 50.1))
        assert "extract" in err.value.command and "complete_ways" in err.value.command

    def test_command_uses_expected_osmium_arguments(self, tmp_path, monkeypatch):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv)
            Path(argv[argv.index("--output") + 1]).write_bytes(b"x")
            return subprocess.CompletedProcess(argv, 0, "", "")

        monkeypatch.setattr(otp_inputs.shutil, "which", lambda b: "/usr/bin/osmium")
        monkeypatch.setattr(otp_inputs.subprocess, "run", fake_run)
        target = tmp_path / "o.pbf"
        clip_osm(OSM_FIXTURE, target, BBox(19.9, 50.0, 20.0, 50.1))
        argv = calls[0]
        assert argv[1] == "extract"
        assert argv[argv.index("--strategy") + 1] == "complete_ways"
        assert "--set-bounds" in argv
        assert target.read_bytes() == b"x" and not (tmp_path / "o.pbf.part").exists()

    def test_osmium_failure_raises_and_leaves_no_part_file(self, tmp_path, monkeypatch):
        def fake_run(argv, **kwargs):
            Path(argv[argv.index("--output") + 1]).write_bytes(b"partial")
            raise subprocess.CalledProcessError(2, argv, stderr="bad input")

        monkeypatch.setattr(otp_inputs.shutil, "which", lambda b: "/usr/bin/osmium")
        monkeypatch.setattr(otp_inputs.subprocess, "run", fake_run)
        with pytest.raises(PrepareError, match="bad input"):
            clip_osm(OSM_FIXTURE, tmp_path / "o.pbf", BBox(19.9, 50.0, 20.0, 50.1))
        assert not (tmp_path / "o.pbf").exists()
        assert not (tmp_path / "o.pbf.part").exists()

    @pytest.mark.skipif(not HAS_OSMIUM, reason="osmium-tool is not installed")
    def test_real_clip_of_fixture_extract(self, tmp_path):
        target = tmp_path / "clipped.osm.pbf"
        clip_osm(OSM_FIXTURE, target, BBox(19.93, 50.055, 19.95, 50.068))
        assert target.stat().st_size > 0
        otp_inputs.validate_osm_pbf(target)


# ------------------------------------------------------------------------- command


class TestCommand:
    def run(self, *args):
        out = StringIO()
        call_command("prepare_otp_inputs", *args, stdout=out)
        return out.getvalue()

    def test_city_is_required(self):
        with pytest.raises(CommandError, match="city"):
            call_command("prepare_otp_inputs")

    def test_success_output(self, env, server):
        out = self.run("--city", CITY_ID, "--no-clip")
        assert CITY_ID in out and "gtfs fa" in out and "ready" in out
        assert (env.data / CITY_ID / "build-config.json").exists()

    def test_options_are_passed_through(self, env, server):
        self.run("--city", CITY_ID, "--bbox", "19,50,20,51")
        assert env.clips[0][2] == BBox(19, 50, 20, 51)
        self.run("--city", CITY_ID, "--buffer-km", "1", "--bbox", "19,50,21,51")
        assert len(env.clips) == 2

    def test_osm_file_option(self, env, server):
        self.run("--city", CITY_ID, "--no-clip", "--osm-file", str(OSM_FIXTURE))
        assert URL_OSM not in server.urls()

    def test_unknown_city_is_command_error(self, env):
        with pytest.raises(CommandError, match="unknown city"):
            self.run("--city", "nowhere")

    def test_invalid_bbox_is_command_error(self, env, server):
        with pytest.raises(CommandError, match="bbox"):
            self.run("--city", CITY_ID, "--bbox", "1,2,3")

    def test_missing_osmium_message_is_instructive(self, env, server, monkeypatch, settings):
        monkeypatch.setattr(otp_inputs, "clip_osm", clip_osm)  # use the real one
        settings.OTP_OSMIUM_BIN = "definitely-not-osmium-xyz"
        with pytest.raises(CommandError) as err:
            self.run("--city", CITY_ID)
        message = str(err.value)
        assert "--no-clip" in message and "osmium" in message and "extract" in message


# ------------------------------------------------------------- download_feed arguments


def one_body_server(body: bytes):
    def opener(request, timeout=None):
        return FakeResponse(body)

    return opener


class TestDownloadFeedLimits:
    def serve(self, monkeypatch, body: bytes):
        monkeypatch.setattr(download.urllib.request, "urlopen", one_body_server(body))

    def test_defaults_unchanged_when_new_arguments_are_omitted(
        self, tmp_path, monkeypatch, settings
    ):
        settings.TRANSIT_GTFS_MAX_BYTES = 10
        self.serve(monkeypatch, b"x" * 50)
        with pytest.raises(download.DownloadError, match="feed larger than 10 bytes"):
            download.download_feed("http://x.invalid/f", tmp_path / "f")

    def test_max_bytes_and_label_override_settings(self, tmp_path, monkeypatch, settings):
        settings.TRANSIT_GTFS_MAX_BYTES = 10
        self.serve(monkeypatch, b"x" * 50)
        with pytest.raises(download.DownloadError, match="OSM extract larger than 20 bytes"):
            download.download_feed(
                "http://x.invalid/f", tmp_path / "f", max_bytes=20, label="OSM extract"
            )
        result = download.download_feed("http://x.invalid/f", tmp_path / "f", max_bytes=100)
        assert result.size_bytes == 50

    def test_max_seconds_override(self, tmp_path, monkeypatch, settings):
        settings.TRANSIT_GTFS_DOWNLOAD_MAX_SECONDS = 10**6
        self.serve(monkeypatch, b"x" * 50)
        with pytest.raises(download.DownloadError, match="longer than -1"):
            download.download_feed("http://x.invalid/f", tmp_path / "f", max_seconds=-1)


class TestOsmDownloadLimits:
    def test_oversized_osm_download_is_rejected_with_label(self, env, server, settings):
        settings.OTP_OSM_MAX_BYTES = 100
        with pytest.raises(PrepareError, match="OSM extract larger than 100 bytes"):
            prepare_city(CITY_ID, clip=False)

    def test_osm_limit_does_not_apply_to_gtfs_feeds(self, env, server, settings):
        settings.OTP_OSM_MAX_BYTES = 10**9
        settings.TRANSIT_GTFS_MAX_BYTES = 10**9
        prepare_city(CITY_ID, clip=False)

    def test_osm_deadline_setting_is_used(self, env, server, settings):
        settings.OTP_OSM_DOWNLOAD_MAX_SECONDS = -1
        with pytest.raises(PrepareError, match="longer than"):
            prepare_city(CITY_ID, clip=False)


# ---------------------------------------------------------------- PBF header and warnings


class TestPbfHeaderBbox:
    def test_fixture_bounds(self):
        box = otp_inputs.pbf_header_bbox(OSM_FIXTURE)
        assert box is not None
        assert box.min_lon == pytest.approx(19.937, abs=0.002)
        assert box.min_lat == pytest.approx(50.06, abs=0.002)
        assert box.max_lon == pytest.approx(19.94, abs=0.002)
        assert box.max_lat == pytest.approx(50.0625, abs=0.002)

    @pytest.mark.parametrize(
        "content", [b"", b"abc", b"\x00\x00\x00\x05hello", b"\xff" * 200, b"<html></html>" * 20]
    )
    def test_garbage_returns_none_and_never_raises(self, tmp_path, content):
        path = tmp_path / "bad.pbf"
        path.write_bytes(content)
        assert otp_inputs.pbf_header_bbox(path) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert otp_inputs.pbf_header_bbox(tmp_path / "nope.pbf") is None

    def test_truncated_file_returns_none(self, tmp_path):
        path = tmp_path / "cut.pbf"
        path.write_bytes(OSM_FIXTURE.read_bytes()[:40])
        assert otp_inputs.pbf_header_bbox(path) is None


class TestBboxWarnings:
    EXTRACT = BBox(19.0, 49.0, 21.0, 51.0)

    def test_no_warning_for_area_inside_extract(self):
        assert otp_inputs.bbox_warnings(BBox(19.5, 49.5, 20.0, 50.0), self.EXTRACT) == []

    def test_no_extract_bounds_means_no_extent_warning(self):
        assert otp_inputs.bbox_warnings(BBox(19.5, 49.5, 20.0, 50.0), None) == []

    def test_too_wide_or_tall(self):
        assert len(otp_inputs.bbox_warnings(BBox(10, 49.5, 13, 50.0), None)) == 1
        assert len(otp_inputs.bbox_warnings(BBox(19.5, 45, 20.0, 48), None)) == 1

    def test_exactly_two_degrees_is_fine(self):
        assert otp_inputs.bbox_warnings(BBox(19.0, 49.0, 21.0, 51.0), None) == []

    def test_outside_extract_bounds(self):
        warnings = otp_inputs.bbox_warnings(BBox(18.5, 49.5, 20.0, 50.0), self.EXTRACT)
        assert len(warnings) == 1 and "extract" in warnings[0]

    def test_both_warnings_can_be_reported(self):
        assert len(otp_inputs.bbox_warnings(BBox(10, 40, 15, 45), self.EXTRACT)) == 2

    def test_warnings_reach_report_file_and_command_output(self, env, server):
        # the fixture extract covers a tiny area, so the buffered stops bbox exceeds it
        out = StringIO()
        call_command("prepare_otp_inputs", "--city", CITY_ID, stdout=out)
        saved = json.loads((env.data / CITY_ID / "prepare-report.json").read_text())
        assert any("extract" in w for w in saved["warnings"])
        assert "warning:" in out.getvalue() and "extract" in out.getvalue()

    def test_huge_config_bbox_warns(self, env, server, monkeypatch):
        use_city(monkeypatch, make_city(otp=otp_section([10.0, 40.0, 20.0, 50.0])))
        report = prepare_city(CITY_ID)
        assert any("degrees" in w for w in report.warnings)


# ------------------------------------------------------------------- osm-file and paths


class TestOsmFileGuards:
    def test_osm_file_equal_to_output_is_rejected(self, env, server):
        prepare_city(CITY_ID, clip=False)
        output = env.data / CITY_ID / f"{CITY_ID}.osm.pbf"
        with pytest.raises(PrepareError, match="osm-file"):
            prepare_city(CITY_ID, clip=False, osm_file=output)

    def test_osm_file_equal_to_output_via_dotdot_path_is_rejected(self, env, server):
        prepare_city(CITY_ID, clip=False)
        output = env.data / CITY_ID / f"{CITY_ID}.osm.pbf"
        sneaky = output.parent / "cache" / ".." / output.name
        with pytest.raises(PrepareError, match="osm-file"):
            prepare_city(CITY_ID, clip=False, osm_file=sneaky)

    def test_output_file_is_untouched_after_rejection(self, env, server):
        prepare_city(CITY_ID, clip=False)
        output = env.data / CITY_ID / f"{CITY_ID}.osm.pbf"
        before = output.read_bytes()
        with pytest.raises(PrepareError):
            prepare_city(CITY_ID, clip=False, osm_file=output)
        assert output.read_bytes() == before

    def test_command_reports_rejection(self, env, server):
        output = env.data / CITY_ID / f"{CITY_ID}.osm.pbf"
        output.parent.mkdir(parents=True)
        shutil.copyfile(OSM_FIXTURE, output)
        with pytest.raises(CommandError, match="osm-file"):
            call_command("prepare_otp_inputs", "--city", CITY_ID, "--osm-file", str(output))

    def test_osmium_receives_absolute_paths(self):
        argv = otp_inputs.osmium_command(
            "osmium", Path("rel/in.pbf"), Path("rel/out.pbf"), BBox(19.9, 50.0, 20.0, 50.1)
        )
        assert Path(argv[argv.index("--output") + 1]).is_absolute()
        assert Path(argv[-1]).is_absolute()


# ----------------------------------------------------------------------------- lock


class TestCityLock:
    def lock_path(self, env):
        return env.data / CITY_ID / "cache" / "prepare.lock"

    def test_lock_is_released_after_success(self, env, server):
        prepare_city(CITY_ID, clip=False)
        assert not self.lock_path(env).exists()
        prepare_city(CITY_ID, clip=False)  # can run again

    def test_second_run_fails_fast_naming_holder_and_file(self, env, server):
        lock = self.lock_path(env)
        lock.parent.mkdir(parents=True)
        lock.write_text("pid 4242 on otphost since 2026-01-01T00:00:00+00:00\n")
        with pytest.raises(PrepareError) as err:
            prepare_city(CITY_ID, clip=False)
        assert "pid 4242" in str(err.value) and str(lock) in str(err.value)
        assert server.requests == []  # failed before any download
        assert lock.exists()  # a lock held by someone else is not removed

    def test_lock_is_released_on_prepare_error(self, env, server):
        server.bodies[URL_A] = urllib.error.URLError("down")
        with pytest.raises(PrepareError):
            prepare_city(CITY_ID, clip=False)
        assert not self.lock_path(env).exists()

    def test_lock_is_released_on_unexpected_exception(self, env, server, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(otp_inputs, "build_otp_configs", boom)
        with pytest.raises(RuntimeError):
            prepare_city(CITY_ID, clip=False)
        assert not self.lock_path(env).exists()

    def test_lock_file_records_pid_while_held(self, tmp_path):
        path = tmp_path / "l.lock"
        with otp_inputs.CityLock(path, "c"):
            assert f"pid {os.getpid()}" in path.read_text()
            with pytest.raises(PrepareError), otp_inputs.CityLock(path, "c"):
                pass
            assert path.exists()  # the failed second attempt did not release it
        assert not path.exists()

    def test_command_reports_lock_as_command_error(self, env, server):
        lock = self.lock_path(env)
        lock.parent.mkdir(parents=True)
        lock.write_text("pid 1 on h since t\n")
        with pytest.raises(CommandError, match="another"):
            call_command("prepare_otp_inputs", "--city", CITY_ID, "--no-clip")
