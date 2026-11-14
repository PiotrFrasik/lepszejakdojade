"""Static GTFS import of a feed with an area filter (issue #43). No network."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import yaml
from django.conf import settings

from cities import registry
from cities.registry import FeedFilter, get_city
from transit_data.models import (
    Agency,
    FeedVersion,
    Route,
    Shape,
    Stop,
    StopTime,
    Trip,
)
from transit_data.static_gtfs import download
from transit_data.static_gtfs.pipeline import Outcome, import_city, import_feed

from .gtfs_support import CITY, FEED, FakeServer, zip_directory

RAIL_AREA = Path(__file__).resolve().parent.parent / "fixtures" / "gtfs" / "rail_area"

BBOX = [19.80, 49.95, 20.10, 50.15]
NOWHERE = [0.0, 0.0, 1.0, 1.0]

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("gtfs_city")]


# The shipped fixture has a platform without coordinates; the loader gives it its parent's.
FEED_DIR: list[Path] = [RAIL_AREA]


def test_shipped_fixture_with_coordinate_less_platform_imports_cleanly(filtered):
    result = run(path=RAIL_AREA)
    assert result.outcome == Outcome.IMPORTED, result.message
    version = FeedVersion.objects.get(pk=result.feed_version_id)
    platform = Stop.objects.get(feed_version=version, gtfs_id="KGL_2")
    assert platform.point.x == pytest.approx(19.947)
    assert platform.point.y == pytest.approx(50.068)
    corrections = version.report["files"]["stops.txt"]["corrections"]
    assert corrections == {"missing or invalid coordinates, used the parent station's": 1}


def set_filter(filter_config: dict | None) -> None:
    """Rewrite the gtfsville city config so ``gv_main`` carries the given filter."""
    path = Path(settings.CITY_CONFIG_DIR) / "gtfsville.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    feed = data["feeds"]["gtfs_static"][0]
    assert feed["id"] == FEED
    feed.pop("filter", None)
    if filter_config is not None:
        feed["filter"] = filter_config
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    registry.clear_cache()


def run(force=False, path=None):
    (result,) = import_city(CITY, FEED, force=force, file=path or FEED_DIR[0])
    return result


@pytest.fixture
def filtered():
    set_filter({"bbox": BBOX, "exclude_agencies": ["SKM"]})


def counts(version):
    return {
        model.__name__: model.objects.filter(feed_version=version).count()
        for model in (Agency, Stop, Route, Trip, StopTime, Shape)
    }


# ----------------------------------------------------------------------- filter applied


def test_filter_is_applied_before_loading(filtered):
    result = run()
    assert result.outcome == Outcome.IMPORTED, result.message
    version = FeedVersion.objects.get(pk=result.feed_version_id)
    assert counts(version) == {
        "Agency": 2,
        "Stop": 5,
        "Route": 2,
        "Trip": 2,
        "StopTime": 5,
        "Shape": 2,  # SH_S1 and SH_IC; SH_BUS is only used by a dropped trip
    }
    assert version.report["counts"]["trips"] == 2
    assert version.report["counts"]["stop_times"] == 5


def test_stops_in_database_are_only_the_filtered_ones(filtered):
    version = FeedVersion.objects.get(pk=run().feed_version_id)
    gtfs_ids = set(Stop.objects.filter(feed_version=version).values_list("gtfs_id", flat=True))
    assert gtfs_ids == {"KGL", "KGL_1", "KGL_2", "KPL", "WIE"}
    trips = set(Trip.objects.filter(feed_version=version).values_list("gtfs_id", flat=True))
    assert trips == {"T_S1_1", "T_IC_1"}


def test_unfiltered_feed_imports_everything():
    set_filter(None)
    result = run()
    assert result.outcome == Outcome.IMPORTED, result.message
    version = FeedVersion.objects.get(pk=result.feed_version_id)
    assert Trip.objects.filter(feed_version=version).count() == 5
    assert version.report["area_filter"] == {}


def test_report_records_area_filter(filtered):
    version = FeedVersion.objects.get(pk=run().feed_version_id)
    area = version.report["area_filter"]
    assert area["config"] == {
        "bbox": BBOX,
        "exclude_agencies": ["SKM"],
        "min_stops_in_area": 2,
    }
    assert area["files"]["trips.txt"] == {"read": 5, "kept": 2}
    assert area["trips_excluded_agency"] == 1
    assert area["trips_outside_area"] == 2


def test_report_is_formatted_with_the_filter_line(filtered):
    from transit_data.static_gtfs.report import format_report

    version = FeedVersion.objects.get(pk=run().feed_version_id)
    text = "\n".join(format_report(version.report))
    assert "area filter" in text
    assert "trips 2/5" in text


# ------------------------------------------------------------------ change detection


def test_same_file_and_same_filter_is_unchanged(filtered):
    first = run()
    second = run()
    assert second.outcome == Outcome.UNCHANGED
    assert FeedVersion.objects.filter(city_id=CITY, feed_id=FEED).count() == 1
    assert FeedVersion.objects.get(pk=first.feed_version_id).status == FeedVersion.Status.ACTIVE


def test_changed_filter_triggers_a_reimport_of_the_same_file(filtered):
    first = run()
    set_filter({"bbox": BBOX})  # SKM no longer excluded: one more trip
    second = run()
    assert second.outcome == Outcome.IMPORTED, second.message
    assert second.feed_version_id != first.feed_version_id
    new = FeedVersion.objects.get(pk=second.feed_version_id)
    assert new.status == FeedVersion.Status.ACTIVE
    assert Trip.objects.filter(feed_version=new).count() == 3
    old = FeedVersion.objects.get(pk=first.feed_version_id)
    assert old.status != FeedVersion.Status.ACTIVE


def test_adding_a_filter_to_a_previously_unfiltered_feed_reimports():
    set_filter(None)
    first = run()
    set_filter({"bbox": BBOX, "exclude_agencies": ["SKM"]})
    second = run()
    assert second.outcome == Outcome.IMPORTED, second.message
    assert Trip.objects.filter(feed_version_id=second.feed_version_id).count() == 2
    assert first.feed_version_id != second.feed_version_id


def test_removing_the_filter_reimports_everything(filtered):
    run()
    set_filter(None)
    result = run()
    assert result.outcome == Outcome.IMPORTED, result.message
    assert Trip.objects.filter(feed_version_id=result.feed_version_id).count() == 5


def test_smaller_area_after_filter_change_is_not_rejected_by_size_check():
    # 5 stop_times against 12 in the active version is below the 50 % limit, which would
    # normally be rejected as a truncated feed; a changed area is legitimate.
    set_filter({"bbox": [19.0, 49.0, 21.5, 52.5], "exclude_agencies": ["SKM"]})
    wide = run()
    assert Trip.objects.filter(feed_version_id=wide.feed_version_id).count() == 4
    assert StopTime.objects.filter(feed_version_id=wide.feed_version_id).count() == 12
    set_filter({"bbox": BBOX, "exclude_agencies": ["SKM"]})
    result = run()
    assert result.outcome == Outcome.IMPORTED, result.message
    assert FeedVersion.objects.get(pk=result.feed_version_id).report["comparison"] == {}


def test_conditional_get_is_not_used_when_the_filter_changed(monkeypatch, filtered):
    body = zip_directory(FEED_DIR[0])
    server = FakeServer(body, etag='"v1"')
    monkeypatch.setattr(download.urllib.request, "urlopen", server)
    (first,) = import_city(CITY, FEED)
    assert first.outcome == Outcome.IMPORTED, first.message
    # Same file: the second request is conditional and answers 304.
    (second,) = import_city(CITY, FEED)
    assert second.outcome == Outcome.UNCHANGED
    assert server.requests[-1].get_header("If-none-match") == '"v1"'
    # Changed filter: the file is fetched again unconditionally and imported.
    set_filter({"bbox": BBOX})
    (third,) = import_city(CITY, FEED)
    assert third.outcome == Outcome.IMPORTED, third.message
    assert server.requests[-1].get_header("If-none-match") is None


# ----------------------------------------------------------------------- idempotency


def test_forced_reimport_does_not_duplicate_rows(filtered):
    first = run()
    second = run(force=True)
    assert second.outcome == Outcome.IMPORTED, second.message
    new = FeedVersion.objects.get(pk=second.feed_version_id)
    assert counts(new) == counts(FeedVersion.objects.get(pk=first.feed_version_id))
    # Rows are scoped to their version: the total is the sum of both versions.
    assert Trip.objects.count() == 4
    assert StopTime.objects.count() == 10


def test_filtered_import_is_deterministic(filtered):
    first = run()
    second = run(force=True)

    def stop_times(version_id):
        rows = StopTime.objects.filter(feed_version_id=version_id)
        return sorted(
            rows.values_list("trip__gtfs_id", "stop__gtfs_id", "arrival_time", "departure_time")
        )

    assert stop_times(first.feed_version_id) == stop_times(second.feed_version_id)


# ------------------------------------------------------------------------- failures


def test_empty_result_fails_and_keeps_the_active_version(filtered):
    first = run()
    set_filter({"bbox": NOWHERE})
    result = run()
    assert result.outcome == Outcome.FAILED
    failed = FeedVersion.objects.get(pk=result.feed_version_id)
    assert failed.status == FeedVersion.Status.FAILED
    assert failed.data_error is True
    assert "no trip" in failed.error
    assert FeedVersion.objects.get(pk=first.feed_version_id).status == FeedVersion.Status.ACTIVE
    assert Trip.objects.filter(feed_version_id=first.feed_version_id).count() == 2


def test_empty_result_on_first_import_leaves_no_active_version():
    set_filter({"bbox": NOWHERE})
    result = run()
    assert result.outcome == Outcome.FAILED
    assert not FeedVersion.objects.filter(status=FeedVersion.Status.ACTIVE).exists()
    assert Trip.objects.count() == 0


def test_invalid_filter_fails_and_keeps_the_active_version(filtered):
    first = run()
    city = get_city(CITY)
    feed = next(f for f in city.feeds if f.id == FEED)
    broken = dataclasses.replace(feed, filter=FeedFilter(bbox=(20.0, 50.0, 19.0, 51.0)))
    result = import_feed(city, broken, file=FEED_DIR[0])
    assert result.outcome == Outcome.FAILED
    assert "invalid filter" in result.message
    failed = FeedVersion.objects.get(pk=result.feed_version_id)
    assert failed.status == FeedVersion.Status.FAILED
    assert FeedVersion.objects.get(pk=first.feed_version_id).status == FeedVersion.Status.ACTIVE


def test_same_file_failed_with_same_filter_is_not_retried(filtered):
    set_filter({"bbox": NOWHERE})
    first = run()
    assert first.outcome == Outcome.FAILED
    again = run()
    assert again.outcome == Outcome.UNCHANGED
    assert "failed version" in again.message
    assert FeedVersion.objects.filter(status=FeedVersion.Status.FAILED).count() == 1


def test_same_file_failed_with_another_filter_is_retried():
    set_filter({"bbox": NOWHERE})
    assert run().outcome == Outcome.FAILED
    set_filter({"bbox": BBOX, "exclude_agencies": ["SKM"]})
    result = run()
    assert result.outcome == Outcome.IMPORTED, result.message


def test_force_retries_a_failed_file_with_the_same_filter():
    set_filter({"bbox": NOWHERE})
    run()
    again = run(force=True)
    assert again.outcome == Outcome.FAILED
    assert FeedVersion.objects.filter(status=FeedVersion.Status.FAILED).count() == 2


def test_filter_is_not_applied_to_other_feeds_of_the_city(filtered):
    # gv_second has no filter; importing it from the same fixture keeps all five trips.
    (result,) = import_city(CITY, "gv_second", file=FEED_DIR[0])
    assert result.outcome == Outcome.IMPORTED, result.message
    assert Trip.objects.filter(feed_version_id=result.feed_version_id).count() == 5


def test_oversized_archive_fails_as_a_data_error_and_keeps_the_active_version(filtered, settings):
    first = run()
    settings.TRANSIT_GTFS_MAX_UNCOMPRESSED_BYTES = 10
    result = run(force=True)
    assert result.outcome == Outcome.FAILED
    assert "exceeds the limit" in result.message
    failed = FeedVersion.objects.get(pk=result.feed_version_id)
    assert failed.status == FeedVersion.Status.FAILED
    assert failed.data_error is True
    assert FeedVersion.objects.get(pk=first.feed_version_id).status == FeedVersion.Status.ACTIVE
