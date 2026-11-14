"""Stops without usable coordinates inherit the nearest positioned ancestor's position.

Covers the loader and its agreement with the area filter (issue #43). No network.
"""

from __future__ import annotations

import csv
import io
import zipfile

import pytest

from transit_data.models import FeedVersion, Stop
from transit_data.static_gtfs.area_filter import AreaFilter, filter_feed
from transit_data.static_gtfs.pipeline import Outcome, import_city

from .gtfs_support import CITY, FEED, copy_feed, zip_directory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("gtfs_city")]


@pytest.fixture(autouse=True)
def tolerate_skipped_stops(settings):
    settings.TRANSIT_GTFS_MAX_SKIPPED_RATIO = 0.5


CORRECTION = "missing or invalid coordinates, used the parent station's"
HEADER = "stop_id,stop_code,stop_name,stop_lat,stop_lon,location_type,parent_station"
TIMED_PLAT = (
    "trip_id,arrival_time,departure_time,stop_id,stop_sequence"
    "\nT,08:00:00,08:00:00,PLAT,0\nT,08:10:00,08:10:00,STATION,1\n"
)


def stops_feed(tmp_path, rows: list[str]):
    """The minimal fixture feed with extra stops (unused by stop_times) appended."""
    extra = "".join(f"{row}\n" for row in rows)
    return copy_feed(tmp_path / "feed", {"stops.txt": lambda text: text + extra})


def stop_row(stop_id, lat="", lon="", parent="", location_type="0"):
    # the minimal fixture's columns: id, code, name, lat, lon, type, parent, wheelchair, platform
    return f"{stop_id},,Name {stop_id},{lat},{lon},{location_type},{parent},,"


def run(path):
    (result,) = import_city(CITY, FEED, file=path)
    assert result.outcome == Outcome.IMPORTED, result.message
    return FeedVersion.objects.get(pk=result.feed_version_id)


def point_of(version, gtfs_id):
    return Stop.objects.get(feed_version=version, gtfs_id=gtfs_id).point


def test_platform_listed_before_its_parent_inherits_the_position(tmp_path):
    feed = stops_feed(
        tmp_path,
        [
            stop_row("PLAT", parent="STATION"),
            stop_row("STATION", "50.5", "19.5", location_type="1"),
        ],
    )
    version = run(feed)
    point = point_of(version, "PLAT")
    assert (point.x, point.y) == (pytest.approx(19.5), pytest.approx(50.5))


def test_grandparent_position_is_inherited_through_a_positionless_parent(tmp_path):
    feed = stops_feed(
        tmp_path,
        [
            stop_row("PLAT", parent="ENTRANCE_AREA"),
            stop_row("ENTRANCE_AREA", parent="STATION", location_type="2"),
            stop_row("STATION", "50.5", "19.5", location_type="1"),
        ],
    )
    version = run(feed)
    for stop_id in ("PLAT", "ENTRANCE_AREA"):
        point = point_of(version, stop_id)
        assert (point.x, point.y) == (pytest.approx(19.5), pytest.approx(50.5))


def test_nearest_positioned_ancestor_wins(tmp_path):
    feed = stops_feed(
        tmp_path,
        [
            stop_row("PLAT", parent="MID"),
            stop_row("MID", "50.2", "19.2", parent="TOP", location_type="1"),
            stop_row("TOP", "50.9", "19.9", location_type="1"),
        ],
    )
    point = point_of(run(feed), "PLAT")
    assert (point.x, point.y) == (pytest.approx(19.2), pytest.approx(50.2))


def test_own_coordinates_are_not_overridden(tmp_path):
    feed = stops_feed(
        tmp_path,
        [
            stop_row("PLAT", "50.1", "19.1", parent="STATION"),
            stop_row("STATION", "50.5", "19.5", location_type="1"),
        ],
    )
    point = point_of(run(feed), "PLAT")
    assert (point.x, point.y) == (pytest.approx(19.1), pytest.approx(50.1))


def test_parent_cycle_does_not_hang_and_the_stops_are_skipped(tmp_path):
    feed = stops_feed(
        tmp_path,
        [stop_row("CYC_A", parent="CYC_B"), stop_row("CYC_B", parent="CYC_A")],
    )
    version = run(feed)
    assert not Stop.objects.filter(feed_version=version, gtfs_id__in=["CYC_A", "CYC_B"]).exists()
    assert version.report["files"]["stops.txt"]["skipped"] == 2


def test_self_parent_is_skipped(tmp_path):
    version = run(stops_feed(tmp_path, [stop_row("SELF", parent="SELF")]))
    assert not Stop.objects.filter(feed_version=version, gtfs_id="SELF").exists()


