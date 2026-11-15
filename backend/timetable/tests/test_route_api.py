"""GET /cities/{city}/lines/{line_id}/route/ (docs/api.md, "Timetable (#10)")."""

import pytest

from .conftest import FRIDAY, MAIN, MONDAY, SATURDAY, SUNDAY

pytestmark = pytest.mark.django_db

LINE = f"{MAIN}:R10"


def route(api, line=LINE, **params):
    return api.get(f"lines/{line}/route/", **params)


def sid(gtfs_id):
    return f"{MAIN}:{gtfs_id}"


def variant_by_kind(body, kind):
    return [v for v in body["variants"] if v["kind"] == kind]


def stop_by_id(body, gtfs_id):
    return next(s for s in body["stops"] if s["stop_id"] == sid(gtfs_id))


def test_response_shape(api, dataset):
    response = route(api, date=MONDAY)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"line", "direction", "date", "directions", "stops", "variants", "shape"}
    assert body["line"]["id"] == LINE
    assert body["direction"] == 0
    assert body["date"] == MONDAY
    stop = body["stops"][0]
    assert set(stop) == {
        "stop_id", "name", "code", "lat", "lon", "wheelchair_boarding", "variant_only",
        "transfers",
    }  # fmt: skip


def test_direction_defaults_to_zero(api, dataset):
    assert route(api, date=MONDAY).json() == route(api, date=MONDAY, direction=0).json()


def test_directions_list_both_with_most_common_headsign(api, dataset):
    body = route(api, date=MONDAY).json()
    assert body["directions"] == [
        {"direction": 0, "headsign": "Terminus A"},
        {"direction": 1, "headsign": "Start place"},
    ]


def test_direction_one_stops_in_reverse_order(api, dataset):
    body = route(api, date=MONDAY, direction=1).json()
    assert body["direction"] == 1
    assert [s["stop_id"] for s in body["stops"]] == [sid(x) for x in ("S4", "S3", "S2", "S1")]


def test_main_variant_stops_in_order_with_variant_only_stops_inserted(api, dataset):
    body = route(api, date=MONDAY).json()
    ids = [s["stop_id"] for s in body["stops"]]
    main = next(v for v in body["variants"] if v["kind"] == "main")
    assert main["stop_ids"] == [sid(x) for x in ("S1", "S2", "S3", "S4")]
    # main stops keep their order
    assert [i for i in ids if i in main["stop_ids"]] == main["stop_ids"]
    only = {s["stop_id"] for s in body["stops"] if s["variant_only"]}
    assert only == {sid("D"), sid("X")}
    assert not any(stop_by_id(body, x)["variant_only"] for x in ("S1", "S2", "S3", "S4"))
    # depot stop precedes S1, X sits between S1 and S3
    assert ids.index(sid("D")) < ids.index(sid("S1"))
    assert ids.index(sid("S1")) < ids.index(sid("X")) < ids.index(sid("S3"))


def test_variants_main_first_with_kinds_and_counts(api, dataset):
    body = route(api, date=MONDAY).json()
    variants = body["variants"]
    assert variants[0]["kind"] == "main"
    assert variants[0]["trip_count"] == 5
    assert len({v["id"] for v in variants}) == len(variants)
    kinds = sorted(v["kind"] for v in variants)
    assert kinds == ["depot", "main", "other", "short_turn"]
    short = variant_by_kind(body, "short_turn")[0]
    assert short["stop_ids"] == [sid("S2"), sid("S3")]
    assert short["trip_count"] == 2
    assert short["headsign"] == "Gamma short"
    depot = variant_by_kind(body, "depot")[0]
    assert depot["stop_ids"][0] == sid("D")
    other = variant_by_kind(body, "other")[0]
    assert sid("X") in other["stop_ids"]
    assert other["headsign"] == "Via Xi"
    assert variants[0]["headsign"] == "Terminus A"


def test_variants_use_only_trips_running_on_the_date(api, dataset):
    body = route(api, date=SUNDAY).json()
    assert [v["kind"] for v in body["variants"]] == ["main"]
    assert body["variants"][0]["trip_count"] == 1
    assert body["date"] == SUNDAY
    assert not any(s["variant_only"] for s in body["stops"])


def test_date_falls_forward_to_next_day_with_service(api, dataset):
    # Direction 1 only runs on weekdays: a Saturday request answers with Monday.
    body = route(api, direction=1, date=SATURDAY).json()
    assert body["date"] == "2026-11-23"  # the next Monday
    assert [s["stop_id"] for s in body["stops"]][0] == sid("S4")


def test_date_is_kept_when_it_has_service(api, dataset):
    assert route(api, direction=1, date=FRIDAY).json()["date"] == FRIDAY


def test_default_date_is_today_or_next_service_day(api, dataset):
    body = route(api).json()
    assert len(body["date"]) == 10 and body["date"][4] == "-"


def test_wheelchair_boarding_and_code(api, dataset):
    body = route(api, date=MONDAY).json()
    assert stop_by_id(body, "S1")["wheelchair_boarding"] is True
    assert stop_by_id(body, "S2")["wheelchair_boarding"] is False
    assert stop_by_id(body, "S3")["wheelchair_boarding"] is None
    assert stop_by_id(body, "S1")["code"] == "01"
    assert stop_by_id(body, "S2")["code"] is None  # GTFS has none


