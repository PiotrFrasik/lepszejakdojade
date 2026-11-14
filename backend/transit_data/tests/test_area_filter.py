"""Area filter for large GTFS feeds (issue #43), against the miniature rail feed.

No network, no database. Expected numbers come from fixtures/gtfs/README.md.
"""

from __future__ import annotations

import csv
import io
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from transit_data.static_gtfs.area_filter import (
    AreaFilter,
    AreaFilterError,
    feed_area_filter,
    filter_feed,
)

from .gtfs_support import zip_directory

RAIL_AREA = Path(__file__).resolve().parent.parent / "fixtures" / "gtfs" / "rail_area"
BBOX = (19.80, 49.95, 20.10, 50.15)
AREA = AreaFilter(bbox=BBOX, exclude_agencies=frozenset({"SKM"}))
ST_HEAD = "trip_id,arrival_time,departure_time,stop_id,stop_sequence"
TIMED_AB = ST_HEAD + "\nT,08:00:00,08:00:00,A,0\nT,08:10:00,08:10:00,B,1\n"
TIMED_T1_T2 = (
    ST_HEAD
    + "\nT1,08:00:00,08:00:00,A,0\nT1,08:10:00,08:10:00,B,1"
    + "\nT2,08:00:00,08:00:00,A,0\nT2,08:10:00,08:10:00,C,1\n"
)
TIMED_ABC_DIST = (
    ST_HEAD
    + ",shape_dist_traveled\nT,08:00:00,08:00:00,A,0,\nT,08:10:00,08:10:00,B,1,"
    + "\nT,08:20:00,08:20:00,C,2,\n"
)


@pytest.fixture
def source(tmp_path) -> Path:
    path = tmp_path / "source.zip"
    path.write_bytes(zip_directory(RAIL_AREA))
    return path


def read_zip(path: Path) -> dict[str, list[dict[str, str]]]:
    tables = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            text = archive.read(name).decode("utf-8")
            tables[name] = list(csv.DictReader(io.StringIO(text)))
    return tables


@pytest.fixture
def result(source, tmp_path):
    target = tmp_path / "out.zip"
    stats = filter_feed(source, target, AREA)
    return SimpleNamespace(tables=read_zip(target), stats=stats, path=target)


def ids(rows, column):
    return [row[column] for row in rows]


def make_feed(tmp_path: Path, files: dict[str, str], name="custom") -> Path:
    """Write a synthetic feed (file name -> CSV text) and zip it."""
    directory = tmp_path / name
    directory.mkdir()
    for file_name, text in files.items():
        (directory / file_name).write_text(text, encoding="utf-8")
    path = tmp_path / f"{name}.zip"
    path.write_bytes(zip_directory(directory))
    return path


def mutated_rail_feed(tmp_path: Path, mutations: dict[str, str | None]) -> Path:
    """Copy rail_area, replace (text) or delete (None) files, return the zip path."""
    directory = tmp_path / "mutated"
    shutil.copytree(RAIL_AREA, directory)
    for name, text in mutations.items():
        if text is None:
            (directory / name).unlink()
        else:
            (directory / name).write_text(text, encoding="utf-8")
    path = tmp_path / "mutated.zip"
    path.write_bytes(zip_directory(directory))
    return path


# --------------------------------------------------------------- fixture expectations


def test_fixture_result_counts(result):
    t = result.tables
    assert len(t["agency.txt"]) == 2
    assert len(t["stops.txt"]) == 5
    assert len(t["routes.txt"]) == 2
    assert len(t["trips.txt"]) == 2
    assert len(t["stop_times.txt"]) == 5
    assert len(t["calendar.txt"]) == 2
    assert len(t["calendar_dates.txt"]) == 1
    assert len(t["shapes.txt"]) == 7
    assert len(t["transfers.txt"]) == 1


def test_kept_trips_and_dropped_reasons(result):
    assert sorted(ids(result.tables["trips.txt"], "trip_id")) == ["T_IC_1", "T_S1_1"]
    assert result.stats.trips_excluded_agency == 1  # T_SKM_1
    assert result.stats.trips_outside_area == 2  # T_IC_2 (one call), T_BUS_1 (none)


