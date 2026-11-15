"""POST /cities/{city}/journeys/search/ with a fake OTP."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from journeys.tests.conftest import (
    BASE_LAT,
    BASE_LON,
    direct,
    itinerary,
    place,
    plan,
    post,
    route,
    transit_leg,
    walk_leg,
)

pytestmark = pytest.mark.django_db

S1 = place("Alpha", BASE_LAT, BASE_LON, "tt_main:S1")
S4 = place("Delta", BASE_LAT + 0.0027, BASE_LON, "tt_main:S4")
ORIGIN = place("Origin street", BASE_LAT - 0.0005, BASE_LON)
DEST = place("Dest street", BASE_LAT + 0.003, BASE_LON)
STOPS = {"from": {"stop_id": "tt_main:S1"}, "to": {"stop_id": "tt_main:S4"}}


def simple_transit():
    """walk - tram 10 - walk, 07:00-07:30 UTC."""
    return itinerary(
        "2026-11-16T07:00:00Z",
        "2026-11-16T07:30:00Z",
        [
            walk_leg(
                "2026-11-16T07:00:00Z",
                "2026-11-16T07:05:00Z",
                ORIGIN,
                S1,
                duration=300,
                distance=350,
            ),
            transit_leg(
                "2026-11-16T07:05:00Z",
                "2026-11-16T07:25:00Z",
                S1,
                S4,
                route(),
                intermediate=[place("Beta", 0, 0, "tt_main:S2")],
            ),
            walk_leg(
                "2026-11-16T07:25:00Z", "2026-11-16T07:30:00Z", S4, DEST, duration=200, distance=150
            ),
        ],
        duration=1800,
    )


def one_leg(start, end, r=None, mode="TRAM"):
    return itinerary(start, end, [transit_leg(start, end, S1, S4, r or route(), mode=mode)])


def ride_of(response):
    return response.json()["itineraries"][0]["legs"][0]


# ------------------------------------------------------------------ happy path


def test_happy_path_maps_legs_and_converts_to_city_time(client, fake_otp):
    fake_otp.transit = plan(simple_transit())
    response = post(
        client,
        {
            "from": {"lat": ORIGIN["lat"], "lon": ORIGIN["lon"], "name": "Home"},
            "to": {"lat": DEST["lat"], "lon": DEST["lon"]},
            "time": "2026-11-16T08:00:00+01:00",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["from"] == {"name": "Home", "lat": ORIGIN["lat"], "lon": ORIGIN["lon"]}
    assert data["to"]["name"] is None
    assert len(data["itineraries"]) == 1
    it = data["itineraries"][0]
    assert it["id"] == "i1"
    # UTC from OTP -> Europe/Warsaw (winter, +01:00)
    assert it["start"] == "2026-11-16T08:00:00+01:00"
    assert it["end"] == "2026-11-16T08:30:00+01:00"
    assert it["duration"] == 1800
    assert it["transfers"] == 0
    assert it["walk_distance"] == 500
    assert it["walk_duration"] == 500
    walk1, ride, walk2 = it["legs"]
    assert walk1["mode"] == "walk"
    assert walk1["line"] is None and walk1["trip_id"] is None and walk1["headsign"] is None
    assert walk1["intermediate_stops"] == []
    assert walk1["from"]["name"] == "Home"  # request label on the journey start
    assert walk1["from"]["stop_id"] is None
    assert walk1["to"]["stop_id"] == "tt_main:S1"
    assert walk2["to"]["name"] is None  # no label requested for the destination
    assert ride["mode"] == "tram"
    assert ride["start"] == "2026-11-16T08:05:00+01:00"
    assert ride["headsign"] == "Delta"
    assert ride["trip_id"] == "tt_main:m1"
    assert ride["intermediate_stops"] == [{"name": "Beta", "stop_id": "tt_main:S2"}]
    assert ride["line"] == {
        "id": "tt_main:R10",
        "short_name": "10",
        "vehicle_type": "tram",
        "group": "day",
        "colour": "#ff0000",
        "text_colour": "#ffffff",
    }
    assert ride["geometry"]["type"] == "LineString"
    assert len(ride["geometry"]["coordinates"]) >= 2


def test_summer_time_uses_plus_two_offset(client, fake_otp):
    fake_otp.transit = plan(one_leg("2026-07-01T06:00:00Z", "2026-07-01T06:30:00Z"))
    data = post(client, {**STOPS, "time": "2026-07-01T08:00:00+02:00"}).json()
    assert data["itineraries"][0]["start"] == "2026-07-01T08:00:00+02:00"


def test_estimated_time_wins_over_scheduled(client, fake_otp):
    leg = transit_leg(
        "2026-11-16T07:05:00Z",
        "2026-11-16T07:25:00Z",
        S1,
        S4,
        route(),
        estimated_start="2026-11-16T07:07:00Z",
    )
    fake_otp.transit = plan(itinerary("2026-11-16T07:05:00Z", "2026-11-16T07:25:00Z", [leg]))
    assert ride_of(post(client, STOPS))["start"] == "2026-11-16T08:07:00+01:00"


def test_stop_places_use_stop_coordinates_and_name(client, fake_otp):
    fake_otp.transit = plan(simple_transit())
    data = post(client, STOPS).json()
    assert data["from"]["name"] == "Alpha"
    assert data["to"]["name"] == "Delta"
    assert data["from"]["lat"] == pytest.approx(BASE_LAT)
    assert data["from"]["lon"] == pytest.approx(BASE_LON)


def test_polyline_geometry_is_decoded_to_lon_lat(client, fake_otp):
    leg = walk_leg(
        "2026-11-16T07:00:00Z", "2026-11-16T07:01:00Z", ORIGIN, S1, points="_p~iF~ps|U_ulLnnqC"
    )
    ride = transit_leg("2026-11-16T07:05:00Z", "2026-11-16T07:25:00Z", S1, S4, route())
    fake_otp.transit = plan(itinerary("2026-11-16T07:00:00Z", "2026-11-16T07:25:00Z", [leg, ride]))
    assert ride_of(post(client, STOPS))["geometry"]["coordinates"] == [
        [-120.2, 38.5],
        [-120.95, 40.7],
    ]


def test_invalid_polyline_falls_back_to_straight_line(client, fake_otp):
    leg = transit_leg("2026-11-16T07:05:00Z", "2026-11-16T07:25:00Z", S1, S4, route())
    leg["legGeometry"] = {"points": "\x01\x02"}
    fake_otp.transit = plan(itinerary("2026-11-16T07:05:00Z", "2026-11-16T07:25:00Z", [leg]))
    coords = ride_of(post(client, STOPS))["geometry"]["coordinates"]
    assert coords == [[S1["lon"], S1["lat"]], [S4["lon"], S4["lat"]]]


def test_three_otp_queries_go_to_the_city_url(client, fake_otp):
    post(client, STOPS)
    assert set(fake_otp.urls) == {"http://otp.invalid:8080"}
    assert len(fake_otp.calls) == 3  # transit, walk, bike


# --------------------------------------------------------------- preferences


def test_default_preferences_send_no_otp_preferences(client, fake_otp):
    post(client, STOPS)
    assert "preferences" not in fake_otp.transit_call


@pytest.mark.parametrize(
    ("pref", "key"),
    [("fewer_transfers", "transit"), ("less_walking", "street"), ("wheelchair", "accessibility")],
)
def test_each_preference_changes_otp_request(client, fake_otp, pref, key):
    response = post(client, {**STOPS, "preferences": {pref: True}})
    assert response.status_code == 200
    assert list(fake_otp.transit_call["preferences"]) == [key]


def test_arrive_mode_sends_latest_arrival(client, fake_otp):
    post(client, {**STOPS, "time": "2026-11-16T08:00:00+01:00", "time_mode": "arrive"})
    assert fake_otp.transit_call["dateTime"] == {"latestArrival": "2026-11-16T08:00:00+01:00"}


def test_depart_mode_is_default(client, fake_otp):
    post(client, {**STOPS, "time": "2026-11-16T08:00:00+01:00"})
    assert fake_otp.transit_call["dateTime"] == {"earliestDeparture": "2026-11-16T08:00:00+01:00"}


def test_naive_time_is_interpreted_in_city_zone(client, fake_otp):
    post(client, {**STOPS, "time": "2026-11-16T08:00:00"})
    assert fake_otp.transit_call["dateTime"] == {"earliestDeparture": "2026-11-16T08:00:00+01:00"}


def test_utc_time_is_converted_to_city_zone(client, fake_otp):
    post(client, {**STOPS, "time": "2026-11-16T07:00:00Z"})
    assert fake_otp.transit_call["dateTime"] == {"earliestDeparture": "2026-11-16T08:00:00+01:00"}


def test_missing_time_defaults_to_now(client, fake_otp):
    post(client, STOPS)
    sent = datetime.fromisoformat(fake_otp.transit_call["dateTime"]["earliestDeparture"])
    assert abs((datetime.now(ZoneInfo("Europe/Warsaw")) - sent).total_seconds()) < 60


# ---------------------------------------------------- sorting, limits, filtering


def test_depart_sorted_by_arrival_and_capped_at_five(client, fake_otp):
    nodes = [
        one_leg("2026-11-16T07:00:00Z", f"2026-11-16T07:{minute:02d}:00Z")
        for minute in (50, 10, 40, 20, 30, 15, 45)
    ]
    fake_otp.transit = plan(*nodes)
    its = post(client, STOPS).json()["itineraries"]
    assert [i["end"][11:16] for i in its] == ["08:10", "08:15", "08:20", "08:30", "08:40"]
    assert [i["id"] for i in its] == ["i1", "i2", "i3", "i4", "i5"]


def test_arrive_sorted_by_departure_descending(client, fake_otp):
    nodes = [
        one_leg(f"2026-11-16T07:{minute:02d}:00Z", "2026-11-16T08:00:00Z")
        for minute in (10, 40, 20)
    ]
    fake_otp.transit = plan(*nodes)
    its = post(
        client, {**STOPS, "time_mode": "arrive", "time": "2026-11-16T09:00:00+01:00"}
    ).json()["itineraries"]
    assert [i["start"][11:16] for i in its] == ["08:40", "08:20", "08:10"]


def test_walk_only_itineraries_are_dropped(client, fake_otp):
    walk_only = itinerary(
        "2026-11-16T07:00:00Z",
        "2026-11-16T07:30:00Z",
        [walk_leg("2026-11-16T07:00:00Z", "2026-11-16T07:30:00Z", ORIGIN, DEST)],
    )
    fake_otp.transit = plan(walk_only, simple_transit())
    its = post(client, STOPS).json()["itineraries"]
    assert len(its) == 1
    assert any(leg["mode"] != "walk" for leg in its[0]["legs"])


def test_only_walk_results_give_empty_itineraries(client, fake_otp):
    walk_only = itinerary(
        "2026-11-16T07:00:00Z",
        "2026-11-16T07:30:00Z",
        [walk_leg("2026-11-16T07:00:00Z", "2026-11-16T07:30:00Z", ORIGIN, DEST)],
    )
    fake_otp.transit = plan(walk_only)
    response = post(client, STOPS)
    assert response.status_code == 200
    assert response.json()["itineraries"] == []


def test_transfers_is_transit_legs_minus_one(client, fake_otp):
    s2 = place("Beta", BASE_LAT + 0.0009, BASE_LON, "tt_main:S2")
    legs = [
        transit_leg("2026-11-16T07:00:00Z", "2026-11-16T07:10:00Z", S1, s2, route()),
        walk_leg("2026-11-16T07:10:00Z", "2026-11-16T07:12:00Z", s2, s2),
        transit_leg(
            "2026-11-16T07:15:00Z",
            "2026-11-16T07:30:00Z",
            s2,
            S4,
            route("tt_main:R52", "52", 0, "FFFFFF", "000000"),
        ),
        transit_leg(
            "2026-11-16T07:31:00Z",
            "2026-11-16T07:40:00Z",
            S4,
            DEST,
            route("tt_main:RN1", "N1", 3, "000000", ""),
            mode="BUS",
        ),
    ]
    fake_otp.transit = plan(itinerary("2026-11-16T07:00:00Z", "2026-11-16T07:40:00Z", legs))
    it = post(client, STOPS).json()["itineraries"][0]
    assert it["transfers"] == 2
    assert [leg["mode"] for leg in it["legs"]] == ["tram", "walk", "tram", "bus"]
    # White and black GTFS colours count as unset: the night group colour is used for N1.
    assert it["legs"][3]["line"]["group"] == "night"
    assert it["legs"][3]["line"]["colour"] == "#f0e68c"


def test_single_transit_leg_has_zero_transfers(client, fake_otp):
    fake_otp.transit = plan(simple_transit())
    assert post(client, STOPS).json()["itineraries"][0]["transfers"] == 0


def test_route_missing_from_db_falls_back_to_otp_route(client, fake_otp):
    ghost = route("tt_main:NEW7", "7", 3, "00AA00", "FFFFFF")
    fake_otp.transit = plan(
        one_leg("2026-11-16T07:00:00Z", "2026-11-16T07:20:00Z", ghost, mode="BUS")
    )
    leg = ride_of(post(client, STOPS))
    assert leg["mode"] == "bus"
    assert leg["line"] == {
        "id": "tt_main:NEW7",
        "short_name": "7",
        "vehicle_type": "bus",
        "group": "day",
        "colour": "#00aa00",
        "text_colour": "#ffffff",
    }


def test_fallback_without_route_colour_uses_group_colour(client, fake_otp):
    ghost = route("tt_main:NEWN2", "N2", 3, "", "")
    fake_otp.transit = plan(
        one_leg("2026-11-16T07:00:00Z", "2026-11-16T07:20:00Z", ghost, mode="BUS")
    )
    line = ride_of(post(client, STOPS))["line"]
    assert line["group"] == "night"
    assert line["colour"] == "#f0e68c"
    assert line["text_colour"] in ("#000000", "#ffffff")


def test_itinerary_with_unsupported_mode_is_dropped(client, fake_otp):
    ferry = route("tt_main:F1", "F1", 4)  # GTFS type 4 = ferry, not shown in ttville
    bad = one_leg("2026-11-16T07:00:00Z", "2026-11-16T07:20:00Z", ferry, mode="FERRY")
    fake_otp.transit = plan(bad, simple_transit())
    assert len(post(client, STOPS).json()["itineraries"]) == 1


# ------------------------------------------------------------- empty, comparison


def test_empty_result_is_200_with_empty_list(client, fake_otp):
    fake_otp.transit = plan()
    response = post(client, STOPS)
    assert response.status_code == 200
    assert response.json()["itineraries"] == []


def test_comparison_values(client, fake_otp):
    fake_otp.walk = direct(1800, 2000.4)
    fake_otp.bike = direct(600, 2200)
    assert post(client, STOPS).json()["comparison"] == {
        "walk": {"duration": 1800, "distance": 2000},
        "bike": {"duration": 600, "distance": 2200},
    }


def test_comparison_null_when_no_street_route(client, fake_otp):
    fake_otp.walk = plan()
    fake_otp.bike = plan()
    assert post(client, STOPS).json()["comparison"] == {"walk": None, "bike": None}


def test_comparison_null_above_three_hours_only(client, fake_otp):
    fake_otp.walk = direct(3 * 3600 + 1, 15000)
    fake_otp.bike = direct(3 * 3600, 15000)  # exactly 3 h is allowed
    comparison = post(client, STOPS).json()["comparison"]
    assert comparison["walk"] is None
    assert comparison["bike"] == {"duration": 10800, "distance": 15000}


def test_walk_and_bike_queries_are_street_only(client, fake_otp):
    post(client, STOPS)
    assert fake_otp.direct_call("WALK")["modes"]["directOnly"] is True
    assert fake_otp.direct_call("BICYCLE")["modes"]["directOnly"] is True


# ---------------------------------------------------------------------- validation

BAD_REQUESTS = [
    {"from": {"stop_id": "tt_main:S1", "lat": 50.06, "lon": 19.94}, "to": STOPS["to"]},
    {"from": {}, "to": STOPS["to"]},
    {"from": STOPS["from"], "to": {"lat": 50.06}},
    {"from": STOPS["from"]},
    {"to": STOPS["to"]},
    {**STOPS, "time_mode": "sometime"},
    {**STOPS, "time": "tomorrow"},
    {"from": {"lat": "abc", "lon": 19.9}, "to": STOPS["to"]},
    {**STOPS, "preferences": {"wheelchair": "maybe"}},
]


@pytest.mark.parametrize("data", BAD_REQUESTS)
def test_invalid_request_is_400_validation_error(client, fake_otp, data):
    response = post(client, data)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert fake_otp.calls == []


def test_unknown_stop_id_is_400_with_details(client, fake_otp):
    response = post(client, {"from": {"stop_id": "tt_main:NOPE"}, "to": STOPS["to"]})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert any(key.startswith("from") for key in error["details"])


@pytest.mark.parametrize("stop_id", ["not_in_config:S1", "garbage"])
def test_stop_of_unknown_feed_or_malformed_is_400(client, fake_otp, stop_id):
    response = post(client, {"from": {"stop_id": stop_id}, "to": STOPS["to"]})
    assert response.status_code == 400


def test_same_stop_and_point_is_400(client, fake_otp):
    response = post(client, {"from": STOPS["from"], "to": {"lat": BASE_LAT, "lon": BASE_LON}})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert fake_otp.calls == []


def test_same_stop_twice_is_400(client, fake_otp):
    assert post(client, {"from": STOPS["from"], "to": STOPS["from"]}).status_code == 400


def test_point_outside_city_bbox_is_400(client, fake_otp):
    response = post(client, {"from": {"lat": 52.23, "lon": 21.01}, "to": STOPS["to"]})
    assert response.status_code == 400
    assert "from" in response.json()["error"]["details"]
    assert fake_otp.calls == []


def test_both_points_outside_report_both_fields(client, fake_otp):
    response = post(client, {"from": {"lat": 52.23, "lon": 21.01}, "to": {"lat": 40, "lon": 10}})
    assert set(response.json()["error"]["details"]) >= {"from", "to"}


def test_bad_time_mode_is_reported_on_its_field(client, fake_otp):
    response = post(client, {**STOPS, "time_mode": "x"})
    assert "time_mode" in response.json()["error"]["details"]


def test_unknown_city_is_404(client, fake_otp):
    response = post(client, STOPS, city="atlantis")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_is_not_allowed(client, fake_otp):
    assert client.get("/api/v1/cities/ttville/journeys/search/").status_code == 405


def test_no_auth_required(client, fake_otp):
    assert post(client, STOPS).status_code == 200
