"""GET /cities/{city}/stops/{stop_id}/ (docs/api.md, "Stop overview", #9).

Fictional stop group "Hub": platforms A1, A2, A3 (feed tt_main, 100 m apart) and B1 (feed
tt_second, 50 m from A1), plus a different "Hub" F1 about 1 km away. Other stops (End1, End2,
Mid) are far from everything. Trips of every service day count, so one weekday calendar is
enough.
"""

import pytest

from transit_data.models import FeedVersion

from .conftest import LAT_PER_100M, MAIN, MONDAY, SECOND, Builder

pytestmark = pytest.mark.django_db

HUB = "Hub"
WK = ["monday", "tuesday", "wednesday", "thursday", "friday"]


def sid(gtfs_id, feed=MAIN):
    return f"{feed}:{gtfs_id}"


def overview(api, stop, **kwargs):
    return api.get(f"stops/{stop}/", **kwargs)


def body(api, stop="A1", **kwargs):
    response = overview(api, sid(stop) if ":" not in stop else stop, **kwargs)
    assert response.status_code == 200, response.content
    return response.json()


def by_line(data):
    return {item["line"]["short_name"]: item for item in data["lines"]}


def order(data):
    return [item["line"]["short_name"] for item in data["lines"]]


def add_stops(b):
    b.stop("A1", HUB, 0, 0)
    b.stop("A2", HUB, LAT_PER_100M, 0)
    b.stop("A3", HUB, LAT_PER_100M * 2, 0)
    b.stop("F1", HUB, LAT_PER_100M * 100, 0)
    b.stop("End1", "End one", LAT_PER_100M * 200, 0)
    b.stop("End2", "End two", LAT_PER_100M * 300, 0)
    b.stop("Mid", "Middle", -LAT_PER_100M * 200, 0)


@pytest.fixture
def ov(db, city_config):
    """Main feed with the Hub group; second feed with one more Hub platform."""
    b = Builder(MAIN)
    b.calendar("WK", WK)
    add_stops(b)
    second = Builder(SECOND)
    second.calendar("WK", WK)
    second.stop("B1", HUB, LAT_PER_100M * 0.5, 0)
    second.stop("B9", "Elsewhere", LAT_PER_100M * 400, 0)
    b.second = second
    return b


def run(b, gtfs_id, route, stops, direction=0, headsign="Terminus A", start="08:00"):
    return b.simple_trip(gtfs_id, route, "WK", stops, start, direction=direction, headsign=headsign)


# ------------------------------------------------------------------ shape and grouping


def test_response_shape_and_group(api, ov):
    ov.route("R10", "10", 0, color="FF0000", text_color="FFFFFF")
    run(ov, "t1", "R10", ["A1", "End1"])
    data = body(api, "A1")
    assert set(data) == {"stop", "lines"}
    stop = data["stop"]
    assert set(stop) == {"id", "name", "lat", "lon", "vehicle_types", "stop_ids"}
    assert stop["id"] == sid("A1")
    assert stop["name"] == HUB
    assert stop["vehicle_types"] == ["tram"]
    assert isinstance(stop["lat"], float)
    assert isinstance(stop["lon"], float)
    line = data["lines"][0]
    assert set(line) == {"line", "directions"}
    assert set(line["line"]) == {
        "id",
        "short_name",
        "vehicle_type",
        "group",
        "colour",
        "text_colour",
    }
    assert line["line"]["id"] == sid("R10")
    assert line["line"]["colour"] == "#ff0000"
    assert set(line["directions"][0]) == {"direction", "headsign", "platform_id"}


