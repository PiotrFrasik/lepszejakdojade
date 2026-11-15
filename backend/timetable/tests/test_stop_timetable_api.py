"""GET /cities/{city}/lines/{line_id}/stops/{stop_id}/timetable/ (docs/api.md, #10)."""

import pytest

from .conftest import (
    FRIDAY,
    HOLIDAY,
    MAIN,
    MONDAY,
    SATURDAY,
    SUNDAY,
    Builder,
    today_in_city,
)

pytestmark = pytest.mark.django_db

LINE = f"{MAIN}:R10"


def sid(gtfs_id):
    return f"{MAIN}:{gtfs_id}"


def timetable(api, stop="S1", line=LINE, **params):
    return api.get(f"lines/{line}/stops/{sid(stop)}/timetable/", **params)


def body_of(api, stop="S1", line=LINE, **params):
    response = timetable(api, stop, line, **params)
    assert response.status_code == 200, response.content
    return response.json()


def column(body, day_type):
    return next(c for c in body["columns"] if c["day_type"] == day_type)


def times(body, day_type):
    """Flat list of ``HH:MM`` of one column, in response order."""
    return [d["time"] for h in column(body, day_type)["hours"] for d in h["departures"]]


def departures(body, day_type):
    return [d for h in column(body, day_type)["hours"] for d in h["departures"]]


def test_response_shape(api, dataset):
    body = body_of(api, "S2", date=MONDAY)
    assert set(body) == {
        "line", "stop", "direction", "headsign", "date", "day_type", "previous_stop",
        "next_stop", "columns", "variants",
    }  # fmt: skip
    assert body["line"]["id"] == LINE
    assert body["stop"] == {"stop_id": sid("S2"), "name": "Beta", "code": None}
    assert body["direction"] == 0
    assert body["headsign"] == "Terminus A"
    assert body["date"] == MONDAY
    departure = departures(body, "weekday")[0]
    assert set(departure) == {
        "minute", "time", "next_day", "trip_id", "headsign", "markers", "variant"
    }  # fmt: skip


def test_stop_code_is_returned_when_present(api, dataset):
    assert body_of(api, "S1", date=MONDAY)["stop"]["code"] == "01"


def test_three_columns_in_fixed_order(api, dataset):
    body = body_of(api, date=MONDAY)
    assert [c["day_type"] for c in body["columns"]] == ["weekday", "saturday", "sunday"]
    assert [c["date"] for c in body["columns"]] == [MONDAY, SATURDAY, SUNDAY]
    assert body["day_type"] == "weekday"


def test_column_content_per_day_type(api, dataset):
    body = body_of(api, date=MONDAY)
    assert times(body, "saturday") == ["07:00"]
    assert times(body, "sunday") == ["08:00"]
    assert "07:00" in times(body, "weekday")
    assert "08:00" not in times(body, "weekday")


@pytest.mark.parametrize(
    "request_date,top,weekday,saturday,sunday",
    [
        (FRIDAY, "weekday", FRIDAY, SATURDAY, SUNDAY),
        (SATURDAY, "saturday", "2026-11-23", SATURDAY, SUNDAY),
        (SUNDAY, "sunday", "2026-11-23", "2026-11-28", SUNDAY),
        # Wednesday holiday that runs the Sunday timetable (calendar_dates).
        (HOLIDAY, "sunday", "2026-11-12", "2026-11-14", HOLIDAY),
    ],
)
def test_first_date_on_or_after_requested_per_day_type(
    api, dataset, request_date, top, weekday, saturday, sunday
):
    body = body_of(api, date=request_date)
    assert body["day_type"] == top
    assert [c["date"] for c in body["columns"]] == [weekday, saturday, sunday]


def test_holiday_shows_sunday_timetable_in_sunday_column(api, dataset):
    body = body_of(api, date=HOLIDAY)
    assert times(body, "sunday") == ["08:00"]
    assert "05:12" not in times(body, "sunday")
    # The next normal weekday still has the weekday timetable.
    assert "05:12" in times(body, "weekday")


