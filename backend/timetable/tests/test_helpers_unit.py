"""Pure helpers: natural sort, readable text colour, ids, calendar time formats."""

from datetime import date
from zoneinfo import ZoneInfo

import pytest

from timetable.calendar import clock_time, gtfs_timestamp
from timetable.lines import make_id, natural_key, parse_id, readable_text_colour

WARSAW = ZoneInfo("Europe/Warsaw")


def test_natural_sort_orders_numbers_numerically_and_before_letters():
    names = ["N1", "52", "10", "2", "L-10", "L-1", "M1", "103", "3"]
    expected = ["2", "3", "10", "52", "103", "L-1", "L-10", "M1", "N1"]
    assert sorted(names, key=natural_key) == expected


def test_natural_sort_is_case_insensitive_and_ignores_separators():
    assert natural_key("L-1") == natural_key("L1")
    assert natural_key("n1") == natural_key("N1")


def test_readable_text_colour():
    assert readable_text_colour("#112233") == "#ffffff"
    assert readable_text_colour("#f0e68c") == "#000000"
    assert readable_text_colour("#ffffff") == "#000000"
    assert readable_text_colour("#000000") == "#ffffff"


def test_id_round_trip_keeps_colons_in_gtfs_id():
    assert make_id("ztp_tram", "a:b") == "ztp_tram:a:b"
    assert parse_id("ztp_tram:a:b") == ("ztp_tram", "a:b")


@pytest.mark.parametrize("value", ["", "nocolon", ":x", "x:"])
def test_malformed_ids_are_rejected(value):
    assert parse_id(value) is None


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, ("00:00", False)),
        (5 * 3600 + 12 * 60, ("05:12", False)),
        (23 * 3600 + 59 * 60, ("23:59", False)),
        (24 * 3600 + 15 * 60, ("00:15", True)),
        (25 * 3600 + 5 * 60 + 59, ("01:05", True)),
    ],
)
def test_clock_time(seconds, expected):
    assert clock_time(seconds) == expected


def test_gtfs_timestamp_has_offset_and_rolls_over_midnight():
    assert gtfs_timestamp(date(2026, 11, 16), 5 * 3600 + 12 * 60, WARSAW) == (
        "2026-11-16T05:12:00+01:00"
    )
    assert gtfs_timestamp(date(2026, 11, 16), 24 * 3600 + 15 * 60, WARSAW) == (
        "2026-11-17T00:15:00+01:00"
    )
    assert gtfs_timestamp(date(2026, 7, 6), 8 * 3600, WARSAW) == "2026-07-06T08:00:00+02:00"
    assert gtfs_timestamp(date(2026, 7, 6), None, WARSAW) is None


def test_gtfs_timestamp_on_dst_change_days():
    assert gtfs_timestamp(date(2026, 3, 29), 8 * 3600, WARSAW) == "2026-03-29T08:00:00+02:00"
    assert gtfs_timestamp(date(2026, 10, 25), 8 * 3600, WARSAW) == "2026-10-25T08:00:00+01:00"