def test_without_exclusion_the_skm_trip_is_kept(source, tmp_path):
    target = tmp_path / "all.zip"
    filter_feed(source, target, AreaFilter(bbox=BBOX))
    trips = read_zip(target)["trips.txt"]
    assert sorted(ids(trips, "trip_id")) == ["T_IC_1", "T_S1_1", "T_SKM_1"]


def test_stops_include_parent_and_platform_without_coordinates(result):
    stops = {row["stop_id"]: row for row in result.tables["stops.txt"]}
    assert set(stops) == {"KGL", "KGL_1", "KGL_2", "KPL", "WIE"}
    assert stops["KGL_2"]["stop_lat"] == "" and stops["KGL_2"]["stop_lon"] == ""
    assert stops["KGL_2"]["parent_station"] == "KGL"


def test_unused_stop_inside_bbox_is_dropped(result):
    assert "UNUSED" not in ids(result.tables["stops.txt"], "stop_id")


def test_outside_stops_are_dropped(result):
    stops = set(ids(result.tables["stops.txt"], "stop_id"))
    assert not stops & {"KRZ", "TAR", "WAW"}


def test_trip_is_clipped_to_calls_inside_the_bbox(result):
    calls = [(row["trip_id"], row["stop_id"]) for row in result.tables["stop_times.txt"]]
    assert sorted(calls) == [
        ("T_IC_1", "KGL_2"),
        ("T_IC_1", "KPL"),
        ("T_S1_1", "KGL_1"),
        ("T_S1_1", "KPL"),
        ("T_S1_1", "WIE"),
    ]


def test_clipped_trip_keeps_real_destination_headsign(result):
    trips = {row["trip_id"]: row for row in result.tables["trips.txt"]}
    assert trips["T_IC_1"]["trip_headsign"] == "Tarnów"


def test_clipped_stop_times_keep_original_times_and_sequences(result):
    rows = {(r["trip_id"], r["stop_id"]): r for r in result.tables["stop_times.txt"]}
    first = rows[("T_IC_1", "KGL_2")]
    assert first["departure_time"] == "08:35:00"
    assert first["stop_sequence"] == "1"


def test_unused_routes_agencies_and_services_are_dropped(result):
    assert sorted(ids(result.tables["routes.txt"], "route_id")) == ["IC_IC", "KML_S1"]
    assert sorted(ids(result.tables["agency.txt"], "agency_id")) == ["IC", "KML"]
    assert sorted(ids(result.tables["calendar.txt"], "service_id")) == ["DAILY", "WD"]
    assert ids(result.tables["calendar_dates.txt"], "service_id") == ["WD"]


def test_shape_is_clipped_with_one_point_on_each_side(result):
    shapes = result.tables["shapes.txt"]
    ic = [r for r in shapes if r["shape_id"] == "SH_IC"]
    assert [r["shape_pt_sequence"] for r in ic] == ["1", "2", "3", "4"]
    assert [r["shape_dist_traveled"] for r in ic] == ["150.0", "290.0", "295.0", "320.0"]
    assert len([r for r in shapes if r["shape_id"] == "SH_S1"]) == 3
    assert "SH_BUS" not in ids(shapes, "shape_id")
    assert result.stats.shapes_clipped >= 1


def test_only_transfer_between_kept_stops_and_trips_remains(result):
    (transfer,) = result.tables["transfers.txt"]
    assert (transfer["from_stop_id"], transfer["to_stop_id"]) == ("KGL_2", "KGL_1")
    assert (transfer["from_trip_id"], transfer["to_trip_id"]) == ("T_IC_1", "T_S1_1")


def test_feed_info_and_attributions_are_copied_unchanged(result):
    for name in ("feed_info.txt", "attributions.txt"):
        original = list(csv.DictReader((RAIL_AREA / name).open(encoding="utf-8", newline="")))
        assert result.tables[name] == original


