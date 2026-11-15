"""Static GTFS: vehicle types, time parsing, expiry warning, lock, admin, tasks."""

from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

import psycopg
import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from transit_data.models import (
    FeedVersion,
    Route,
    Stop,
    VehicleType,
    vehicle_type_for_route_type,
)
from transit_data.static_gtfs import pipeline
from transit_data.static_gtfs.loader import expiry_warning, parse_date, parse_time
from transit_data.static_gtfs.pipeline import Outcome, import_city
from transit_data.static_gtfs.report import ImportReport, format_report

from .gtfs_support import CITY, FEED, copy_feed

# ------------------------------------------------------------------- vehicle type


@pytest.mark.parametrize(
    ("route_type", "expected"),
    [
        (0, "tram"),
        (1, "metro"),
        (2, "rail"),
        (3, "bus"),
        (5, "tram"),
        (11, "bus"),
        (12, "rail"),
        (100, "rail"),
        (199, "rail"),
        (200, "bus"),
        (400, "metro"),
        (401, "metro"),
        (499, "metro"),
        (700, "bus"),
        (714, "bus"),
        (800, "bus"),
        (900, "tram"),
        (901, "tram"),
        (999, "tram"),
        (4, "other"),  # ferry
        (6, "other"),  # gondola
        (500, "other"),
        (1000, "other"),
        (-1, "other"),
        (99999, "other"),
    ],
)
def test_vehicle_type_for_route_type(route_type, expected):
    assert vehicle_type_for_route_type(route_type) == expected


def test_route_vehicle_type_property_uses_route_type():
    assert Route(route_type=900).vehicle_type == VehicleType.TRAM
    assert Route(route_type=3).vehicle_type == VehicleType.BUS
    assert Route(route_type=1).vehicle_type == VehicleType.METRO
    assert Route(route_type=4242).vehicle_type == VehicleType.OTHER


# ------------------------------------------------------------------- time parsing


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("00:00:00", 0),
        ("08:05:30", 8 * 3600 + 5 * 60 + 30),
        ("9:12:00", 9 * 3600 + 12 * 60),
        ("23:59:59", 86399),
        ("24:00:00", 86400),
        ("24:10:00", 87000),
        ("25:30:15", 25 * 3600 + 30 * 60 + 15),
        ("  08:00:00  ", 8 * 3600),
        ("", None),
        ("   ", None),
    ],
)
def test_parse_time(text, seconds):
    assert parse_time(text) == seconds


@pytest.mark.parametrize(
    "text",
    ["8:5:00", "08:60:00", "08:00:60", "-1:00:00", "08:00", "abc", "99:00:00", "08:00:00:00"],
)
def test_parse_time_rejects_malformed_values(text):
    with pytest.raises(ValueError):
        parse_time(text)


def test_parse_date():
    assert parse_date("20261111") == date(2026, 11, 11)
    assert parse_date(" 20280229 ") == date(2028, 2, 29)


@pytest.mark.parametrize("text", ["2026-11-11", "20261301", "20260230", "", "2026111"])
def test_parse_date_rejects_malformed_values(text):
    with pytest.raises(ValueError):
        parse_date(text)


# ------------------------------------------------------------------- expiry warning


def test_expiry_warning_when_service_ends_soon(settings):
    settings.TRANSIT_GTFS_EXPIRY_WARNING_DAYS = 14
    today = date(2026, 11, 14)
    message = expiry_warning(today + timedelta(days=5), today)
    assert message
    assert "2026-11-19" in message
    assert "5" in message


def test_expiry_warning_on_last_day_of_window(settings):
    settings.TRANSIT_GTFS_EXPIRY_WARNING_DAYS = 14
    today = date(2026, 11, 14)
    assert expiry_warning(today + timedelta(days=14), today)
    assert expiry_warning(today + timedelta(days=15), today) is None


def test_expiry_warning_when_service_already_ended():
    today = date(2026, 11, 14)
    message = expiry_warning(date(2026, 11, 1), today)
    assert message
    assert "ended" in message
    assert "13" in message


def test_expiry_warning_service_ends_today(settings):
    today = date(2026, 11, 14)
    assert "ends" in expiry_warning(today, today)