def test_stop_coordinates(api, dataset):
    s1 = stop_by_id(route(api, date=MONDAY).json(), "S1")
    assert s1["lat"] == pytest.approx(50.06, abs=1e-5)
    assert s1["lon"] == pytest.approx(19.94, abs=1e-5)


def test_transfers_same_stop_same_name_within_300_m_sorted(api, dataset):
    s3 = stop_by_id(route(api, date=MONDAY).json(), "S3")
    # N1 stops at S3 itself, 52 at S3b (same name, ~100 m). Day group sorts before night.
    assert [t["short_name"] for t in s3["transfers"]] == ["52", "N1"]


def test_transfers_exclude_far_same_name_and_near_other_name_and_own_line(api, dataset):
    s3 = stop_by_id(route(api, date=MONDAY).json(), "S3")
    names = {t["short_name"] for t in s3["transfers"]}
    assert "99" not in names  # same name but ~500 m away
    assert "77" not in names  # ~50 m away but different name
    assert "10" not in names  # the line itself


def test_transfers_are_line_summaries_of_any_vehicle_type(api, dataset):
    s1 = stop_by_id(route(api, date=MONDAY).json(), "S1")
    metro = next(t for t in s1["transfers"] if t["short_name"] == "M1")
    assert metro["vehicle_type"] == "metro"
    assert set(metro) == {"id", "short_name", "vehicle_type", "group", "colour", "text_colour"}


def test_transfers_empty_when_no_other_line(api, dataset):
    body = route(api, date=MONDAY).json()
    assert stop_by_id(body, "X")["transfers"] == []


def test_transfers_stable_when_cache_is_warm(api, dataset):
    first = route(api, date=MONDAY).json()
    second = route(api, date=MONDAY).json()
    assert first["stops"] == second["stops"]


def test_shape_uses_gtfs_shape(api, dataset):
    shape = route(api, date=MONDAY).json()["shape"]
    assert shape["type"] == "LineString"
    assert shape["coordinates"] == [[19.94, 50.06], [19.95, 50.07], [19.96, 50.08]]


def test_shape_falls_back_to_straight_lines_between_stops(api, dataset):
    shape = route(api, direction=1, date=MONDAY).json()["shape"]  # trips without shape
    assert shape["type"] == "LineString"
    assert len(shape["coordinates"]) == 4
    lon, lat = shape["coordinates"][0]  # S4 comes first in direction 1
    assert lat > 50.06 and lon == pytest.approx(19.94, abs=1e-5)  # [lon, lat] order
    assert shape["coordinates"][-1] == [19.94, 50.06]


def test_trips_without_direction_id_count_as_direction_zero(api, dataset):
    line = f"{MAIN}:R20"
    body = route(api, line=line, date=MONDAY).json()
    assert body["directions"] == [{"direction": 0, "headsign": "Beta end"}]
    assert [s["stop_id"] for s in body["stops"]] == [sid("S1"), sid("S2")]
    assert route(api, line=line, direction=1, date=MONDAY).status_code == 404


def test_blank_headsign_variant_falls_back_to_last_stop_name(api, dataset):
    body = route(api, line=f"{MAIN}:RBLK", date=MONDAY).json()
    assert body["variants"][0]["headsign"] == "Beta"


def test_blank_headsign_direction_falls_back_to_last_stop_name(api, dataset):
    body = route(api, line=f"{MAIN}:RBLK", date=MONDAY).json()
    assert body["directions"][0]["headsign"] == "Beta"


def test_direction_without_trips_is_404(api, dataset):
    response = route(api, line=f"{MAIN}:R52", direction=1, date=MONDAY)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_line_without_trips_is_404(api, dataset):
    assert route(api, line=f"{MAIN}:RNONE", date=MONDAY).status_code == 404


@pytest.mark.parametrize("line", ["nope", f"{MAIN}:missing", "unknown_feed:R10", f"{MAIN}:OLD"])
def test_unknown_line_is_404(api, dataset, line):
    assert route(api, line=line, date=MONDAY).status_code == 404


def test_line_of_feed_outside_city_is_404(api, dataset):
    assert route(api, line="not_in_config:ZZ", date=MONDAY).status_code == 404


@pytest.mark.parametrize("value", ["2", "-1", "x", "0.5"])
def test_bad_direction_is_400(api, dataset, value):
    response = route(api, direction=value, date=MONDAY)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "direction" in error["details"]


@pytest.mark.parametrize("value", ["2026-13-01", "16-11-2026", "2026/11/16", "tomorrow"])
def test_bad_date_is_400(api, dataset, value):
    response = route(api, date=value)
    assert response.status_code == 400
    assert "date" in response.json()["error"]["details"]


def test_date_far_in_future_is_400_not_500(api, dataset):
    assert route(api, date="9999-12-31").status_code == 400


def test_unknown_city_is_404(api, dataset):
    assert route(api, date=MONDAY).status_code == 200
    assert api.get(f"lines/{LINE}/route/", city="atlantis").status_code == 404
