"""Static GTFS import: fixture feed, idempotency, version rotation, failure handling."""

from __future__ import annotations

from datetime import date

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from transit_data.models import (
    Agency,
    Calendar,
    CalendarDate,
    FeedVersion,
    Frequency,
    Route,
    Shape,
    Stop,
    StopTime,
    Trip,
)
from transit_data.static_gtfs.pipeline import ImportConfigError, Outcome, import_city

from .gtfs_support import CITY, FEED, copy_feed, replace_in, zip_directory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("gtfs_city")]


def run(path, force=False, feed=FEED):
    (result,) = import_city(CITY, feed, force=force, file=path)
    return result


@pytest.fixture
def feed_dir(tmp_path):
    return copy_feed(tmp_path / "feed")


@pytest.fixture
def imported(feed_dir):
    result = run(feed_dir)
    assert result.outcome == Outcome.IMPORTED, result.message
    return FeedVersion.objects.get(pk=result.feed_version_id)


def bad_stop_times(tmp_path, name="bad"):
    """Two of the 13 stop_times rows reference an unknown stop (15% > the 5% limit)."""

    def transform(text):
        text = text.replace(
            "T1_WD_0800,08:00:00,08:00:00,ST1_A", "T1_WD_0800,08:00:00,08:00:00,NOPE"
        )
        return text.replace("T1_WE_0900,09:00:00,09:00:00,S4", "T1_WE_0900,09:00:00,09:00:00,NOPE2")

    return copy_feed(tmp_path / name, {"stop_times.txt": transform})


# ------------------------------------------------------------------ fixture import


def test_fixture_import_row_counts(imported):
    assert imported.status == FeedVersion.Status.ACTIVE
    for model, expected in (
        (Agency, 1),
        (Stop, 6),
        (Route, 2),
        (Calendar, 2),
        (CalendarDate, 2),
        (Shape, 1),
        (Trip, 4),
        (StopTime, 13),
        (Frequency, 1),
    ):
        assert model.objects.filter(feed_version=imported).count() == expected, model
    assert imported.report["counts"] == {
        "agencies": 1,
        "stops": 6,
        "routes": 2,
        "calendars": 2,
        "calendar_dates": 2,
        "shapes": 1,
        "trips": 4,
        "stop_times": 13,
        "frequencies": 1,
    }


def test_fixture_import_feed_version_metadata(imported):
    assert imported.city_id == CITY
    assert imported.feed_id == FEED
    assert imported.sha256
    assert imported.source_url.startswith("file:")
    assert imported.publisher_name == "Testville Transit"
    assert imported.feed_info_version == "fixture-1"
    assert imported.error == ""
    assert imported.imported_at is not None


def test_service_range_comes_from_calendar(imported):
    assert imported.service_start_date == date(2026, 1, 1)
    assert imported.service_end_date == date(2028, 12, 31)


def test_times_past_midnight_are_seconds_beyond_86400(imported):
    trip = Trip.objects.get(feed_version=imported, gtfs_id="T1_WD_2350")
    times = {st.stop.gtfs_id: st for st in StopTime.objects.filter(trip=trip)}
    assert times["S3"].arrival_time == 86640  # 24:04:00
    assert times["S4"].arrival_time == 87000  # 24:10:00
    assert times["S4"].departure_time == 87000
    assert times["S2"].arrival_time == 23 * 3600 + 58 * 60 + 30
    assert times["S2"].departure_time == 23 * 3600 + 59 * 60


def test_one_digit_hour_is_parsed(imported):
    trip = Trip.objects.get(feed_version=imported, gtfs_id="T1_WE_0900")
    st = StopTime.objects.get(trip=trip, stop__gtfs_id="S2")
    assert st.arrival_time == 9 * 3600 + 12 * 60


def test_arrival_and_departure_may_differ(imported):
    trip = Trip.objects.get(feed_version=imported, gtfs_id="T1_WD_0800")
    st = StopTime.objects.get(trip=trip, stop_sequence=2)
    assert st.arrival_time == 8 * 3600 + 5 * 60
    assert st.departure_time == 8 * 3600 + 6 * 60