def test_no_expiry_warning_for_distant_or_unknown_end():
    today = date(2026, 11, 14)
    assert expiry_warning(date(2028, 12, 31), today) is None
    assert expiry_warning(None, today) is None


def test_expiry_warning_window_is_configurable(settings):
    settings.TRANSIT_GTFS_EXPIRY_WARNING_DAYS = 2
    today = date(2026, 11, 14)
    assert expiry_warning(today + timedelta(days=5), today) is None
    assert expiry_warning(today + timedelta(days=2), today)


def _calendar_ending(day: date):
    stamp = day.strftime("%Y%m%d")
    return {
        "calendar.txt": lambda t: t.replace("20281231", stamp),
        # Only a removal, so calendar_dates does not extend the service range.
        "calendar_dates.txt": lambda t: "service_id,date,exception_type\nWD,20260105,2\n",
    }


@pytest.mark.usefixtures("gtfs_city")
@pytest.mark.django_db
def test_import_warns_when_service_ends_soon(tmp_path):
    end = timezone.now().astimezone(ZoneInfo("Europe/Warsaw")).date() + timedelta(days=5)
    feed = copy_feed(tmp_path / "feed", _calendar_ending(end))
    (result,) = import_city(CITY, FEED, file=feed)
    assert result.outcome == Outcome.IMPORTED
    warnings = FeedVersion.objects.get(pk=result.feed_version_id).report["warnings"]
    assert any("service ends" in w and end.isoformat() in w for w in warnings)


@pytest.mark.usefixtures("gtfs_city")
@pytest.mark.django_db
def test_import_warns_when_service_already_ended(tmp_path):
    feed = copy_feed(tmp_path / "feed", _calendar_ending(date(2026, 1, 31)))
    (result,) = import_city(CITY, FEED, file=feed)
    assert result.outcome == Outcome.IMPORTED, "an expired feed is imported with a warning"
    warnings = FeedVersion.objects.get(pk=result.feed_version_id).report["warnings"]
    assert any("ended" in w for w in warnings)


@pytest.mark.usefixtures("gtfs_city")
@pytest.mark.django_db
def test_command_prints_warnings(tmp_path, capsys):
    from django.core.management import call_command

    feed = copy_feed(tmp_path / "feed", _calendar_ending(date(2026, 1, 31)))
    call_command("import_gtfs", CITY, feed=FEED, file=feed)
    assert "warning:" in capsys.readouterr().out


# ------------------------------------------------------------------ report format


def test_format_report_lists_ignored_files_and_skips():
    report = ImportReport()
    stats = report.file("stop_times.txt")
    stats.rows = 10
    stats.imported = 8
    stats.skip(3, "unknown stop_id", "X1")
    stats.skip(4, "unknown stop_id", "X2")
    report.ignored_files = ["blocks.txt"]
    report.counts["stops"] = 4
    text = "\n".join(format_report(report.as_dict()))
    assert "stops=4" in text
    assert "skipped 2: unknown stop_id" in text
    assert "ignored files: blocks.txt" in text


def test_report_examples_are_capped_but_counts_are_complete():
    stats = ImportReport().file("stops.txt")
    for i in range(100):
        stats.skip(i, "bad", "x" * 500)
    data = stats.as_dict()
    assert data["skipped"] == 100
    assert data["skip_reasons"] == {"bad": 100}
    assert len(data["examples"]) <= 20
    assert all(len(e["value"]) <= 80 for e in data["examples"])


# ----------------------------------------------------------------- advisory lock


def _other_connection():
    settings = connection.settings_dict
    return psycopg.connect(
        dbname=settings["NAME"],
        user=settings["USER"],
        password=settings["PASSWORD"],
        host=settings["HOST"],
        port=settings["PORT"] or None,
        autocommit=True,
    )


