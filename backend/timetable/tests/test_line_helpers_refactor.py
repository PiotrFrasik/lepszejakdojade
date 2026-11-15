"""Regression tests for line_colours and lines_by_id (extracted for journey search)."""

import pytest

from cities.registry import get_city
from timetable.lines import Feeds, line_colours, lines_by_id
from timetable.tests.conftest import CITY, DAY_COLOUR, NIGHT_COLOUR

pytestmark = pytest.mark.django_db


@pytest.fixture
def city(dataset):
    return get_city(CITY)


def group(city, group_id):
    return next(g for g in city.line_groups if g.id == group_id)


def test_line_colours_uses_route_colour(city):
    assert line_colours("FF0000", "FFFFFF", group(city, "day")) == ("#ff0000", "#ffffff")


def test_line_colours_lowercases_hex(city):
    assert line_colours("AbCdEf", "123ABC", group(city, "day")) == ("#abcdef", "#123abc")


def test_line_colours_missing_text_colour_is_computed(city):
    assert line_colours("FFFF00", "", group(city, "day")) == ("#ffff00", "#000000")
    assert line_colours("000080", None, group(city, "day")) == ("#000080", "#ffffff")


@pytest.mark.parametrize("unset", ["FFFFFF", "000000", "ffffff", "", None])
def test_line_colours_unset_route_colour_uses_group(city, unset):
    colour, _ = line_colours(unset, "AAAAAA", group(city, "night"))
    assert colour == NIGHT_COLOUR


def test_line_colours_group_text_colour_is_readable(city):
    assert line_colours(None, None, group(city, "day")) == (DAY_COLOUR, "#ffffff")
    assert line_colours(None, None, group(city, "night"))[1] == "#000000"


def test_lines_by_id_returns_known_lines_only(city):
    result = lines_by_id(
        city, Feeds(city), ["tt_main:R10", "tt_main:NOPE", "garbage", "unknown_feed:R10"]
    )
    assert set(result) == {"tt_main:R10"}
    assert result["tt_main:R10"].summary()["short_name"] == "10"


def test_lines_by_id_across_feeds(city):
    result = lines_by_id(city, Feeds(city), ["tt_main:R10", "tt_second:B3"])
    assert set(result) == {"tt_main:R10", "tt_second:B3"}
    assert result["tt_second:B3"].summary()["colour"] == "#00aa00"


def test_lines_by_id_ignores_unconfigured_and_superseded_routes(city):
    assert lines_by_id(city, Feeds(city), ["not_in_config:ZZ", "tt_main:OLD"]) == {}


def test_lines_by_id_empty_input(city):
    assert lines_by_id(city, Feeds(city), []) == {}