def test_stop_without_times_is_stored_with_null_times(imported):
    trip = Trip.objects.get(feed_version=imported, gtfs_id="T1_WD_0800")
    st = StopTime.objects.get(trip=trip, stop_sequence=3)
    assert st.arrival_time is None
    assert st.departure_time is None
    assert st.stop.gtfs_id == "S3"


def test_stop_times_keep_pickup_drop_off_and_distance(imported):
    trip = Trip.objects.get(feed_version=imported, gtfs_id="T1_WD_0800")
    first = StopTime.objects.get(trip=trip, stop_sequence=1)
    last = StopTime.objects.get(trip=trip, stop_sequence=4)
    assert (first.pickup_type, first.drop_off_type) == (0, 1)
    assert (last.pickup_type, last.drop_off_type) == (1, 0)
    assert last.shape_dist_traveled == pytest.approx(3.1)
    assert StopTime.objects.get(trip=trip, stop_sequence=3).shape_dist_traveled is None


def test_parent_station_is_linked(imported):
    station = Stop.objects.get(feed_version=imported, gtfs_id="ST1")
    platform_a = Stop.objects.get(feed_version=imported, gtfs_id="ST1_A")
    platform_b = Stop.objects.get(feed_version=imported, gtfs_id="ST1_B")
    assert station.location_type == 1
    assert station.parent_station is None
    assert platform_a.parent_station_id == station.pk
    assert platform_b.parent_station_id == station.pk
    assert {s.gtfs_id for s in station.children.all()} == {"ST1_A", "ST1_B"}
    assert platform_a.platform_code == "A"
    assert platform_a.code == "101"


def test_stop_values(imported):
    stop = Stop.objects.get(feed_version=imported, gtfs_id="S3")
    assert stop.name == "Łąkowa Street"
    assert stop.city_id == CITY
    assert stop.wheelchair_boarding == 0  # empty in the feed -> unknown
    assert stop.point.x == pytest.approx(19.9600)
    assert stop.point.y == pytest.approx(50.0480)
    assert Stop.objects.get(feed_version=imported, gtfs_id="ST1_B").wheelchair_boarding == 2


def test_shape_points_are_ordered_by_sequence(imported):
    shape = Shape.objects.get(feed_version=imported, gtfs_id="SH1")
    coords = [(round(x, 4), round(y, 4)) for x, y in shape.geometry.coords]
    assert coords == [(19.9380, 50.0615), (19.9450, 50.0550), (19.9600, 50.0480), (19.9800, 50.04)]


def test_trips_link_route_shape_and_direction(imported):
    with_shape = Trip.objects.get(feed_version=imported, gtfs_id="T1_WD_0800")
    without_shape = Trip.objects.get(feed_version=imported, gtfs_id="T1_WE_0900")
    assert with_shape.shape.gtfs_id == "SH1"
    assert without_shape.shape is None
    assert with_shape.route.gtfs_id == "R1"
    assert with_shape.service_id == "WD"
    assert with_shape.headsign == "Depot"
    assert with_shape.direction_id == 0
    assert without_shape.direction_id == 1
    assert with_shape.block_id == "B1"
    assert without_shape.block_id == ""


def test_route_colours_and_vehicle_type(imported):
    tram = Route.objects.get(feed_version=imported, gtfs_id="R1")
    bus = Route.objects.get(feed_version=imported, gtfs_id="R2")
    assert (tram.route_type, tram.vehicle_type) == (900, "tram")
    assert (bus.route_type, bus.vehicle_type) == (3, "bus")
    assert tram.color == "1F6FEB"
    assert tram.text_color == "FFFFFF"
    assert bus.color == ""
    assert tram.short_name == "1"
    assert bus.long_name == "Old Bridge - Depot"


