"""Static GTFS import, review round 1: retry semantics, temp tables, stop hierarchy,
share-of-active check, error masking and the download deadline."""

from __future__ import annotations

import urllib.error
from types import SimpleNamespace

import psycopg
import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.db import OperationalError, connection
from django.utils import timezone

from transit_data.models import FeedVersion, Stop, StopTime
from transit_data.static_gtfs import download, pipeline
from transit_data.static_gtfs.download import DownloadError, download_feed, local_feed
from transit_data.static_gtfs.loader import FeedRejected
from transit_data.static_gtfs.pipeline import Outcome, import_city, import_feed
from transit_data.static_gtfs.reader import GtfsFormatError

from .gtfs_support import CITY, FEED, FEED_URL, FakeServer, copy_feed, replace_in, zip_directory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("gtfs_city")]


def run(path, force=False, feed=FEED):
    (result,) = import_city(CITY, feed, force=force, file=path)
    return result


def version_of(result):
    return FeedVersion.objects.get(pk=result.feed_version_id)


def lock_is_free() -> bool:
    """True when another database session can take the advisory lock of the test feed."""
    s = connection.settings_dict
    other = psycopg.connect(
        dbname=s["NAME"],
        user=s["USER"],
        password=s["PASSWORD"],
        host=s["HOST"],
        port=s["PORT"] or None,
        autocommit=True,
    )
    try:
        with other.cursor() as cursor:
            key = pipeline._feed_lock(CITY, FEED).key
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
            return cursor.fetchone()[0]
    finally:
        other.close()


def release_own_lock():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", [pipeline._feed_lock(CITY, FEED).key])


@pytest.fixture
def active(tmp_path):
    result = run(copy_feed(tmp_path / "first"))
    assert result.outcome == Outcome.IMPORTED
    return version_of(result)


@pytest.fixture
def changed(tmp_path):
    """A valid feed that differs from the fixture (different sha256)."""
    return copy_feed(
        tmp_path / "changed", {"routes.txt": replace_in("Old Bridge - Depot", "Old Bridge - Yard")}
    )


def explode(exception):
    def fail(*args, **kwargs):
        raise exception

    return fail


# ----------------------------------------------------------- 1. retry semantics


@pytest.mark.parametrize(
    "exception",
    [RuntimeError("boom"), OperationalError("db gone"), SoftTimeLimitExceeded()],
)
def test_unexpected_load_error_is_not_a_data_error_and_is_retried(
    monkeypatch, active, changed, exception
):
    with monkeypatch.context() as patch:
        patch.setattr(pipeline, "load_feed", explode(exception))
        result = run(changed)
    assert result.outcome == Outcome.FAILED
    failed = version_of(result)
    assert failed.status == FeedVersion.Status.FAILED
    assert failed.data_error is False
    assert type(exception).__name__ in failed.error
    # Active version and its data are untouched, lock is released.
    active.refresh_from_db()
    assert active.status == FeedVersion.Status.ACTIVE
    assert StopTime.objects.filter(feed_version=active).count() == 13
    assert Stop.objects.count() == 6
    assert lock_is_free()
    # The next run without --force imports the very same file.
    retry = run(changed)
    assert retry.outcome == Outcome.IMPORTED, retry.message
    assert version_of(retry).status == FeedVersion.Status.ACTIVE


def test_stale_importing_row_with_same_sha_is_interrupted_and_file_is_imported(tmp_path):
    feed = copy_feed(tmp_path / "feed")
    stale = FeedVersion.objects.create(
        city_id=CITY,
        feed_id=FEED,
        status=FeedVersion.Status.IMPORTING,
        downloaded_at=timezone.now(),
        sha256=local_feed(feed).sha256,
    )
    result = run(feed)
    assert result.outcome == Outcome.IMPORTED
    stale.refresh_from_db()
    assert stale.status == FeedVersion.Status.FAILED
    assert stale.error == "import interrupted"
    assert stale.data_error is False


def test_format_error_is_a_data_error_and_not_retried(tmp_path):
    feed = copy_feed(tmp_path / "feed", {"stops.txt": None})
    first = run(feed)
    assert version_of(first).data_error is True
    second = run(feed)
    assert second.outcome == Outcome.UNCHANGED
    assert "--force" in second.message
    assert run(feed, force=True).outcome == Outcome.FAILED


def test_rejected_feed_is_a_data_error_and_not_retried(tmp_path):
    from .test_gtfs_import import bad_stop_times

    feed = bad_stop_times(tmp_path)
    first = run(feed)
    assert version_of(first).data_error is True
    assert run(feed).outcome == Outcome.UNCHANGED


