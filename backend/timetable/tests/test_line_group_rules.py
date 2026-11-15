"""Line group rules: registry validation and matching (city config, never in code)."""

import copy

import pytest

from cities import registry
from cities.registry import CityConfigError, parse_city


def base_data():
    return {
        "id": "testville",
        "names": {"pl": "Testowo", "en": "Testville"},
        "timezone": "Europe/Warsaw",
        "map": {"center": {"lat": 50.0, "lon": 19.9}, "zoom": 12},
        "vehicle_types": ["tram", "bus"],
        "line_groups": [
            {"id": "day", "names": {"pl": "Dzienne", "en": "Day"}, "colour": "#112233"},
            {"id": "night", "names": {"pl": "Nocne", "en": "Night"}, "colour": "#223344"},
            {"id": "other", "names": {"pl": "Inne", "en": "Other"}, "colour": "#334455"},
        ],
        "realtime": {"departures": True, "vehicles": False},
        "feeds": {"gtfs_static": [], "gtfs_rt": [], "other": []},
        "ticket_zones": [],
        "attributions": [{"name": "Operator", "url": "https://example.com/", "licence": None}],
    }


def city_with(rules):
    data = base_data()
    if rules is not None:
        data["line_group_rules"] = rules
    return parse_city(data, "test")


def test_rules_are_optional_and_default_to_first_group():
    city = city_with(None)
    assert city.line_group_rules == ()
    assert city.line_group_for("tram", "any_feed", "52").id == "day"


def test_first_matching_rule_wins():
    city = city_with(
        [
            {"group": "night", "short_name": "N\\d+"},
            {"group": "other", "vehicle_types": ["bus"]},
        ]
    )
    assert city.line_group_for("bus", "f", "N12").id == "night"
    assert city.line_group_for("bus", "f", "123").id == "other"


def test_unmatched_line_goes_to_first_group():
    city = city_with([{"group": "night", "short_name": "N\\d+"}])
    assert city.line_group_for("tram", "f", "52").id == "day"


def test_short_name_pattern_must_match_whole_name():
    city = city_with([{"group": "night", "short_name": "6\\d"}])
    assert city.line_group_for("tram", "f", "62").id == "night"
    assert city.line_group_for("tram", "f", "62A").id == "day"
    assert city.line_group_for("tram", "f", "162").id == "day"


def test_all_given_criteria_must_match():
    city = city_with([{"group": "night", "vehicle_types": ["bus"], "feeds": ["f1"]}])
    assert city.line_group_for("bus", "f1", "1").id == "night"
    assert city.line_group_for("tram", "f1", "1").id == "day"
    assert city.line_group_for("bus", "f2", "1").id == "day"


def test_rule_may_name_feed_or_vehicle_type_city_does_not_have():
    city = city_with([{"group": "night", "vehicle_types": ["rail"], "feeds": ["unknown_feed"]}])
    assert city.line_group_for("rail", "unknown_feed", "S1").id == "night"


@pytest.mark.parametrize(
    "rule",
    [
        {"group": "nope"},
        {"group": "night", "vehicle_types": ["boat"]},
        {"group": "night", "short_name": "(unclosed"},
        {"group": "night", "unexpected": 1},
        {"vehicle_types": ["bus"]},
        {"group": "night", "vehicle_types": "bus"},
        {"group": "night", "feeds": "f1"},
        {"group": "night", "short_name": 5},
    ],
)
def test_invalid_rule_is_rejected(rule):
    with pytest.raises(CityConfigError):
        city_with([rule])


def test_rules_must_be_a_list():
    with pytest.raises(CityConfigError):
        city_with({"group": "night"})


def test_rule_source_data_is_not_mutated():
    data = base_data()
    data["line_group_rules"] = [{"group": "night", "short_name": "N\\d+"}]
    snapshot = copy.deepcopy(data)
    parse_city(data, "test")
    assert data == snapshot


@pytest.fixture
def shipped():
    registry.clear_cache()
    yield {c.id: c for c in registry.all_cities()}
    registry.clear_cache()


@pytest.mark.parametrize(
    "city,vehicle,feed,short_name,group",
    [
        ("krakow", "tram", "ztp_tram", "52", "day"),
        ("krakow", "tram", "ztp_tram", "62", "night"),
        ("krakow", "tram", "ztp_tram", "72", "replacement"),
        ("krakow", "bus", "ztp_bus", "304", "day"),
        ("krakow", "bus", "ztp_bus", "601", "night"),
        ("krakow", "bus", "ztp_bus", "701", "replacement"),
        ("krakow", "bus", "ztp_bus", "201", "agglomeration"),
        ("krakow", "bus", "ztp_mobilis_bus", "304", "agglomeration"),
        ("krakow", "rail", "rail", "SKA1", "agglomeration"),
        ("warszawa", "bus", "ztm_bus", "175", "day"),
        ("warszawa", "bus", "ztm_bus", "N12", "night"),
        ("warszawa", "bus", "ztm_bus", "Z-1", "replacement"),
        ("warszawa", "bus", "ztm_bus", "525", "express"),
        ("warszawa", "bus", "ztm_bus", "E-2", "express"),
        ("warszawa", "bus", "ztm_bus", "L-3", "suburban"),
        ("warszawa", "bus", "ztm_bus", "712", "suburban"),
        ("warszawa", "rail", "any", "S1", "suburban"),
        ("warszawa", "metro", "ztm_metro", "M1", "day"),
        ("warszawa", "tram", "ztm_tram", "17", "day"),
    ],
)
def test_shipped_city_rules(shipped, city, vehicle, feed, short_name, group):
    assert shipped[city].line_group_for(vehicle, feed, short_name).id == group


def test_shipped_rules_reference_existing_groups(shipped):
    for city in shipped.values():
        ids = {g.id for g in city.line_groups}
        assert all(rule.group in ids for rule in city.line_group_rules)