def test_calendar_and_calendar_dates_are_stored(imported):
    wd = Calendar.objects.get(feed_version=imported, service_id="WD")
    assert (wd.monday, wd.friday, wd.saturday, wd.sunday) == (True, True, False, False)
    assert wd.start_date == date(2026, 1, 1)
    assert wd.end_date == date(2028, 12, 31)
    exceptions = {
        (cd.service_id, cd.date, cd.exception_type)
        for cd in CalendarDate.objects.filter(feed_version=imported)
    }
    assert exceptions == {("WD", date(2026, 11, 11), 2), ("WE", date(2026, 11, 11), 1)}


def test_frequency_is_stored(imported):
    freq = Frequency.objects.get(feed_version=imported)
    assert freq.trip.gtfs_id == "T2_WD_0715"
    assert freq.start_time == 7 * 3600 + 15 * 60
    assert freq.end_time == 9 * 3600 + 15 * 60
    assert freq.headway_secs == 600
    assert freq.exact_times is False


def test_clean_fixture_report_has_no_skips_or_warnings(imported):
    report = imported.report
    assert report["ignored_files"] == []
    assert report["warnings"] == []
    assert all(stats["skipped"] == 0 for stats in report["files"].values())


def test_unknown_files_are_listed_as_ignored(tmp_path):
    feed = copy_feed(tmp_path / "feed")
    (feed / "notes.txt").write_text("hello", encoding="utf-8")
    (feed / "fare_attributes.txt").write_text("fare_id\nF1\n", encoding="utf-8")
    result = run(feed)
    assert result.outcome == Outcome.IMPORTED
    assert result.report["ignored_files"] == ["fare_attributes.txt", "notes.txt"]


def test_zip_input_imports_like_directory(tmp_path):
    feed = copy_feed(tmp_path / "feed")
    archive = tmp_path / "feed.zip"
    archive.write_bytes(zip_directory(feed))
    result = run(archive)
    assert result.outcome == Outcome.IMPORTED
    assert result.report["counts"]["stop_times"] == 13


def test_command_prints_summary(feed_dir, capsys):
    call_command("import_gtfs", CITY, feed=FEED, file=feed_dir)
    out = capsys.readouterr().out
    assert f"{CITY}/{FEED}: imported" in out
    assert "stops=6" in out


# -------------------------------------------------------------------- idempotency


def test_second_run_with_same_file_is_unchanged(feed_dir, imported):
    before = imported.checked_at
    result = run(feed_dir)
    assert result.outcome == Outcome.UNCHANGED
    assert "sha256" in result.message
    assert FeedVersion.objects.filter(city_id=CITY, feed_id=FEED).count() == 1
    imported.refresh_from_db()
    assert imported.status == FeedVersion.Status.ACTIVE
    assert imported.checked_at > before
    assert Stop.objects.count() == 6


def test_command_reports_unchanged(feed_dir, imported, capsys):
    call_command("import_gtfs", CITY, feed=FEED, file=feed_dir)
    assert "unchanged" in capsys.readouterr().out


def test_force_creates_new_active_version_and_supersedes_old(feed_dir, imported):
    result = run(feed_dir, force=True)
    assert result.outcome == Outcome.IMPORTED
    imported.refresh_from_db()
    assert imported.status == FeedVersion.Status.SUPERSEDED
    new = FeedVersion.objects.get(pk=result.feed_version_id)
    assert new.status == FeedVersion.Status.ACTIVE
    assert Stop.objects.filter(feed_version=new).count() == 6
    assert Stop.objects.filter(feed_version=imported).count() == 6


def test_force_rotation_keeps_active_and_one_superseded(feed_dir, imported):
    first = imported
    second = FeedVersion.objects.get(pk=run(feed_dir, force=True).feed_version_id)
    third = FeedVersion.objects.get(pk=run(feed_dir, force=True).feed_version_id)
    versions = FeedVersion.objects.filter(city_id=CITY, feed_id=FEED)
    assert not versions.filter(pk=first.pk).exists()
    assert versions.get(status=FeedVersion.Status.ACTIVE).pk == third.pk
    assert versions.get(status=FeedVersion.Status.SUPERSEDED).pk == second.pk
    assert versions.count() == 2
    # Data of the deleted version is gone too, nothing orphaned.
    assert Stop.objects.filter(feed_version_id=first.pk).count() == 0
    assert StopTime.objects.filter(feed_version_id=first.pk).count() == 0
    assert Trip.objects.filter(feed_version_id=first.pk).count() == 0
    assert StopTime.objects.count() == 26