def test_kept_rows_keep_every_column(result):
    header = (RAIL_AREA / "routes.txt").read_text(encoding="utf-8").splitlines()[0]
    assert list(result.tables["routes.txt"][0]) == header.split(",")


def test_output_is_self_consistent(result):
    t = result.tables
    stop_ids = set(ids(t["stops.txt"], "stop_id"))
    trip_ids = set(ids(t["trips.txt"], "trip_id"))
    assert set(ids(t["stop_times.txt"], "stop_id")) <= stop_ids
    assert set(ids(t["stop_times.txt"], "trip_id")) == trip_ids
    assert set(ids(t["trips.txt"], "route_id")) == set(ids(t["routes.txt"], "route_id"))
    assert set(ids(t["trips.txt"], "service_id")) <= set(ids(t["calendar.txt"], "service_id"))
    assert set(ids(t["routes.txt"], "agency_id")) == set(ids(t["agency.txt"], "agency_id"))
    for stop in t["stops.txt"]:
        if stop["parent_station"]:
            assert stop["parent_station"] in stop_ids


def test_statistics_report(result):
    stats = result.stats.as_dict()
    assert stats["config"] == {
        "bbox": [19.8, 49.95, 20.1, 50.15],
        "exclude_agencies": ["SKM"],
        "min_stops_in_area": 2,
    }
    assert stats["files"]["trips.txt"] == {"read": 5, "kept": 2}
    assert stats["files"]["stop_times.txt"] == {"read": 14, "kept": 5}
    assert stats["trips_excluded_agency"] == 1
    assert stats["trips_outside_area"] == 2


# ----------------------------------------------------------------------- determinism


def test_output_is_byte_identical_for_same_input(source, tmp_path):
    first, second = tmp_path / "a.zip", tmp_path / "b.zip"
    filter_feed(source, first, AREA)
    filter_feed(source, second, AREA)
    assert first.read_bytes() == second.read_bytes()


def test_output_does_not_depend_on_archive_member_order(tmp_path):
    names = sorted(p.name for p in RAIL_AREA.iterdir())
    paths = []
    for label, order in (("fwd", names), ("rev", names[::-1])):
        path = tmp_path / f"{label}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in order:
                archive.write(RAIL_AREA / name, name)
        paths.append(path)
    outputs = []
    for i, path in enumerate(paths):
        out = tmp_path / f"out{i}.zip"
        filter_feed(path, out, AREA)
        outputs.append(read_zip(out))
    assert outputs[0] == outputs[1]


def test_filtered_output_is_itself_a_valid_input(result, tmp_path):
    again = tmp_path / "again.zip"
    filter_feed(result.path, again, AREA)
    assert read_zip(again) == result.tables


# --------------------------------------------------------------------- edge behaviour


def test_stop_without_coordinates_uses_parent_station_position(source, tmp_path):
    # Only KGL_2 (no coordinates, parent KGL in the bbox) and KPL serve T_IC_1 in the area.
    target = tmp_path / "out.zip"
    filter_feed(source, target, AREA)
    assert "KGL_2" in ids(read_zip(target)["stops.txt"], "stop_id")


def test_bbox_edges_are_inclusive(tmp_path):
    feed = make_feed(
        tmp_path,
        {
            "stops.txt": "stop_id,stop_lat,stop_lon\nA,50.0,19.0\nB,50.0,20.0\n",
            "routes.txt": "route_id,agency_id,route_type\nR,X,2\n",
            "trips.txt": "route_id,service_id,trip_id\nR,S,T\n",
            "stop_times.txt": TIMED_AB,
        },
    )
    target = tmp_path / "out.zip"
    stats = filter_feed(feed, target, AreaFilter(bbox=(19.0, 50.0, 20.0, 50.0 + 1e-9)))
    assert stats.rows_kept["stop_times.txt"] == 2


def test_trip_with_one_call_inside_is_dropped(source, tmp_path):
    # T_IC_2 has exactly one call inside; making a second stop usable keeps it.
    target = tmp_path / "out.zip"
    filter_feed(source, target, AREA)
    assert "T_IC_2" not in ids(read_zip(target)["trips.txt"], "trip_id")