def _release(conn, key):
    """Unlock explicitly, then close.

    Closing the client connection does not wait for the server backend to drop its
    session advisory locks, so a following test could still see the feed as busy.
    The result is deliberately not asserted so this never hides the original error.
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
    finally:
        conn.close()


@pytest.mark.django_db
def test_feed_lock_is_exclusive_across_connections():
    with pipeline._feed_lock("c", "f") as first:
        assert first is True
        other = _other_connection()
        try:
            with other.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_try_advisory_lock(%s)", [pipeline._feed_lock("c", "f").key]
                )
                assert cursor.fetchone()[0] is False
        finally:
            other.close()
    # Released on exit: another session can take it now.
    other = _other_connection()
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [pipeline._feed_lock("c", "f").key])
            assert cursor.fetchone()[0] is True
    finally:
        _release(other, pipeline._feed_lock("c", "f").key)


@pytest.mark.django_db
def test_feed_lock_keys_differ_per_feed():
    assert pipeline._feed_lock("c", "a").key != pipeline._feed_lock("c", "b").key
    assert pipeline._feed_lock("c", "a").key != pipeline._feed_lock("d", "a").key
    assert pipeline._feed_lock("c", "a").key == pipeline._feed_lock("c", "a").key


@pytest.mark.django_db
@pytest.mark.usefixtures("gtfs_city")
def test_import_of_a_locked_feed_returns_busy(tmp_path):
    feed = copy_feed(tmp_path / "feed")
    other = _other_connection()
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [pipeline._feed_lock(CITY, FEED).key])
        (result,) = import_city(CITY, FEED, file=feed)
        assert result.outcome == Outcome.BUSY
        assert FeedVersion.objects.count() == 0
        assert Stop.objects.count() == 0
    finally:
        _release(other, pipeline._feed_lock(CITY, FEED).key)
    (result,) = import_city(CITY, FEED, file=feed)
    assert result.outcome == Outcome.IMPORTED


@pytest.mark.django_db
@pytest.mark.usefixtures("gtfs_city")
def test_lock_of_one_feed_does_not_block_another(tmp_path):
    feed = copy_feed(tmp_path / "feed")
    other = _other_connection()
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [pipeline._feed_lock(CITY, FEED).key])
        (result,) = import_city(CITY, "gv_second", file=feed)
        assert result.outcome == Outcome.IMPORTED
    finally:
        _release(other, pipeline._feed_lock(CITY, FEED).key)


@pytest.mark.django_db
@pytest.mark.usefixtures("gtfs_city")
def test_lock_is_released_after_failed_import(tmp_path):
    bad = copy_feed(tmp_path / "bad", {"stops.txt": None})
    (result,) = import_city(CITY, FEED, file=bad)
    assert result.outcome == Outcome.FAILED
    other = _other_connection()
    try:
        with other.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [pipeline._feed_lock(CITY, FEED).key])
            assert cursor.fetchone()[0] is True
    finally:
        _release(other, pipeline._feed_lock(CITY, FEED).key)


# ------------------------------------------------------------------------- admin

MODEL_NAMES = [
    "feedversion",
    "agency",
    "stop",
    "route",
    "calendar",
    "calendardate",
    "shape",
    "trip",
    "stoptime",
    "frequency",
]


@pytest.fixture
def admin_client(client, db):
    user = get_user_model().objects.create_superuser("root", "root@example.org", "pw")
    client.force_login(user)
    return client


@pytest.fixture
def imported_feed(gtfs_city, tmp_path, db):
    (result,) = import_city(CITY, FEED, file=copy_feed(tmp_path / "feed"))
    assert result.outcome == Outcome.IMPORTED
    return FeedVersion.objects.get(pk=result.feed_version_id)


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_admin_changelist_is_available(admin_client, imported_feed, name):
    response = admin_client.get(reverse(f"admin:transit_data_{name}_changelist"))
    assert response.status_code == 200


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_admin_add_is_forbidden(admin_client, imported_feed, name):
    response = admin_client.get(reverse(f"admin:transit_data_{name}_add"))
    assert response.status_code == 403


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_admin_delete_is_forbidden(admin_client, imported_feed, name):
    from django.apps import apps

    obj = apps.get_model("transit_data", name).objects.first()
    assert obj is not None
    url = reverse(f"admin:transit_data_{name}_delete", args=[obj.pk])
    assert admin_client.get(url).status_code == 403
    assert admin_client.post(url, {"post": "yes"}).status_code == 403
    assert type(obj).objects.filter(pk=obj.pk).exists()


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_admin_detail_page_is_read_only_view(admin_client, imported_feed, name):
    from django.apps import apps

    obj = apps.get_model("transit_data", name).objects.first()
    response = admin_client.get(reverse(f"admin:transit_data_{name}_change", args=[obj.pk]))
    assert response.status_code == 200
    assert b'name="_save"' not in response.content


def test_admin_post_cannot_change_a_stop(admin_client, imported_feed):
    stop = Stop.objects.get(gtfs_id="S2")
    url = reverse("admin:transit_data_stop_change", args=[stop.pk])
    response = admin_client.post(url, {"name": "Hacked", "gtfs_id": "S2"})
    assert response.status_code == 403
    stop.refresh_from_db()
    assert stop.name == "Old Bridge"


def test_admin_requires_login(client, db):
    response = client.get(reverse("admin:transit_data_stop_changelist"))
    assert response.status_code == 302
    assert "login" in response["Location"]


def test_admin_feed_version_page_shows_report(admin_client, imported_feed):
    response = admin_client.get(
        reverse("admin:transit_data_feedversion_change", args=[imported_feed.pk])
    )
    assert b"stop_times" in response.content


@pytest.mark.parametrize("query", ["city=gtfsville", "feed_version=%s", "location_type__exact=1"])
def test_admin_stop_filters_work(admin_client, imported_feed, query):
    query = query.replace("%s", str(imported_feed.pk))
    response = admin_client.get(reverse("admin:transit_data_stop_changelist") + "?" + query)
    assert response.status_code == 200


def test_admin_stop_search_by_name(admin_client, imported_feed):
    response = admin_client.get(reverse("admin:transit_data_stop_changelist") + "?q=Depot")
    assert response.status_code == 200
    assert b"Depot" in response.content


# ------------------------------------------------------------------------- tasks


@pytest.mark.usefixtures("gtfs_city")
def test_import_all_gtfs_queues_one_task_per_city(monkeypatch):
    from transit_data import tasks

    queued = []
    monkeypatch.setattr(tasks.import_city_gtfs, "delay", lambda *a, **kw: queued.append((a, kw)))
    tasks.import_all_gtfs()
    assert sorted(a[0] for a, _ in queued) == ["gtfsville", "krakow", "warszawa"]
    assert len(queued) == 3


def test_task_names_are_stable():
    from transit_data import tasks

    assert tasks.import_all_gtfs.name == "transit_data.import_all_gtfs"
    assert tasks.import_city_gtfs.name == "transit_data.import_city_gtfs"


@pytest.mark.django_db
@pytest.mark.usefixtures("gtfs_city")
def test_import_city_gtfs_returns_summary_per_feed(monkeypatch):
    from transit_data import tasks

    # gv_main/gv_second would hit the network: serve nothing, expect failures, not crashes.
    def refuse(request, timeout=None):
        import urllib.error

        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    summary = tasks.import_city_gtfs(CITY)
    outcomes = {item["feed_id"]: item["outcome"] for item in summary}
    assert outcomes == {
        "gv_main": Outcome.FAILED,
        "gv_second": Outcome.FAILED,
        "gv_no_url": Outcome.SKIPPED,
    }
    assert all(set(item) >= {"city_id", "feed_id", "outcome", "message"} for item in summary)


@pytest.mark.django_db
@pytest.mark.usefixtures("gtfs_city")
def test_one_failing_feed_does_not_stop_the_others(monkeypatch, tmp_path):
    from transit_data.static_gtfs import download

    from .gtfs_support import FakeServer, zip_directory

    server = FakeServer(zip_directory(copy_feed(tmp_path / "served")))
    calls = []

    def selective(request, timeout=None):
        calls.append(request.full_url)
        if request.full_url.endswith("main.zip"):
            import urllib.error

            raise urllib.error.URLError("down")
        return server(request, timeout)

    monkeypatch.setattr(download.urllib.request, "urlopen", selective)
    results = import_city(CITY)
    by_feed = {r.feed_id: r.outcome for r in results}
    assert by_feed == {
        "gv_main": Outcome.FAILED,
        "gv_second": Outcome.IMPORTED,
        "gv_no_url": Outcome.SKIPPED,
    }
