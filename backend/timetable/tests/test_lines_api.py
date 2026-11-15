"""GET /cities/{city}/lines/ (docs/api.md, "Timetable (#10)")."""

import pytest

from .conftest import DAY_COLOUR, MAIN, NIGHT_COLOUR, SECOND

pytestmark = pytest.mark.django_db


def lines_by_id(api, **params):
    response = api.get("lines/", **params)
    assert response.status_code == 200
    return {item["id"]: item for item in response.json()}


def test_list_is_plain_array_with_documented_fields(api, dataset):
    response = api.get("lines/")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    item = next(i for i in body if i["id"] == f"{MAIN}:R10")
    assert item == {
        "id": f"{MAIN}:R10",
        "short_name": "10",
        "long_name": "Alpha - Delta",
        "vehicle_type": "tram",
        "group": "day",
        "colour": "#ff0000",
        "text_colour": "#ffffff",
        "notice": None,
    }


def test_notice_is_always_null(api, dataset):
    assert all(item["notice"] is None for item in api.get("lines/").json())


def test_only_active_versions_of_configured_feeds_are_used(api, dataset):
    ids = set(lines_by_id(api))
    assert f"{MAIN}:OLD" not in ids  # superseded version
    assert "not_in_config:ZZ" not in ids  # feed not in city config
    assert f"{SECOND}:B2" in ids  # second configured feed is merged in


def test_sorted_by_group_order_then_naturally(api, dataset):
    items = api.get("lines/").json()
    day = [i["short_name"] for i in items if i["group"] == "day"]
    numeric = [n for n in day if n.isdigit()]
    assert numeric == sorted(numeric, key=int)
    assert numeric[:3] == ["10", "20", "52"]
    order = ["day", "night", "agglomeration", "replacement"]
    group_positions = [order.index(i["group"]) for i in items]
    assert group_positions == sorted(group_positions)


def test_group_rules_by_feed_short_name_and_default(api, dataset):
    by_id = lines_by_id(api)
    assert by_id[f"{MAIN}:RN1"]["group"] == "night"
    assert by_id[f"{SECOND}:B2"]["group"] == "agglomeration"
    assert by_id[f"{MAIN}:R99"]["group"] == "replacement"  # bus 9x rule
    assert by_id[f"{MAIN}:R52"]["group"] == "day"  # no rule matches: first group


def test_group_ids_belong_to_city_line_groups(api, dataset):
    city = api.client.get("/api/v1/cities/ttville/").json()
    group_ids = {g["id"] for g in city["line_groups"]}
    assert {i["group"] for i in api.get("lines/").json()} <= group_ids


def test_route_colour_used_when_set(api, dataset):
    by_id = lines_by_id(api)
    assert by_id[f"{SECOND}:B3"]["colour"] == "#00aa00"
    assert by_id[f"{SECOND}:B3"]["text_colour"] in {"#ffffff", "#000000"}
    assert by_id[f"{MAIN}:R10"]["text_colour"] == "#ffffff"


def test_white_route_colour_counts_as_unset(api, dataset):
    line = lines_by_id(api)[f"{MAIN}:R52"]  # route_color FFFFFF, text 000000
    assert line["colour"] == DAY_COLOUR
    assert line["text_colour"] == "#ffffff"  # readable on the group colour


def test_black_route_colour_counts_as_unset(api, dataset):
    line = lines_by_id(api)[f"{MAIN}:RN1"]  # route_color 000000
    assert line["colour"] == NIGHT_COLOUR
    assert line["text_colour"] == "#000000"


def test_colours_are_lowercase_hex(api, dataset):
    for item in api.get("lines/").json():
        assert len(item["colour"]) == 7 and item["colour"].startswith("#")
        assert item["colour"] == item["colour"].lower()
        assert item["text_colour"] in {"#ffffff", "#000000"} or item["text_colour"].startswith("#")


def test_blank_short_name_falls_back_to_long_name_then_gtfs_id(api, dataset):
    by_id = lines_by_id(api)
    assert by_id[f"{MAIN}:RLONG"]["short_name"] == "Long Name Only"
    assert by_id[f"{MAIN}:RNONE"]["short_name"] == "RNONE"


@pytest.mark.parametrize("vehicle_type", ["tram", "bus", "metro", "rail"])
def test_vehicle_type_filter(api, dataset, vehicle_type):
    items = api.get("lines/", vehicle_type=vehicle_type).json()
    assert all(i["vehicle_type"] == vehicle_type for i in items)


def test_vehicle_type_filter_contents(api, dataset):
    assert {i["short_name"] for i in api.get("lines/", vehicle_type="metro").json()} == {"M1"}
    buses = {i["short_name"] for i in api.get("lines/", vehicle_type="bus").json()}
    assert {"N1", "99", "77", "2", "3"} <= buses
    assert "10" not in buses


def test_empty_result_for_type_without_lines(api, dataset):
    response = api.get("lines/", vehicle_type="rail")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("value", ["boat", "TRAM", "1"])
def test_bad_vehicle_type_is_400(api, dataset, value):
    response = api.get("lines/", vehicle_type=value)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "vehicle_type" in error["details"]


def test_city_without_imported_feeds_returns_empty_list(api, city_config, db):
    response = api.get("lines/")
    assert response.status_code == 200
    assert response.json() == []


def test_unknown_city_is_404(api, dataset):
    response = api.get("lines/", city="atlantis")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_no_authentication_needed(api, dataset):
    assert api.get("lines/").status_code == 200


def test_post_not_allowed(api, dataset):
    assert api.client.post("/api/v1/cities/ttville/lines/", {}, format="json").status_code == 405