def test_wider_bbox_keeps_more_trips(source, tmp_path):
    target = tmp_path / "wide.zip"
    wide = AreaFilter(bbox=(19.0, 49.0, 21.5, 52.5), exclude_agencies=frozenset({"SKM"}))
    filter_feed(source, target, wide)
    trips = ids(read_zip(target)["trips.txt"], "trip_id")
    assert sorted(trips) == ["T_BUS_1", "T_IC_1", "T_IC_2", "T_S1_1"]


def test_shape_without_distances_is_kept_whole(tmp_path):
    feed = make_feed(
        tmp_path,
        {
            "stops.txt": "stop_id,stop_lat,stop_lon\nA,50.0,19.5\nB,50.1,19.6\nC,60.0,30.0\n",
            "routes.txt": "route_id,agency_id,route_type\nR,X,2\n",
            "trips.txt": "route_id,service_id,trip_id,shape_id\nR,S,T,SH\n",
            "stop_times.txt": TIMED_ABC_DIST,
            "shapes.txt": (
                "shape_id,shape_pt_sequence,shape_pt_lat,shape_pt_lon\n"
                "SH,0,50.0,19.5\nSH,1,50.1,19.6\nSH,2,60.0,30.0\n"
            ),
        },
    )
    target = tmp_path / "out.zip"
    filter_feed(feed, target, AreaFilter(bbox=(19.0, 49.0, 20.0, 51.0)))
    assert len(read_zip(target)["shapes.txt"]) == 3


def test_frequencies_follow_kept_trips(tmp_path):
    feed = make_feed(
        tmp_path,
        {
            "stops.txt": "stop_id,stop_lat,stop_lon\nA,50.0,19.5\nB,50.1,19.6\nC,60.0,30.0\n",
            "routes.txt": "route_id,agency_id,route_type\nR,X,2\n",
            "trips.txt": "route_id,service_id,trip_id\nR,S,T1\nR,S,T2\n",
            "stop_times.txt": TIMED_T1_T2,
            "frequencies.txt": (
                "trip_id,start_time,end_time,headway_secs\nT1,06:00:00,09:00:00,600\n"
                "T2,06:00:00,09:00:00,600\n"
            ),
        },
    )
    target = tmp_path / "out.zip"
    filter_feed(feed, target, AreaFilter(bbox=(19.0, 49.0, 20.0, 51.0)))
    assert ids(read_zip(target)["frequencies.txt"], "trip_id") == ["T1"]


def test_after_midnight_times_are_preserved(tmp_path):
    feed = make_feed(
        tmp_path,
        {
            "stops.txt": "stop_id,stop_lat,stop_lon\nA,50.0,19.5\nB,50.1,19.6\n",
            "routes.txt": "route_id,agency_id,route_type\nR,X,2\n",
            "trips.txt": "route_id,service_id,trip_id\nR,S,T\n",
            "stop_times.txt": (
                "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                "T,23:50:00,23:51:00,A,0\nT,24:10:00,24:11:00,B,1\n"
            ),
        },
    )
    target = tmp_path / "out.zip"
    filter_feed(feed, target, AreaFilter(bbox=(19.0, 49.0, 20.0, 51.0)))
    assert ids(read_zip(target)["stop_times.txt"], "arrival_time") == ["23:50:00", "24:10:00"]


def test_other_files_are_dropped_and_reported(source, tmp_path):
    extra = mutated_rail_feed(tmp_path, {})
    with zipfile.ZipFile(extra, "a") as archive:
        archive.writestr("fare_attributes.txt", "fare_id,price\nF,1\n")
    target = tmp_path / "out.zip"
    stats = filter_feed(extra, target, AREA)
    assert "fare_attributes.txt" not in read_zip(target)
    assert stats.dropped_files == ["fare_attributes.txt"]