def test_orphan_stop_without_coordinates_is_still_skipped(tmp_path):
    feed = stops_feed(tmp_path, [stop_row("ORPHAN"), stop_row("LOST", parent="NOWHERE")])
    version = run(feed)
    assert not Stop.objects.filter(feed_version=version, gtfs_id__in=["ORPHAN", "LOST"]).exists()
    stats = version.report["files"]["stops.txt"]
    assert stats["skipped"] == 2
    assert stats["skip_reasons"] == {"missing or invalid coordinates": 2}


def test_each_inheritance_is_counted_as_a_correction(tmp_path):
    feed = stops_feed(
        tmp_path,
        [
            stop_row("P1", parent="STATION"),
            stop_row("P2", parent="STATION"),
            stop_row("STATION", "50.5", "19.5", location_type="1"),
        ],
    )
    version = run(feed)
    assert version.report["files"]["stops.txt"]["corrections"] == {CORRECTION: 2}


def test_feed_without_inheritance_has_no_such_correction(tmp_path):
    version = run(copy_feed(tmp_path / "plain"))
    corrections = version.report["files"]["stops.txt"].get("corrections") or {}
    assert CORRECTION not in corrections


@pytest.mark.parametrize(
    "lat,lon", [("0", "0"), ("0.0", "0.0"), ("95", "19.5"), ("50.5", "200"), ("abc", "19.5")]
)
def test_invalid_own_coordinates_fall_back_to_the_parent(tmp_path, lat, lon):
    feed = stops_feed(
        tmp_path,
        [
            stop_row("PLAT", lat, lon, parent="STATION"),
            stop_row("STATION", "50.5", "19.5", location_type="1"),
        ],
    )
    version = run(feed)
    point = point_of(version, "PLAT")
    assert (point.x, point.y) == (pytest.approx(19.5), pytest.approx(50.5))


@pytest.mark.parametrize("lat,lon", [("0", "0"), ("95", "19.5"), ("50.5", "200"), ("", "")])
def test_area_filter_and_loader_agree_on_unusable_coordinates(tmp_path, lat, lon):
    # A platform with unusable coordinates sits under a parent inside the bbox: both the
    # loader and the filter must treat it as being at the parent's position.
    rows = [
        stop_row("PLAT", lat, lon, parent="STATION"),
        stop_row("STATION", "50.5", "19.5", location_type="1"),
    ]
    stops = f"{HEADER},wheelchair_boarding,platform_code\n" + "\n".join(rows) + "\n"
    feed = {
        "stops.txt": stops,
        "routes.txt": "route_id,agency_id,route_type\nR,A,2\n",
        "trips.txt": "route_id,service_id,trip_id\nR,S,T\n",
        "stop_times.txt": TIMED_PLAT,
    }
    directory = tmp_path / "areafeed"
    directory.mkdir()
    for name, text in feed.items():
        (directory / name).write_text(text, encoding="utf-8")
    source = tmp_path / "areafeed.zip"
    source.write_bytes(zip_directory(directory))
    target = tmp_path / "out.zip"
    stats = filter_feed(source, target, AreaFilter(bbox=(19.0, 50.0, 20.0, 51.0)))
    assert stats.rows_kept["stop_times.txt"] == 2  # PLAT counted inside via its parent
    with zipfile.ZipFile(target) as archive:
        kept = {
            r["stop_id"] for r in csv.DictReader(io.StringIO(archive.read("stops.txt").decode()))
        }
    assert kept == {"PLAT", "STATION"}

    # The loader gives the same platform the same position.
    loader_feed = stops_feed(tmp_path, rows)
    point = point_of(run(loader_feed), "PLAT")
    assert (point.x, point.y) == (pytest.approx(19.5), pytest.approx(50.5))


def test_area_filter_drops_a_platform_whose_parent_is_outside(tmp_path):
    rows = [
        stop_row("PLAT", "0", "0", parent="STATION"),
        stop_row("STATION", "10.0", "10.0", location_type="1"),
    ]
    stops = f"{HEADER},wheelchair_boarding,platform_code\n" + "\n".join(rows) + "\n"
    directory = tmp_path / "f"
    directory.mkdir()
    files = {
        "stops.txt": stops,
        "routes.txt": "route_id,agency_id,route_type\nR,A,2\n",
        "trips.txt": "route_id,service_id,trip_id\nR,S,T\n",
        "stop_times.txt": TIMED_PLAT,
    }
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")
    source = tmp_path / "f.zip"
    source.write_bytes(zip_directory(directory))
    from transit_data.static_gtfs.area_filter import AreaFilterError

    with pytest.raises(AreaFilterError):
        filter_feed(source, tmp_path / "o.zip", AreaFilter(bbox=(19.0, 50.0, 20.0, 51.0)))