def test_holiday_which_equals_sunday_set_is_sunday_even_without_hardcoded_list(api, dataset):
    # 2026-11-12 is a normal Thursday, not a holiday.
    assert body_of(api, date="2026-11-12")["day_type"] == "weekday"


def test_default_date_is_today_in_city_timezone(api, dataset):
    body = body_of(api)
    assert body["date"] == today_in_city().isoformat()


def test_hours_ascending_with_after_midnight_last(api, dataset):
    body = body_of(api, "S1", date=MONDAY)
    hours = [h["hour"] for h in column(body, "weekday")["hours"]]
    assert hours == [5, 6, 7, 11, 12, 23, 0]


def test_after_midnight_departure_has_next_day_flag(api, dataset):
    body = body_of(api, "S1", date=MONDAY)
    last = column(body, "weekday")["hours"][-1]
    assert last["hour"] == 0
    (late,) = last["departures"]
    assert late == {
        "minute": 15,
        "time": "00:15",
        "next_day": True,
        "trip_id": sid("m5"),
        "headsign": "Terminus A",
        "markers": [],
        "variant": "v1",
    }
    flags = {d["time"]: d["next_day"] for d in departures(body, "weekday")}
    assert flags["23:50"] is False
    assert flags["05:12"] is False


def test_same_day_early_morning_and_after_midnight_departures_do_not_mix(api, dataset):
    dataset.simple_trip("early", "R10", "WK", ["S1", "S2"], "00:30")
    body = body_of(api, "S1", date=MONDAY)
    flat = [(d["time"], d["next_day"]) for d in departures(body, "weekday")]
    assert ("00:30", False) in flat and ("00:15", True) in flat
    assert flat.index(("00:30", False)) < flat.index(("05:12", False))
    assert flat.index(("00:15", True)) > flat.index(("23:50", False))


def test_departures_inside_an_hour_are_sorted_by_minute(api, dataset):
    dataset.simple_trip("m6", "R10", "WK", ["S1", "S2"], "05:03")
    hour5 = column(body_of(api, "S1", date=MONDAY), "weekday")["hours"][0]
    assert hour5["hour"] == 5
    assert [d["minute"] for d in hour5["departures"]] == [3, 12]
    assert all(d["time"].endswith(f":{d['minute']:02d}") for d in hour5["departures"])


def test_only_hours_with_departures_are_listed(api, dataset):
    hours = [h["hour"] for h in column(body_of(api, "S1", date=MONDAY), "weekday")["hours"]]
    assert all(h["departures"] for h in column(body_of(api, "S1", date=MONDAY), "weekday")["hours"])
    assert 8 not in hours


def test_low_floor_marker(api, dataset):
    body = body_of(api, "S1", date=MONDAY)
    by_trip = {d["trip_id"]: d for d in departures(body, "weekday")}
    assert by_trip[sid("m1")]["markers"] == ["low_floor"]
    assert by_trip[sid("m4")]["markers"] == []


def test_short_turn_and_variant_markers_and_variant_ids_match_route(api, dataset):
    route = api.get(f"lines/{LINE}/route/", date=MONDAY).json()
    kind_of = {v["id"]: v["kind"] for v in route["variants"]}
    body = body_of(api, "S2", date=MONDAY)
    by_trip = {d["trip_id"]: d for d in departures(body, "weekday")}

    assert by_trip[sid("st1")]["markers"] == ["short_turn"]
    assert kind_of[by_trip[sid("st1")]["variant"]] == "short_turn"
    assert by_trip[sid("st1")]["headsign"] == "Gamma short"
    assert by_trip[sid("dp1")]["markers"] == ["variant"]
    assert kind_of[by_trip[sid("dp1")]["variant"]] == "depot"
    assert by_trip[sid("m1")]["markers"] == ["low_floor"]
    assert kind_of[by_trip[sid("m1")]["variant"]] == "main"
    assert by_trip[sid("m1")]["variant"] == route["variants"][0]["id"]

    # The legend lists non-main variants used here, consistent with the route response.
    legend = {v["id"]: v for v in body["variants"]}
    assert set(legend) == {by_trip[sid("st1")]["variant"], by_trip[sid("dp1")]["variant"]}
    for variant_id, item in legend.items():
        assert item["kind"] == kind_of[variant_id]
        route_variant = next(v for v in route["variants"] if v["id"] == variant_id)
        assert item["headsign"] == route_variant["headsign"]