def test_keep_superseded_setting_is_honoured(feed_dir, imported, settings):
    settings.TRANSIT_GTFS_KEEP_SUPERSEDED = 0
    run(feed_dir, force=True)
    versions = FeedVersion.objects.filter(city_id=CITY, feed_id=FEED)
    assert [v.status for v in versions] == [FeedVersion.Status.ACTIVE]


def test_versions_of_different_feeds_are_independent(feed_dir, imported):
    other = run(feed_dir, feed="gv_second")
    assert other.outcome == Outcome.IMPORTED
    assert FeedVersion.objects.filter(status=FeedVersion.Status.ACTIVE).count() == 2
    # The same GTFS ids may exist in both feeds.
    assert Stop.objects.filter(gtfs_id="ST1").count() == 2


def test_changed_file_creates_new_version(tmp_path, imported):
    changed = copy_feed(
        tmp_path / "changed", {"routes.txt": replace_in("Old Bridge - Depot", "Old Bridge - Yard")}
    )
    result = run(changed)
    assert result.outcome == Outcome.IMPORTED
    imported.refresh_from_db()
    assert imported.status == FeedVersion.Status.SUPERSEDED
    route = Route.objects.get(feed_version_id=result.feed_version_id, gtfs_id="R2")
    assert route.long_name == "Old Bridge - Yard"


# --------------------------------------------------------------- failure handling


def test_missing_stops_file_fails_and_stores_error(tmp_path):
    feed = copy_feed(tmp_path / "feed", {"stops.txt": None})
    result = run(feed)
    assert result.outcome == Outcome.FAILED
    assert "stops.txt" in result.message
    version = FeedVersion.objects.get(pk=result.feed_version_id)
    assert version.status == FeedVersion.Status.FAILED
    assert "stops.txt" in version.error
    assert Stop.objects.count() == 0


def test_missing_required_column_fails_with_clear_error(tmp_path):
    feed = copy_feed(tmp_path / "feed", {"routes.txt": replace_in("route_type", "route_kind")})
    result = run(feed)
    assert result.outcome == Outcome.FAILED
    assert "route_type" in result.message


def test_not_a_zip_fails(tmp_path):
    bogus = tmp_path / "bogus.zip"
    bogus.write_bytes(b"this is not a zip file")
    result = run(bogus)
    assert result.outcome == Outcome.FAILED
    assert "zip" in result.message.lower()


def test_missing_local_file_fails_with_stored_version(tmp_path):
    result = run(tmp_path / "does-not-exist")
    assert result.outcome == Outcome.FAILED
    assert FeedVersion.objects.get(pk=result.feed_version_id).status == FeedVersion.Status.FAILED


def test_more_than_five_percent_bad_stop_times_is_rejected(tmp_path):
    result = run(bad_stop_times(tmp_path))
    assert result.outcome == Outcome.FAILED
    assert "stop_times.txt" in result.message
    assert "skipped" in result.message
    version = FeedVersion.objects.get(pk=result.feed_version_id)
    assert version.status == FeedVersion.Status.FAILED
    assert version.report["files"]["stop_times.txt"]["skipped"] == 2
    assert version.report["files"]["stop_times.txt"]["skip_reasons"] == {"unknown stop_id": 2}


def test_rejected_feed_leaves_no_rows_behind(tmp_path):
    run(bad_stop_times(tmp_path))
    for model in (Stop, Route, Trip, StopTime, Calendar, Shape, Agency):
        assert model.objects.count() == 0, model