def test_agency_without_agency_id_column_is_kept(tmp_path):
    feed = make_feed(
        tmp_path,
        {
            "agency.txt": "agency_name,agency_url,agency_timezone\nOnly,https://x.example/,UTC\n",
            "stops.txt": "stop_id,stop_lat,stop_lon\nA,50.0,19.5\nB,50.1,19.6\n",
            "routes.txt": "route_id,route_type\nR,2\n",
            "trips.txt": "route_id,service_id,trip_id\nR,S,T\n",
            "stop_times.txt": TIMED_AB,
        },
    )
    target = tmp_path / "out.zip"
    filter_feed(feed, target, AreaFilter(bbox=(19.0, 49.0, 20.0, 51.0)))
    assert len(read_zip(target)["agency.txt"]) == 1


# ------------------------------------------------------------------------- errors


def test_empty_result_raises(source, tmp_path):
    target = tmp_path / "out.zip"
    nowhere = AreaFilter(bbox=(0.0, 0.0, 1.0, 1.0))
    with pytest.raises(AreaFilterError, match="no trip"):
        filter_feed(source, target, nowhere)


def test_excluding_every_agency_raises(source, tmp_path):
    everyone = AreaFilter(bbox=BBOX, exclude_agencies=frozenset({"KML", "IC", "SKM"}))
    with pytest.raises(AreaFilterError):
        filter_feed(source, tmp_path / "out.zip", everyone)


@pytest.mark.parametrize("missing", ["stops.txt", "routes.txt", "trips.txt", "stop_times.txt"])
def test_missing_required_file_raises(tmp_path, missing):
    feed = mutated_rail_feed(tmp_path, {missing: None})
    with pytest.raises(AreaFilterError, match=missing):
        filter_feed(feed, tmp_path / "out.zip", AREA)


def test_not_a_zip_raises_a_format_error(tmp_path):
    from transit_data.static_gtfs.reader import GtfsFormatError

    path = tmp_path / "bad.zip"
    path.write_bytes(b"not a zip at all")
    with pytest.raises(GtfsFormatError):
        filter_feed(path, tmp_path / "out.zip", AREA)


# --------------------------------------------------------------- AreaFilter.from_config


def test_from_config_none_is_none():
    assert AreaFilter.from_config(None) is None


def test_from_config_mapping():
    area = AreaFilter.from_config({"bbox": [19, 49, 20, 50], "exclude_agencies": [" SKM "]})
    assert area == AreaFilter(bbox=(19.0, 49.0, 20.0, 50.0), exclude_agencies=frozenset({"SKM"}))


def test_from_config_object_with_attributes():
    raw = SimpleNamespace(bbox=(19, 49, 20, 50), exclude_agencies=("SKM",))
    assert AreaFilter.from_config(raw).exclude_agencies == frozenset({"SKM"})


def test_from_config_without_exclusions():
    assert AreaFilter.from_config({"bbox": [19, 49, 20, 50]}).exclude_agencies == frozenset()


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"bbox": None},
        {"bbox": [19, 49, 20]},
        {"bbox": [19, 49, 20, 50, 51]},
        {"bbox": ["a", 49, 20, 50]},
        {"bbox": [19, 49, float("nan"), 50]},
        {"bbox": [19, 49, float("inf"), 50]},
        {"bbox": [20, 49, 19, 50]},
        {"bbox": [19, 50, 20, 49]},
        {"bbox": [19, 49, 20, 91]},
        {"bbox": [-181, 49, 20, 50]},
        {"bbox": [19, 49, 20, 50], "exclude_agencies": "SKM"},
        {"bbox": [19, 49, 20, 50], "exclude_agencies": [1]},
    ],
)
def test_from_config_invalid(raw):
    with pytest.raises(AreaFilterError):
        AreaFilter.from_config(raw)


def test_feed_area_filter_reads_the_feed_attribute():
    feed = SimpleNamespace(filter=SimpleNamespace(bbox=BBOX, exclude_agencies=()))
    assert feed_area_filter(feed) == AreaFilter(bbox=BBOX)
    assert feed_area_filter(SimpleNamespace(filter=None)) is None
    assert feed_area_filter(SimpleNamespace()) is None