def test_variants_legend_is_empty_when_only_main_variant_is_used(api, dataset):
    body = body_of(api, "S1", line=f"{MAIN}:R20", date=MONDAY)
    assert body["variants"] == []
    assert all(d["variant"] == "v1" and d["markers"] == [] for d in departures(body, "weekday"))


def test_no_pickup_trip_is_excluded_but_still_listed_at_other_stops(api, dataset):
    at_s2 = {d["trip_id"] for d in departures(body_of(api, "S2", date=MONDAY), "weekday")}
    at_s1 = {d["trip_id"] for d in departures(body_of(api, "S1", date=MONDAY), "weekday")}
    assert sid("m2") not in at_s2
    assert sid("m2") in at_s1


def test_stop_time_without_departure_is_excluded(api, dataset):
    at_s2 = {d["trip_id"] for d in departures(body_of(api, "S2", date=MONDAY), "weekday")}
    assert sid("m3") not in at_s2


def test_last_stop_gives_empty_columns_not_an_error(api, dataset):
    body = body_of(api, "S4", date=MONDAY)
    assert [c["day_type"] for c in body["columns"]] == ["weekday", "saturday", "sunday"]
    assert all(c["hours"] == [] for c in body["columns"])
    assert body["next_stop"] is None
    assert body["previous_stop"]["stop_id"] == sid("S3")


def test_trip_ending_at_stop_is_excluded_while_others_continue(api, dataset):
    # Short-turn trips end at S3; other trips continue from S3.
    body = body_of(api, "S3", date=MONDAY)
    trips = {d["trip_id"] for d in departures(body, "weekday")}
    assert sid("st1") not in trips and sid("st2") not in trips
    assert sid("m1") in trips


def test_previous_and_next_stop_on_main_variant(api, dataset):
    body = body_of(api, "S2", date=MONDAY)
    assert body["previous_stop"] == {"stop_id": sid("S1"), "name": "Alpha"}
    assert body["next_stop"] == {"stop_id": sid("S3"), "name": "Gamma"}


def test_previous_stop_null_at_first_stop(api, dataset):
    body = body_of(api, "S1", date=MONDAY)
    assert body["previous_stop"] is None
    assert body["next_stop"]["stop_id"] == sid("S2")


def test_direction_one_timetable(api, dataset):
    body = body_of(api, "S4", direction=1, date=MONDAY)
    assert body["direction"] == 1
    assert body["headsign"] == "Start place"
    assert times(body, "weekday") == ["06:00"]
    assert times(body, "saturday") == [] and times(body, "sunday") == []
    assert body["previous_stop"] is None
    assert body["next_stop"]["stop_id"] == sid("S3")


def test_empty_columns_still_have_dates(api, dataset):
    body = body_of(api, "S1", line=f"{MAIN}:R20", date=MONDAY)
    assert column(body, "saturday")["hours"] == []
    assert column(body, "saturday")["date"] == SATURDAY
    assert column(body, "sunday")["date"] == SUNDAY


def test_service_beyond_fourteen_days_is_not_shown(api, dataset):
    dataset.calendar("FUT", ["monday", "tuesday"], start="2026-12-14", end="2026-12-31")
    dataset.simple_trip("fut1", "R10", "FUT", ["S1", "S2"], "15:00")
    body = body_of(api, "S1", date=MONDAY)
    assert "15:00" not in times(body, "weekday")
    assert column(body, "weekday")["date"] == MONDAY


def test_trips_without_direction_id_are_direction_zero(api, dataset):
    body = body_of(api, "S1", line=f"{MAIN}:R20", date=MONDAY)
    assert times(body, "weekday") == ["08:00"]
    assert timetable(api, "S1", f"{MAIN}:R20", direction=1, date=MONDAY).status_code == 404