def test_rejected_feed_keeps_active_version_untouched(tmp_path, imported):
    result = run(bad_stop_times(tmp_path))
    assert result.outcome == Outcome.FAILED
    imported.refresh_from_db()
    assert imported.status == FeedVersion.Status.ACTIVE
    assert Stop.objects.filter(feed_version=imported).count() == 6
    assert StopTime.objects.filter(feed_version=imported).count() == 13
    assert Stop.objects.count() == 6
    failed = FeedVersion.objects.get(pk=result.feed_version_id)
    assert failed.pk != imported.pk
    assert failed.status == FeedVersion.Status.FAILED


def test_small_amount_of_bad_rows_is_skipped_not_rejected(tmp_path, settings):
    settings.TRANSIT_GTFS_MAX_SKIPPED_RATIO = 0.2
    result = run(bad_stop_times(tmp_path))
    assert result.outcome == Outcome.IMPORTED
    assert result.report["counts"]["stop_times"] == 11
    assert result.report["files"]["stop_times.txt"]["skipped"] == 2


def test_malformed_time_row_is_skipped_with_reason(tmp_path, settings):
    settings.TRANSIT_GTFS_MAX_SKIPPED_RATIO = 0.2
    feed = copy_feed(
        tmp_path / "feed", {"stop_times.txt": replace_in("08:15:00,08:15:00", "8:99:00,08:15:00")}
    )
    result = run(feed)
    assert result.outcome == Outcome.IMPORTED
    stats = result.report["files"]["stop_times.txt"]
    assert stats["skipped"] == 1
    assert "invalid arrival_time or departure_time" in stats["skip_reasons"]


def test_failed_file_is_not_retried_without_force(tmp_path):
    feed = bad_stop_times(tmp_path)
    first = run(feed)
    second = run(feed)
    assert first.outcome == Outcome.FAILED
    assert second.outcome == Outcome.UNCHANGED
    assert "--force" in second.message
    assert FeedVersion.objects.filter(status=FeedVersion.Status.FAILED).count() == 1


def test_failed_file_is_retried_with_force(tmp_path):
    feed = bad_stop_times(tmp_path)
    run(feed)
    again = run(feed, force=True)
    assert again.outcome == Outcome.FAILED
    assert FeedVersion.objects.filter(status=FeedVersion.Status.FAILED).count() == 2


def test_different_file_after_failure_is_imported(tmp_path):
    run(bad_stop_times(tmp_path))
    assert run(copy_feed(tmp_path / "good")).outcome == Outcome.IMPORTED


def test_failed_version_rows_are_capped(tmp_path, settings):
    settings.TRANSIT_GTFS_KEEP_FAILED = 3
    feed = bad_stop_times(tmp_path)
    ids = [run(feed, force=True).feed_version_id for _ in range(6)]
    kept = set(
        FeedVersion.objects.filter(status=FeedVersion.Status.FAILED).values_list("pk", flat=True)
    )
    assert kept == set(ids[-3:])


def test_failed_versions_capped_at_five_by_default(tmp_path):
    feed = bad_stop_times(tmp_path)
    for _ in range(8):
        run(feed, force=True)
    assert FeedVersion.objects.filter(status=FeedVersion.Status.FAILED).count() == 5


def test_stale_importing_version_is_marked_failed(feed_dir, imported):
    stale = FeedVersion.objects.create(
        city_id=CITY,
        feed_id=FEED,
        status=FeedVersion.Status.IMPORTING,
        downloaded_at=timezone.now(),
    )
    result = run(feed_dir, force=True)
    assert result.outcome == Outcome.IMPORTED
    stale.refresh_from_db()
    assert stale.status == FeedVersion.Status.FAILED
    assert stale.error
    assert not FeedVersion.objects.filter(status=FeedVersion.Status.IMPORTING).exists()


def test_stale_importing_version_of_other_feed_is_left_alone(feed_dir):
    other = FeedVersion.objects.create(
        city_id=CITY,
        feed_id="gv_second",
        status=FeedVersion.Status.IMPORTING,
        downloaded_at=timezone.now(),
    )
    run(feed_dir)
    other.refresh_from_db()
    assert other.status == FeedVersion.Status.IMPORTING


