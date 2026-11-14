"""Celery task, beat schedule and the ``collect_trip_updates`` management command."""

from io import StringIO

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command

from transit_data import realtime
from transit_data.models import FeedFetch, StopEvent
from transit_data.realtime import FetchError
from transit_data.tasks import collect_trip_updates

from .conftest import (
    KRAKOW_BUS_FEED,
    KRAKOW_TRAM_FEED,
    epoch,
    krakow_trip_update_urls,
    make_message,
)

pytestmark = pytest.mark.django_db

BUS_URL = "https://gtfs.ztp.krakow.pl/TripUpdates_A.pb"
TRAM_URL = "https://gtfs.ztp.krakow.pl/TripUpdates_T.pb"


def serve_all_krakow(served, tram_pb, bus_pb):
    """Serve every configured Krakow TripUpdates feed.

    Tram and bus get the recorded messages; any other configured feed gets an empty valid message,
    so tests do not depend on how many feeds the city has.
    """
    empty = make_message([], epoch(2026, 11, 10, 12))
    for url in krakow_trip_update_urls().values():
        served[url] = empty
    served[TRAM_URL] = tram_pb
    served[BUS_URL] = bus_pb


def test_task_polls_all_feeds_and_stores_events(served, tram_pb, bus_pb):
    serve_all_krakow(served, tram_pb, bus_pb)

    collect_trip_updates.delay()

    assert sorted(served.requested) == sorted(krakow_trip_update_urls().values())
    assert StopEvent.objects.count() == 145  # extra feeds are served empty
    assert set(FeedFetch.objects.values_list("status", flat=True)) == {"ok"}


def test_task_does_not_raise_when_every_feed_fails(served):
    for url in krakow_trip_update_urls().values():
        served[url] = b""
    served[BUS_URL] = FetchError("network_error", "down")

    collect_trip_updates.delay()  # eager mode propagates exceptions, so this proves it

    statuses = sorted(FeedFetch.objects.values_list("status", flat=True))
    assert statuses.count("network_error") == 1
    assert statuses.count("parse_error") == len(krakow_trip_update_urls()) - 1
    assert len(statuses) == len(krakow_trip_update_urls())


def test_task_is_registered_under_the_scheduled_name():
    assert collect_trip_updates.name == "transit_data.collect_trip_updates"
    entry = settings.CELERY_BEAT_SCHEDULE["collect-trip-updates"]
    assert entry["task"] == collect_trip_updates.name
    assert entry["schedule"] > 0
    assert entry["options"]["expires"] == entry["schedule"]


def run_command(*args):
    out = StringIO()
    call_command("collect_trip_updates", *args, stdout=out)
    return out.getvalue()


def test_command_polls_all_feeds_and_reports(served, tram_pb, bus_pb):
    serve_all_krakow(served, tram_pb, bus_pb)

    output = run_command()

    assert f"krakow/{KRAKOW_TRAM_FEED}: ok" in output
    assert f"krakow/{KRAKOW_BUS_FEED}: ok" in output
    assert "stop_events=50" in output and "stop_events=95" in output
    assert StopEvent.objects.count() == 145


def test_command_city_option(served, tram_pb, bus_pb):
    serve_all_krakow(served, tram_pb, bus_pb)
    run_command("--city", "krakow")
    assert sorted(served.requested) == sorted(krakow_trip_update_urls().values())


def test_command_feed_option_polls_only_that_feed(served, tram_pb):
    served[TRAM_URL] = tram_pb

    output = run_command("--city", "krakow", "--feed", KRAKOW_TRAM_FEED)

    assert served.requested == [TRAM_URL]
    assert KRAKOW_BUS_FEED not in output
    assert StopEvent.objects.count() == 50


@pytest.mark.parametrize(
    "args",
    [
        ["--city", "warszawa"],  # configured, but has no TripUpdates feed
        ["--city", "atlantis"],
        ["--city", "krakow", "--feed", "no_such_feed"],
    ],
)
def test_command_without_matching_feed_fails_with_clear_error(served, args):
    with pytest.raises(CommandError, match="No matching"):
        run_command(*args)
    assert served.requested == []


def test_command_reports_failures_without_crashing(served):
    served[TRAM_URL] = b"not protobuf"

    output = run_command("--feed", KRAKOW_TRAM_FEED)

    assert "parse_error" in output
    assert "error=" in output


def test_command_loop_with_count_polls_repeatedly(served, tram_pb, monkeypatch):
    served[TRAM_URL] = tram_pb
    sleeps = []
    monkeypatch.setattr(
        "transit_data.management.commands.collect_trip_updates.time.sleep", sleeps.append
    )

    run_command("--feed", KRAKOW_TRAM_FEED, "--loop", "30", "--count", "3")

    assert served.requested == [TRAM_URL] * 3
    assert sleeps == [30.0, 30.0]
    # First poll stored events; the others saw the same header timestamp.
    assert list(FeedFetch.objects.order_by("id").values_list("status", flat=True)) == [
        "ok",
        "unchanged",
        "unchanged",
    ]


def test_command_dump_dir(served, tram_pb, tmp_path):
    served[TRAM_URL] = tram_pb
    run_command("--feed", KRAKOW_TRAM_FEED, "--dump-dir", str(tmp_path / "raw"))
    assert [p.read_bytes() for p in (tmp_path / "raw").glob("*.pb")] == [tram_pb]


def test_collector_module_exposes_trip_update_feeds_from_config():
    pairs = realtime.trip_update_feeds()
    assert {(c.id, f.id) for c, f in pairs} == {
        ("krakow", feed_id) for feed_id in krakow_trip_update_urls()
    }
    assert {KRAKOW_TRAM_FEED, KRAKOW_BUS_FEED} <= {f.id for _, f in pairs}