@pytest.mark.parametrize("exception", [GtfsFormatError("bad"), FeedRejected("rejected")])
def test_format_and_rejection_exceptions_set_data_error(monkeypatch, tmp_path, exception):
    feed = copy_feed(tmp_path / "feed")
    with monkeypatch.context() as patch:
        patch.setattr(pipeline, "load_feed", explode(exception))
        result = run(feed)
    assert version_of(result).data_error is True
    assert run(feed).outcome == Outcome.UNCHANGED


def test_download_failure_is_not_a_data_error(tmp_path, monkeypatch):
    server = FakeServer(zip_directory(copy_feed(tmp_path / "served")))
    server.error = urllib.error.HTTPError(FEED_URL, 500, "Boom", {}, None)
    monkeypatch.setattr(download.urllib.request, "urlopen", server)
    city = pipeline.get_city(CITY)
    feed = next(f for f in city.feeds if f.id == FEED)
    result = import_feed(city, feed)
    assert result.outcome == Outcome.FAILED
    assert version_of(result).data_error is False
    server.error = None
    assert import_feed(city, feed).outcome == Outcome.IMPORTED


def test_failed_version_save_leaves_importing_row_that_is_recovered(monkeypatch, tmp_path):
    feed = copy_feed(tmp_path / "feed")
    real_save = FeedVersion.save

    def save(self, *args, **kwargs):
        if self.status == FeedVersion.Status.FAILED:
            raise OperationalError("connection lost")
        return real_save(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(pipeline, "load_feed", explode(RuntimeError("boom")))
        patch.setattr(FeedVersion, "save", save)
        result = run(feed)  # must not raise
    assert result.outcome == Outcome.FAILED
    assert version_of(result).status == FeedVersion.Status.IMPORTING
    assert run(feed).outcome == Outcome.IMPORTED


# ---------------------------------------------------------------- 2. temp tables


def test_public_tables_with_import_helper_names_survive_an_import(tmp_path):
    with connection.cursor() as cursor:
        cursor.execute("CREATE TABLE public.gtfs_import_parent (child bigint, parent bigint)")
        cursor.execute("INSERT INTO public.gtfs_import_parent VALUES (1, 2)")
        cursor.execute(
            "CREATE TABLE public.gtfs_import_shape_point"
            " (shape_id text, seq int, lon float, lat float)"
        )
        cursor.execute("INSERT INTO public.gtfs_import_shape_point VALUES ('x', 1, 0, 0)")
    result = run(copy_feed(tmp_path / "feed"))
    assert result.outcome == Outcome.IMPORTED
    with connection.cursor() as cursor:
        cursor.execute("SELECT child, parent FROM public.gtfs_import_parent")
        assert cursor.fetchall() == [(1, 2)]
        cursor.execute("SELECT shape_id FROM public.gtfs_import_shape_point")
        assert cursor.fetchall() == [("x",)]


# -------------------------------------------------------------- 3. stop hierarchy

ROW_ST1 = "ST1,,Main Square,50.0614,19.9383,1,,1,"
ROW_ST1_A = "ST1_A,101,Main Square,50.0615,19.9380,0,ST1,1,A"


def stops_variant(tmp_path, transform):
    return copy_feed(tmp_path / "hier", {"stops.txt": transform})


def corrections(result):
    return result.report["files"]["stops.txt"]["corrections"]


def test_station_with_parent_has_link_cleared(tmp_path):
    new = "ST1,,Main Square,50.0614,19.9383,1,S2,1,"
    result = run(stops_variant(tmp_path, replace_in(ROW_ST1, new)))
    assert result.outcome == Outcome.IMPORTED
    assert Stop.objects.get(gtfs_id="ST1").parent_station is None
    assert corrections(result) == {"parent_station on a station, cleared": 1}


def test_platform_with_non_station_parent_has_link_cleared(tmp_path):
    new = "ST1_A,101,Main Square,50.0615,19.9380,0,S2,1,A"
    result = run(stops_variant(tmp_path, replace_in(ROW_ST1_A, new)))
    assert result.outcome == Outcome.IMPORTED
    assert Stop.objects.get(gtfs_id="ST1_A").parent_station is None
    assert Stop.objects.get(gtfs_id="ST1_B").parent_station.gtfs_id == "ST1"
    (reason,) = corrections(result)
    assert reason.startswith("parent_station has location_type 0 instead of 1")


def test_boarding_area_needs_a_platform_parent(tmp_path):
    def add_boarding_areas(text):
        return (
            text.rstrip("\n")
            + "\nBA_OK,,Boarding,50.0615,19.9381,4,ST1_A,,"
            + "\nBA_BAD,,Boarding,50.0615,19.9382,4,ST1,,\n"
        )

    result = run(stops_variant(tmp_path, add_boarding_areas))
    assert result.outcome == Outcome.IMPORTED
    assert Stop.objects.get(gtfs_id="BA_OK").parent_station.gtfs_id == "ST1_A"
    assert Stop.objects.get(gtfs_id="BA_BAD").parent_station is None
    (reason,) = corrections(result)
    assert reason.startswith("parent_station has location_type 1 instead of 0")


def test_unknown_parent_station_is_cleared(tmp_path):
    new = "ST1_A,101,Main Square,50.0615,19.9380,0,NOPE,1,A"
    result = run(stops_variant(tmp_path, replace_in(ROW_ST1_A, new)))
    assert Stop.objects.get(gtfs_id="ST1_A").parent_station is None
    assert corrections(result) == {"unknown parent_station, cleared": 1}


def station_in_stop_times(tmp_path):
    old = "T2_WD_0715,07:30:00,07:30:00,S4"
    new = "T2_WD_0715,07:30:00,07:30:00,ST1"
    return copy_feed(tmp_path / "st", {"stop_times.txt": replace_in(old, new)})


def test_stop_time_on_a_station_is_skipped_with_reason(tmp_path, settings):
    settings.TRANSIT_GTFS_MAX_SKIPPED_RATIO = 0.2
    result = run(station_in_stop_times(tmp_path))
    assert result.outcome == Outcome.IMPORTED
    stats = result.report["files"]["stop_times.txt"]
    assert stats["skipped"] == 1
    assert stats["skip_reasons"] == {"stop_id is not a stop or platform (location_type 1)": 1}
    assert StopTime.objects.count() == 12


def test_stop_time_on_a_station_counts_toward_the_threshold(tmp_path):
    result = run(station_in_stop_times(tmp_path))  # 1 of 13 = 7.7% > 5%
    assert result.outcome == Outcome.FAILED
    assert "stop_times.txt" in result.message


# ------------------------------------------------------- 4. share of active version


def shrunk_feed(tmp_path):
    """Keeps one trip with 2 stop times: trips 1 of 4, stop_times 2 of 13."""

    def only_t2(text):
        return "".join(line for line in text.splitlines(True) if "T1_" not in line)

    return copy_feed(tmp_path / "small", {"trips.txt": only_t2, "stop_times.txt": only_t2})


def test_much_smaller_feed_is_rejected_and_active_kept(tmp_path, active):
    result = run(shrunk_feed(tmp_path))
    assert result.outcome == Outcome.FAILED
    assert "below 50%" in result.message
    failed = version_of(result)
    assert failed.data_error is True
    active.refresh_from_db()
    assert active.status == FeedVersion.Status.ACTIVE
    assert Stop.objects.filter(feed_version=active).count() == 6
    assert StopTime.objects.filter(feed_version=active).count() == 13
    comparison = failed.report["comparison"]
    assert comparison["active_feed_version_id"] == active.pk
    assert comparison["min_share"] == 0.5
    assert comparison["trips"] == {"new": 1, "active": 4}
    assert comparison["stop_times"] == {"new": 2, "active": 13}


def test_smaller_feed_is_not_retried_without_force(tmp_path, active):
    feed = shrunk_feed(tmp_path)
    run(feed)
    assert run(feed).outcome == Outcome.UNCHANGED


def test_force_bypasses_share_check(tmp_path, active):
    result = run(shrunk_feed(tmp_path), force=True)
    assert result.outcome == Outcome.IMPORTED, result.message
    assert version_of(result).report["comparison"] == {}
    active.refresh_from_db()
    assert active.status == FeedVersion.Status.SUPERSEDED


def test_min_share_setting_is_honoured(tmp_path, active, settings):
    settings.TRANSIT_GTFS_MIN_SHARE_OF_ACTIVE = 0.1
    result = run(shrunk_feed(tmp_path))
    assert result.outcome == Outcome.IMPORTED, result.message
    comparison = version_of(result).report["comparison"]
    assert comparison["trips"] == {"new": 1, "active": 4}
    assert comparison["stop_times"] == {"new": 2, "active": 13}


def test_first_import_has_no_comparison(tmp_path):
    result = run(copy_feed(tmp_path / "feed"))
    assert version_of(result).report["comparison"] == {}


def test_feed_of_similar_size_passes_share_check(active, changed):
    result = run(changed)
    assert result.outcome == Outcome.IMPORTED
    comparison = version_of(result).report["comparison"]
    assert comparison["trips"] == {"new": 4, "active": 4}


# ----------------------------------------------------------------- 5. error masking


def flaky_connection(monkeypatch):
    """Replace the pipeline connection: the first cursor (lock) works, later ones fail."""
    real = pipeline.connection
    calls = []

    class FlakyConnection:
        def cursor(self):
            calls.append(1)
            if len(calls) > 1:
                raise OperationalError("unlock failed")
            return real.cursor()

    monkeypatch.setattr(pipeline, "connection", FlakyConnection())


def test_unlock_failure_does_not_mask_the_original_exception(monkeypatch):
    flaky_connection(monkeypatch)
    with pytest.raises(ValueError, match="original"), pipeline._feed_lock(CITY, FEED) as locked:
        assert locked
        raise ValueError("original")
    monkeypatch.undo()
    release_own_lock()


def test_unlock_failure_without_exception_does_not_raise(monkeypatch):
    flaky_connection(monkeypatch)
    with pipeline._feed_lock(CITY, FEED):
        pass
    monkeypatch.undo()
    release_own_lock()


def importing_version():
    return FeedVersion.objects.create(
        city_id=CITY,
        feed_id=FEED,
        status=FeedVersion.Status.IMPORTING,
        downloaded_at=timezone.now(),
    )


def test_mark_failed_never_raises_when_database_is_broken(monkeypatch):
    version = importing_version()
    monkeypatch.setattr(FeedVersion, "save", explode(OperationalError("down")))
    result = pipeline._mark_failed(
        version, pipeline.ImportReport(), 0.0, "the original error", data_error=True
    )
    assert result.outcome == Outcome.FAILED
    assert result.message == "the original error"


def test_mark_failed_survives_cleanup_errors(monkeypatch):
    version = importing_version()
    monkeypatch.setattr(pipeline, "cleanup_feed", explode(OperationalError("cleanup")))
    result = pipeline._mark_failed(version, pipeline.ImportReport(), 0.0, "err", data_error=False)
    assert result.outcome == Outcome.FAILED
    version.refresh_from_db()
    assert version.status == FeedVersion.Status.FAILED
    assert version.data_error is False


def test_cleanup_failure_after_success_keeps_the_import(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "cleanup_feed", explode(OperationalError("cleanup")))
    result = run(copy_feed(tmp_path / "feed"))
    assert result.outcome == Outcome.IMPORTED
    assert version_of(result).status == FeedVersion.Status.ACTIVE


# ----------------------------------------------------------- 6. download deadline


class _Clock:
    """Fake ``time`` module: the first reading is the start, later ones are far later."""

    def __init__(self):
        self.readings = 0

    def monotonic(self):
        self.readings += 1
        return 0.0 if self.readings == 1 else 10_000.0


def serve(tmp_path, monkeypatch, settings, slow):
    settings.TRANSIT_GTFS_DOWNLOAD_MAX_SECONDS = 10
    server = FakeServer(zip_directory(copy_feed(tmp_path / "served")))
    monkeypatch.setattr(download.urllib.request, "urlopen", server)
    if slow:
        monkeypatch.setattr(download, "time", SimpleNamespace(monotonic=_Clock().monotonic))
    return server


def test_download_deadline_aborts_a_slow_download(tmp_path, monkeypatch, settings):
    serve(tmp_path, monkeypatch, settings, slow=True)
    with pytest.raises(DownloadError, match="longer than 10 seconds"):
        download_feed(FEED_URL, tmp_path / "out.zip")


def test_download_within_deadline_succeeds(tmp_path, monkeypatch, settings):
    server = serve(tmp_path, monkeypatch, settings, slow=False)
    assert download_feed(FEED_URL, tmp_path / "out.zip").size_bytes == len(server.body)


def test_slow_download_is_recorded_as_failed_without_data_error(tmp_path, monkeypatch, settings):
    serve(tmp_path, monkeypatch, settings, slow=True)
    city = pipeline.get_city(CITY)
    feed = next(f for f in city.feeds if f.id == FEED)
    result = import_feed(city, feed)
    assert result.outcome == Outcome.FAILED
    assert "longer than" in result.message
    assert version_of(result).data_error is False