def test_command_exits_with_code_1_when_a_feed_fails(tmp_path, capsys):
    feed = bad_stop_times(tmp_path)
    with pytest.raises(CommandError) as excinfo:
        call_command("import_gtfs", CITY, feed=FEED, file=feed)
    assert excinfo.value.returncode == 1
    out = capsys.readouterr().out
    assert "failed" in out
    assert "unknown stop_id" in out


def test_command_exit_is_zero_for_unchanged(feed_dir, imported):
    call_command("import_gtfs", CITY, feed=FEED, file=feed_dir)  # must not raise


# --------------------------------------------------------------------- calendars


def test_calendar_txt_is_optional_when_calendar_dates_exists(tmp_path):
    feed = copy_feed(tmp_path / "feed", {"calendar.txt": None})
    result = run(feed)
    assert result.outcome == Outcome.IMPORTED, result.message
    assert result.report["counts"]["calendars"] == 0
    assert result.report["counts"]["calendar_dates"] == 2
    version = FeedVersion.objects.get(pk=result.feed_version_id)
    # Only the "added" exception contributes service days.
    assert version.service_start_date == date(2026, 11, 11)
    assert version.service_end_date == date(2026, 11, 11)


def test_calendar_dates_txt_is_optional_when_calendar_exists(tmp_path):
    feed = copy_feed(tmp_path / "feed", {"calendar_dates.txt": None})
    result = run(feed)
    assert result.outcome == Outcome.IMPORTED, result.message
    assert result.report["counts"]["calendar_dates"] == 0
    version = FeedVersion.objects.get(pk=result.feed_version_id)
    assert version.service_end_date == date(2028, 12, 31)


def test_missing_both_calendar_files_is_an_error(tmp_path):
    feed = copy_feed(tmp_path / "feed", {"calendar.txt": None, "calendar_dates.txt": None})
    result = run(feed)
    assert result.outcome == Outcome.FAILED
    assert "calendar" in result.message
    assert FeedVersion.objects.get(pk=result.feed_version_id).status == FeedVersion.Status.FAILED


# ----------------------------------------------------------------- config / args


def test_feed_without_url_is_skipped():
    (result,) = import_city(CITY, "gv_no_url")
    assert result.outcome == Outcome.SKIPPED
    assert FeedVersion.objects.count() == 0


def test_city_import_covers_every_static_feed(monkeypatch):
    from transit_data.static_gtfs.pipeline import ImportResult

    called = []

    def fake_import_feed(city, feed, force=False, file=None):
        called.append(feed.id)
        return ImportResult(city.id, feed.id, Outcome.UNCHANGED)

    monkeypatch.setattr("transit_data.static_gtfs.pipeline.import_feed", fake_import_feed)
    results = import_city(CITY)
    assert called == ["gv_main", "gv_second", "gv_no_url"]
    assert len(results) == 3


def test_command_skips_feed_without_url(capsys):
    call_command("import_gtfs", CITY, feed="gv_no_url")
    assert "skipped" in capsys.readouterr().out


def test_unknown_city_is_a_clear_error():
    with pytest.raises(ImportConfigError, match="atlantis"):
        import_city("atlantis")
    with pytest.raises(CommandError, match="atlantis"):
        call_command("import_gtfs", "atlantis")


def test_unknown_feed_is_a_clear_error():
    with pytest.raises(CommandError, match="no static GTFS feed"):
        call_command("import_gtfs", CITY, feed="nope")


def test_realtime_feed_id_is_not_a_static_feed():
    with pytest.raises(CommandError):
        call_command("import_gtfs", "krakow", feed="ztp_tram_trip_updates")


def test_file_without_feed_is_a_clear_error(feed_dir):
    with pytest.raises(CommandError, match="--feed"):
        call_command("import_gtfs", CITY, file=feed_dir)
    assert FeedVersion.objects.count() == 0