def test_frequency_trips_are_expanded_per_headway(api, dataset):
    body = body_of(api, "S2", line=f"{MAIN}:RM1", date=MONDAY)
    assert times(body, "weekday") == [f"06:{m:02d}" for m in (3, 13, 23, 33, 43, 53)]
    assert {d["trip_id"] for d in departures(body, "weekday")} == {sid("f1")}
    body_s1 = body_of(api, "S1", line=f"{MAIN}:RM1", date=MONDAY)
    assert times(body_s1, "weekday") == [f"06:{m:02d}" for m in (0, 10, 20, 30, 40, 50)]
    assert times(body_s1, "saturday") == []


def test_blank_headsign_top_level_falls_back_to_last_stop(api, dataset):
    assert body_of(api, "S1", line=f"{MAIN}:RBLK", date=MONDAY)["headsign"] == "Beta"


def test_blank_headsign_departure_falls_back_to_last_stop(api, dataset):
    body = body_of(api, "S1", line=f"{MAIN}:RBLK", date=MONDAY)
    assert departures(body, "weekday")[0]["headsign"] == "Beta"


def test_stop_headsign_overrides_trip_headsign(api, dataset):
    from transit_data.models import StopTime

    StopTime.objects.filter(trip=dataset.trips["m1"], stop=dataset.stops["S1"]).update(
        stop_headsign="Only to Delta"
    )
    by_trip = {d["trip_id"]: d for d in departures(body_of(api, "S1", date=MONDAY), "weekday")}
    assert by_trip[sid("m1")]["headsign"] == "Only to Delta"


def test_rerun_with_warm_cache_gives_same_answer(api, dataset):
    assert body_of(api, "S3", date=MONDAY) == body_of(api, "S3", date=MONDAY)


def test_only_active_feed_version_data_is_used(api, dataset):
    old = Builder(MAIN, status="superseded")
    old.calendar("WK", ["monday"])
    old.stop("S1", "Alpha")
    old.stop("S2", "Beta")
    old.route("R10", "10")
    old.simple_trip("old_trip", "R10", "WK", ["S1", "S2"], "03:33")
    body = body_of(api, "S1", date=MONDAY)
    assert "03:33" not in times(body, "weekday")
    assert not any(d["trip_id"].endswith("old_trip") for d in departures(body, "weekday"))


# ---------------------------------------------------------------------------- errors


def test_unknown_line_is_404(api, dataset):
    assert timetable(api, "S1", line=f"{MAIN}:nope", date=MONDAY).status_code == 404


def test_unknown_stop_is_404(api, dataset):
    response = timetable(api, "nope", date=MONDAY)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_malformed_stop_id_is_404(api, dataset):
    response = api.get(f"lines/{LINE}/stops/garbage/timetable/", date=MONDAY)
    assert response.status_code == 404


def test_stop_not_served_by_line_is_404(api, dataset):
    assert timetable(api, "S3far", date=MONDAY).status_code == 404


def test_stop_not_served_in_that_direction_is_404(api, dataset):
    # The depot stop is only called at by direction 0 trips.
    assert timetable(api, "D", direction=0, date=MONDAY).status_code == 200
    assert timetable(api, "D", direction=1, date=MONDAY).status_code == 404


def test_direction_without_trips_is_404(api, dataset):
    assert timetable(api, "S3", line=f"{MAIN}:R52", direction=1, date=MONDAY).status_code == 404


@pytest.mark.parametrize("value", ["2", "x", "-1"])
def test_bad_direction_is_400(api, dataset, value):
    response = timetable(api, direction=value, date=MONDAY)
    assert response.status_code == 400
    assert "direction" in response.json()["error"]["details"]


@pytest.mark.parametrize("value", ["2026-13-01", "16.11.2026", "abc", "2026-02-30", "9999-12-31"])
def test_bad_date_is_400(api, dataset, value):
    response = timetable(api, date=value)
    assert response.status_code == 400
    assert "date" in response.json()["error"]["details"]


def test_unknown_city_is_404(api, dataset):
    response = api.get(f"lines/{LINE}/stops/{sid('S1')}/timetable/", city="atlantis")
    assert response.status_code == 404