def test_contains_is_lat_lon_ordered():
    area = AreaFilter(bbox=BBOX)
    assert area.contains(50.0, 19.9)
    assert not area.contains(19.9, 50.0)


def test_as_dict_is_stable_for_equal_filters():
    a = AreaFilter(bbox=BBOX, exclude_agencies=frozenset({"B", "A"}))
    b = AreaFilter(bbox=BBOX, exclude_agencies=frozenset({"A", "B"}))
    assert a.as_dict() == b.as_dict()
    assert a.as_dict()["exclude_agencies"] == ["A", "B"]


# ------------------------------------------------------------ timed calls and clipping


FREE_AREA = AreaFilter(bbox=(19.0, 49.0, 20.0, 51.0))
GOOD_TRIP = "G,08:00:00,08:00:00,A,0\nG,08:10:00,08:10:00,B,1\n"  # a trip that is always kept


def timed_feed(tmp_path: Path, rows: str, agencies=None, routes=None) -> Path:
    """Feed with inside stops A..D, E (also inside), O (outside) and the given stop_times rows
    (``trip,arrival,departure,stop,seq`` lines)."""
    files = {
        "stops.txt": (
            "stop_id,stop_lat,stop_lon\nA,50.0,19.1\nB,50.0,19.2\nC,50.0,19.3\n"
            "D,50.0,19.4\nE,50.0,19.5\nO,10.0,10.0\n"
        ),
        "routes.txt": routes or "route_id,agency_id,route_type\nR,X,2\n",
        "trips.txt": "route_id,service_id,trip_id\nR,S,T\nR,S,G\n",
        "stop_times.txt": ST_HEAD + "\n" + rows,
    }
    if agencies:
        files["agency.txt"] = agencies
    return make_feed(tmp_path, files)


def kept_calls(path: Path, trip: str) -> list[tuple[str, str]]:
    rows = read_zip(path)["stop_times.txt"]
    return [(r["stop_sequence"], r["stop_id"]) for r in rows if r["trip_id"] == trip]


def run_timed(tmp_path: Path, rows: str) -> Path:
    target = tmp_path / "out.zip"
    filter_feed(timed_feed(tmp_path, rows + GOOD_TRIP), target, FREE_AREA)
    return target


def test_untimed_calls_at_the_ends_are_dropped_and_between_are_kept(tmp_path):
    rows = "T,,,A,0\nT,08:00:00,08:00:00,B,1\nT,,,C,2\nT,08:20:00,08:20:00,D,3\nT,,,E,4\n"
    out = run_timed(tmp_path, rows)
    assert kept_calls(out, "T") == [("1", "B"), ("2", "C"), ("3", "D")]


def test_calls_outside_the_area_between_timed_calls_are_not_kept(tmp_path):
    rows = "T,08:00:00,08:00:00,A,0\nT,08:05:00,08:05:00,O,1\nT,08:10:00,08:10:00,B,2\n"
    out = run_timed(tmp_path, rows)
    assert kept_calls(out, "T") == [("0", "A"), ("2", "B")]


@pytest.mark.parametrize("timing", ["08:00:00,", ",08:00:00"], ids=["arrival", "departure"])
def test_a_call_with_only_arrival_or_only_departure_is_timed(tmp_path, timing):
    rows = f"T,{timing},A,0\nT,{timing},B,1\n"
    out = run_timed(tmp_path, rows)
    assert kept_calls(out, "T") == [("0", "A"), ("1", "B")]


def test_only_timed_inside_calls_count_towards_the_minimum(tmp_path):
    # Three inside calls but only one of them timed: the trip is not ridden in the area.
    rows = "T,,,A,0\nT,08:00:00,08:00:00,B,1\nT,,,C,2\n"
    out = run_timed(tmp_path, rows)
    assert kept_calls(out, "T") == []
    assert kept_calls(out, "G") != []