def test_group_spans_platforms_and_feeds_but_not_far_namesakes(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"])
    data = body(api, "A1")
    assert sorted(data["stop"]["stop_ids"]) == [sid("A1"), sid("A2"), sid("A3"), sid("B1", SECOND)]
    assert sid("F1") not in data["stop"]["stop_ids"]


@pytest.mark.parametrize("requested", ["A1", "A2", "A3"])
def test_any_platform_of_the_group_gives_the_same_group_and_echoes_the_id(api, ov, requested):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"])
    reference = body(api, "A1")
    data = body(api, requested)
    assert data["stop"]["id"] == sid(requested)
    assert sorted(data["stop"]["stop_ids"]) == sorted(reference["stop"]["stop_ids"])
    assert data["lines"] == reference["lines"]


def test_platform_of_the_other_feed_resolves_the_same_group(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"])
    data = body(api, sid("B1", SECOND))
    assert data["stop"]["id"] == sid("B1", SECOND)
    assert sid("A1") in data["stop"]["stop_ids"]
    assert order(data) == ["10"]


def test_line_of_another_feed_at_the_group_is_included(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"])
    s = ov.second
    s.route("B7", "7", 3)
    run(s, "b1", "B7", ["B1", "B9"], headsign="Elsewhere")
    data = body(api, "A1")
    assert order(data) == ["10", "7"]
    line = by_line(data)["7"]
    assert line["line"]["id"] == sid("B7", SECOND)
    assert line["directions"][0]["platform_id"] == sid("B1", SECOND)
    assert data["stop"]["vehicle_types"] == ["tram", "bus"]


def test_other_namesake_stop_group_has_own_lines(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"])
    ov.route("R20", "20", 0)
    run(ov, "t2", "R20", ["F1", "End2"])
    assert order(body(api, "F1")) == ["20"]
    assert order(body(api, "A1")) == ["10"]


# ------------------------------------------------------------------ which lines and directions


def test_terminus_only_direction_is_omitted_but_other_direction_stays(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t0", "R10", ["A1", "End1"], direction=0)
    run(ov, "t1", "R10", ["End1", "A1"], direction=1)  # ends at the group
    directions = by_line(body(api, "A1"))["10"]["directions"]
    assert [d["direction"] for d in directions] == [0]


def test_line_with_only_terminus_calls_is_omitted(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t0", "R10", ["A1", "End1"])
    ov.route("R30", "30", 0)
    run(ov, "t3", "R30", ["Mid", "A2"], direction=1)
    assert order(body(api, "A1")) == ["10"]


def test_trip_calling_at_group_platform_before_and_after_other_stop(api, ov):
    ov.route("R10", "10", 0)
    # The call at A1 departs (later stops exist), the final call at A2 does not.
    run(ov, "t0", "R10", ["A1", "End1", "A2"])
    directions = by_line(body(api, "A1"))["10"]["directions"]
    assert directions[0]["platform_id"] == sid("A1")


def test_pickup_type_1_is_not_a_departure(api, ov):
    ov.route("RP", "P", 0)
    ov.trip(
        "p1",
        "RP",
        "WK",
        [("A1", "08:00", "08:00", {"pickup_type": 1}), ("End1", "08:05", "08:05")],
    )
    assert body(api, "A1")["lines"] == []


def test_pickup_type_1_platform_is_not_chosen(api, ov):
    ov.route("RP", "P", 0)
    for index in range(3):
        ov.trip(
            f"p{index}",
            "RP",
            "WK",
            [("A1", "08:00", "08:00", {"pickup_type": 1}), ("End1", "08:05", "08:05")],
        )
    run(ov, "q1", "RP", ["A2", "End1"])
    directions = by_line(body(api, "A1"))["P"]["directions"]
    assert [d["platform_id"] for d in directions] == [sid("A2")]


def test_missing_direction_id_counts_as_direction_0(api, ov):
    ov.route("RND", "ND", 0)
    run(ov, "n1", "RND", ["A1", "End1"], direction=None)
    run(ov, "n2", "RND", ["A1", "End1"], direction=0)
    directions = by_line(body(api, "A1"))["ND"]["directions"]
    assert [d["direction"] for d in directions] == [0]


def test_line_with_only_missing_direction_id_gets_direction_0(api, ov):
    ov.route("RND", "ND", 0)
    run(ov, "n1", "RND", ["A1", "End1"], direction=None)
    directions = by_line(body(api, "A1"))["ND"]["directions"]
    assert [d["direction"] for d in directions] == [0]


def test_both_directions_sorted_even_when_created_in_reverse(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A2", "End2"], direction=1, headsign="Two")
    run(ov, "t0", "R10", ["A1", "End1"], direction=0, headsign="One")
    directions = by_line(body(api, "A1"))["10"]["directions"]
    assert [(d["direction"], d["headsign"]) for d in directions] == [(0, "One"), (1, "Two")]


def test_line_without_trips_at_the_stop_is_absent(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"])
    ov.route("R20", "20", 0)
    run(ov, "t2", "R20", ["Mid", "End2"])
    ov.route("R21", "21", 0)  # route without any trip
    assert order(body(api, "A1")) == ["10"]


def test_superseded_feed_version_lines_never_appear(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"])
    old = Builder(MAIN, status=FeedVersion.Status.SUPERSEDED)
    old.calendar("WK", WK)
    add_stops(old)
    old.route("OLD", "OLD", 0)
    run(old, "o1", "OLD", ["A1", "End1"])
    assert order(body(api, "A1")) == ["10"]


def test_trips_on_any_service_day_count(api, ov):
    ov.calendar("SU", ["sunday"])
    ov.route("R10", "10", 0)
    ov.simple_trip("s1", "R10", "SU", ["A1", "End1"], "09:00")
    assert order(body(api, "A1")) == ["10"]


def test_after_midnight_trip_counts(api, ov):
    ov.route("R10", "10", 0)
    ov.trip("late", "R10", "WK", [("A1", "24:10", "24:10"), ("End1", "24:20", "24:20")])
    assert order(body(api, "A1")) == ["10"]


# ------------------------------------------------------------------ platform choice


def test_platform_is_the_one_with_most_trips(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"], start="08:00")
    run(ov, "t2", "R10", ["A2", "End1"], start="08:10")
    run(ov, "t3", "R10", ["A2", "End1"], start="08:20")
    directions = by_line(body(api, "A1"))["10"]["directions"]
    assert directions[0]["platform_id"] == sid("A2")


def test_platform_tie_goes_to_lowest_id(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A3", "End1"], start="08:00")
    run(ov, "t2", "R10", ["A2", "End1"], start="08:10")
    directions = by_line(body(api, "A3"))["10"]["directions"]
    assert directions[0]["platform_id"] == sid("A2")


def test_platform_is_chosen_per_direction(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"], direction=0)
    run(ov, "t2", "R10", ["A3", "End2"], direction=1)
    directions = by_line(body(api, "A1"))["10"]["directions"]
    assert [d["platform_id"] for d in directions] == [sid("A1"), sid("A3")]


def test_trip_visiting_a_platform_twice_counts_once(api, ov):
    ov.route("R10", "10", 0)
    # One trip calls twice at A1 (loop); two other trips call once at A2: A2 wins.
    run(ov, "loop", "R10", ["A1", "End1", "A1", "End2"])
    run(ov, "t2", "R10", ["A2", "End1"])
    run(ov, "t3", "R10", ["A2", "End1"])
    directions = by_line(body(api, "A1"))["10"]["directions"]
    assert directions[0]["platform_id"] == sid("A2")


# ------------------------------------------------------------------ headsign choice


def test_headsign_is_the_most_frequent_at_the_chosen_platform(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"], headsign="Alpha", start="08:00")
    run(ov, "t2", "R10", ["A1", "End1"], headsign="Zeta", start="08:10")
    run(ov, "t3", "R10", ["A1", "End1"], headsign="Zeta", start="08:20")
    assert by_line(body(api, "A1"))["10"]["directions"][0]["headsign"] == "Zeta"


def test_headsign_tie_is_alphabetical(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"], headsign="Beta", start="08:00")
    run(ov, "t2", "R10", ["A1", "End1"], headsign="Alpha", start="08:10")
    assert by_line(body(api, "A1"))["10"]["directions"][0]["headsign"] == "Alpha"


def test_headsign_comes_from_the_chosen_platform_only(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"], headsign="Minor", start="08:00")
    for index in range(2):
        run(ov, f"o{index}", "R10", ["A2", "End1"], headsign="Major", start=f"09:0{index}")
    directions = by_line(body(api, "A1"))["10"]["directions"]
    assert directions[0]["platform_id"] == sid("A2")
    assert directions[0]["headsign"] == "Major"


def test_headsign_ignores_trips_not_departing_at_the_platform(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"], headsign="Goes on")
    run(ov, "t2", "R10", ["End1", "A1"], headsign="Ends here")  # terminates at A1
    run(ov, "t3", "R10", ["End1", "A1"], headsign="Ends here", start="09:00")
    assert by_line(body(api, "A1"))["10"]["directions"][0]["headsign"] == "Goes on"


def test_stop_headsign_overrides_trip_headsign(api, ov):
    ov.route("R10", "10", 0)
    ov.trip(
        "t1",
        "R10",
        "WK",
        [("A1", "08:00", "08:00", {"stop_headsign": "Via stop"}), ("End1", "08:05", "08:05")],
        headsign="Trip sign",
    )
    assert by_line(body(api, "A1"))["10"]["directions"][0]["headsign"] == "Via stop"


def test_blank_trip_headsign_falls_back_to_last_stop_name(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "Mid", "End2"], headsign="")
    assert by_line(body(api, "A1"))["10"]["directions"][0]["headsign"] == "End two"


def test_blank_stop_headsign_falls_back_to_trip_headsign(api, ov):
    ov.route("R10", "10", 0)
    ov.trip(
        "t1",
        "R10",
        "WK",
        [("A1", "08:00", "08:00", {"stop_headsign": ""}), ("End1", "08:05", "08:05")],
        headsign="Trip sign",
    )
    assert by_line(body(api, "A1"))["10"]["directions"][0]["headsign"] == "Trip sign"


def test_fallback_and_real_headsigns_are_counted_together(api, ov):
    ov.route("R10", "10", 0)
    # "End one" comes from the last-stop fallback twice and from a real headsign once.
    run(ov, "t1", "R10", ["A1", "End1"], headsign="", start="08:00")
    run(ov, "t2", "R10", ["A1", "End1"], headsign="", start="08:10")
    run(ov, "t3", "R10", ["A1", "End1"], headsign="End one", start="08:20")
    run(ov, "t4", "R10", ["A1", "End2"], headsign="Aaa", start="08:30")
    assert by_line(body(api, "A1"))["10"]["directions"][0]["headsign"] == "End one"


# ------------------------------------------------------------------ sorting


def test_lines_sorted_by_vehicle_type_then_group_then_natural_name(api, ov):
    # Created in an order different from the expected one.
    for gtfs, short, route_type in [
        ("rail", "S1", 2),
        ("metro", "M1", 1),
        ("b100", "100", 3),
        ("bN5", "N5", 3),
        ("b5", "5", 3),
        ("b91", "91", 3),
        ("t10", "10", 0),
        ("t2", "2", 0),
        ("t10a", "10A", 0),
        ("tB", "B", 0),
        ("t1", "1", 0),
    ]:
        ov.route(gtfs, short, route_type)
        run(ov, f"trip_{gtfs}", gtfs, ["A1", "End1"])
    ov.second.route("b7", "7", 3)
    run(ov.second, "trip_b7", "b7", ["B1", "B9"])
    data = body(api, "A1")
    assert order(data) == [
        # tram, natural order
        "1",
        "2",
        "10",
        "10A",
        "B",
        # bus: day, night, agglomeration, replacement (city line_groups order)
        "5",
        "100",
        "N5",
        "7",
        "91",
        "M1",
        "S1",
    ]
    assert data["stop"]["vehicle_types"] == ["tram", "bus", "metro", "rail"]
    groups = {item["line"]["short_name"]: item["line"]["group"] for item in data["lines"]}
    assert groups["5"] == "day"
    assert groups["N5"] == "night"
    assert groups["91"] == "replacement"
    assert groups["7"] == "agglomeration"


def test_line_summary_matches_lines_endpoint(api, ov):
    ov.route("R10", "10", 0, color="FF0000", text_color="FFFFFF")
    run(ov, "t1", "R10", ["A1", "End1"])
    summary = body(api, "A1")["lines"][0]["line"]
    listed = next(x for x in api.get("lines/").json() if x["id"] == summary["id"])
    assert {k: listed[k] for k in summary} == summary


# ------------------------------------------------------------------ empty, errors, cache header


def test_group_without_any_trips_gives_empty_lines(api, ov):
    data = body(api, "A1")
    assert data["lines"] == []
    assert data["stop"]["vehicle_types"] == []
    assert data["stop"]["name"] == HUB


def test_cache_control_max_age_300(api, ov):
    response = overview(api, sid("A1"))
    assert response.status_code == 200
    assert "max-age=300" in response["Cache-Control"]


def test_unknown_stop_is_404(api, ov):
    response = overview(api, sid("nope"))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("stop", ["garbage", "unknown_feed:A1", f"{MAIN}:", ":A1"])
def test_malformed_or_unknown_feed_stop_ids_are_404(api, ov, stop):
    assert overview(api, stop).status_code == 404


def test_unknown_city_is_404(api, ov):
    response = api.get(f"stops/{sid('A1')}/", city="nowhere")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_404_messages_are_translated(api, ov):
    pl = overview(api, sid("nope"), lang="pl").json()["error"]["message"]
    en = overview(api, sid("nope"), lang="en").json()["error"]["message"]
    assert pl == "Nie znaleziono przystanku."
    assert en == "Stop not found."
    pl_city = api.get("stops/x:y/", lang="pl", city="nowhere").json()["error"]["message"]
    en_city = api.get("stops/x:y/", lang="en", city="nowhere").json()["error"]["message"]
    assert pl_city != en_city


def test_nameless_stop_and_stop_of_superseded_version_are_404(api, ov):
    ov.stop("Nameless", "  ", 0, 0)
    assert overview(api, sid("Nameless")).status_code == 404
    old = Builder(MAIN, status=FeedVersion.Status.SUPERSEDED)
    old.stop("OldOnly", "Old place", 0, 0)
    assert overview(api, sid("OldOnly")).status_code == 404


def test_post_is_not_allowed(api, ov):
    response = api.client.post(f"/api/v1/cities/ttville/stops/{sid('A1')}/", {})
    assert response.status_code == 405


# ------------------------------------------------------------------ cache and feed versions


def test_new_feed_version_invalidates_cached_directions(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"], headsign="Before")
    first = body(api, "A1")
    assert by_line(first)["10"]["directions"][0]["headsign"] == "Before"
    # A repeated request is served from the cache with the same content.
    assert body(api, "A1") == first

    FeedVersion.objects.filter(pk=ov.version.pk).update(status=FeedVersion.Status.SUPERSEDED)
    new = Builder(MAIN)
    new.calendar("WK", WK)
    add_stops(new)
    new.route("R10", "10", 0)
    new.route("R11", "11", 0)
    run(new, "t1", "R10", ["A2", "End1"], headsign="After")
    run(new, "t2", "R11", ["A1", "End2"])
    data = body(api, "A1")
    assert order(data) == ["10", "11"]
    direction = by_line(data)["10"]["directions"][0]
    assert (direction["headsign"], direction["platform_id"]) == ("After", sid("A2"))


def test_cached_result_is_stable_after_data_change_within_same_version(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"], headsign="Before")
    first = body(api, "A1")
    run(ov, "t2", "R10", ["A1", "End1"], headsign="Later", start="09:00")
    run(ov, "t3", "R10", ["A1", "End1"], headsign="Later", start="09:10")
    # Feed versions are immutable, so the cached directions are kept for the version.
    assert body(api, "A1") == first


# ------------------------------------------------------------------ links to other endpoints


def test_returned_platform_and_direction_open_the_stop_timetable(api, ov):
    ov.route("R10", "10", 0)
    ov.route("RBUS", "5", 3)
    run(ov, "t0", "R10", ["A2", "End1"], direction=0)
    run(ov, "t1", "R10", ["A3", "End2"], direction=1)
    run(ov, "t2", "RBUS", ["A1", "End1"], direction=None)
    ov.second.route("b7", "7", 3)
    run(ov.second, "trip_b7", "b7", ["B1", "B9"], direction=1)
    data = body(api, "A1")
    checked = 0
    for item in data["lines"]:
        for direction in item["directions"]:
            response = api.get(
                f"lines/{item['line']['id']}/stops/{direction['platform_id']}/timetable/",
                direction=direction["direction"],
                date=MONDAY,
            )
            assert response.status_code == 200, (item["line"]["id"], direction, response.content)
            checked += 1
    assert checked == 4


# ------------------------------------------------------------------ stop search unchanged


def test_stop_search_still_groups_and_lists_vehicle_types(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"])
    ov.second.route("b7", "7", 3)
    run(ov.second, "trip_b7", "b7", ["B1", "B9"])
    found = api.get("stops/", q="hub").json()
    assert len(found) == 2
    near = next(r for r in found if sid("A1") in r["stop_ids"])
    far = next(r for r in found if r["stop_ids"] == [sid("F1")])
    assert set(near) == {"stop_id", "name", "lat", "lon", "vehicle_types", "stop_ids"}
    assert sorted(near["stop_ids"]) == [sid("A1"), sid("A2"), sid("A3"), sid("B1", SECOND)]
    assert near["vehicle_types"] == ["tram", "bus"]
    assert far["vehicle_types"] == []


def test_search_stop_id_opens_the_overview_of_the_same_group(api, ov):
    ov.route("R10", "10", 0)
    run(ov, "t1", "R10", ["A1", "End1"])
    near = next(r for r in api.get("stops/", q="hub").json() if sid("A1") in r["stop_ids"])
    data = body(api, near["stop_id"])
    assert sorted(data["stop"]["stop_ids"]) == sorted(near["stop_ids"])
    assert data["stop"]["vehicle_types"] == near["vehicle_types"]