def test_trip_with_two_timed_inside_calls_is_kept(tmp_path):
    rows = "T,08:00:00,08:00:00,A,0\nT,08:10:00,08:10:00,B,1\n"
    assert len(kept_calls(run_timed(tmp_path, rows), "T")) == 2


def test_unparseable_stop_sequence_is_dropped_and_not_counted(tmp_path):
    rows = "T,08:00:00,08:00:00,A,0\nT,08:10:00,08:10:00,B,x\n"
    out = run_timed(tmp_path, rows)
    assert kept_calls(out, "T") == []  # one valid timed call left: below the minimum


def test_unparseable_stop_sequence_row_is_not_written_for_a_kept_trip(tmp_path):
    rows = "T,08:00:00,08:00:00,A,0\nT,08:10:00,08:10:00,B,1\nT,08:20:00,08:20:00,C,\n"
    out = run_timed(tmp_path, rows)
    assert kept_calls(out, "T") == [("0", "A"), ("1", "B")]


def test_empty_result_message_mentions_timed_calls_and_bbox(tmp_path):
    feed = timed_feed(tmp_path, "T,,,A,0\nT,,,B,1\nG,08:00:00,08:00:00,A,0\n")
    with pytest.raises(AreaFilterError) as error:
        filter_feed(feed, tmp_path / "out.zip", FREE_AREA)
    assert str(error.value) == (
        "no trip has at least 2 timed calls inside bbox [19.0, 49.0, 20.0, 51.0]"
    )


# ---------------------------------------------------------------------- agency.txt


TWO_AGENCIES = "agency_id,agency_name\nX,Operator X\nY,Operator Y\n"
THREE_AGENCIES = "agency_id,agency_name\nX,Operator X\nY,Operator Y\nZ,Operator Z\n"


def agencies_kept(tmp_path, agencies, routes) -> list[dict]:
    feed = timed_feed(
        tmp_path,
        GOOD_TRIP + "T,08:00:00,08:00:00,C,0\nT,08:10:00,08:10:00,D,1\n",
        agencies=agencies,
        routes=routes,
    )
    target = tmp_path / "out.zip"
    filter_feed(feed, target, FREE_AREA)
    return read_zip(target)["agency.txt"]


def test_all_agencies_are_kept_without_an_agency_id_column(tmp_path):
    agencies = "agency_name,agency_url,agency_timezone\nA,https://a.example/,UTC\nB,https://b.example/,UTC\n"
    kept = agencies_kept(tmp_path, agencies, "route_id,route_type\nR,2\n")
    assert [row["agency_name"] for row in kept] == ["A", "B"]


def test_single_agency_is_kept_even_if_routes_name_another_id(tmp_path):
    kept = agencies_kept(
        tmp_path, "agency_id,agency_name\nX,Only\n", "route_id,agency_id,route_type\nR,OTHER,2\n"
    )
    assert [row["agency_id"] for row in kept] == ["X"]


def test_all_agencies_are_kept_when_a_kept_route_has_a_blank_agency_id(tmp_path):
    kept = agencies_kept(tmp_path, TWO_AGENCIES, "route_id,agency_id,route_type\nR,,2\n")
    assert [row["agency_id"] for row in kept] == ["X", "Y"]


def test_only_used_agencies_are_kept_otherwise(tmp_path):
    kept = agencies_kept(tmp_path, THREE_AGENCIES, "route_id,agency_id,route_type\nR,Y,2\n")
    assert [row["agency_id"] for row in kept] == ["Y"]


# ------------------------------------------------------------ uncompressed size limit


def test_oversized_archive_is_rejected_with_a_format_error(source, tmp_path):
    from transit_data.static_gtfs.reader import GtfsFormatError

    with pytest.raises(GtfsFormatError, match="exceeds the limit"):
        filter_feed(source, tmp_path / "out.zip", AREA, max_uncompressed_bytes=10)


def test_archive_within_the_limit_is_filtered(source, tmp_path):
    filter_feed(source, tmp_path / "out.zip", AREA, max_uncompressed_bytes=10_000_000)
    assert (tmp_path / "out.zip").is_file()
