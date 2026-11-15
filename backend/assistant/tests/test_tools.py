"""Assistant tools and next-departures logic on the small fictional ttville GTFS dataset."""

from __future__ import annotations

import pytest

from assistant import chat as chat_module
from assistant.departures import upcoming_departures
from assistant.tests.conftest import CITY, at
from assistant.tests.fakes import ScriptedProvider, ask, call, say
from assistant.tools import ToolContext, run_tool
from cities.registry import get_city
from timetable.lines import Feeds

pytestmark = pytest.mark.django_db


def make_ctx(now="2026-11-16 05:00") -> ToolContext:
    return ToolContext(city=get_city(CITY), now=at(now))


def run(name, now="2026-11-16 05:00", **arguments):
    return run_tool(make_ctx(now), call(name, **arguments))


def result(name, now="2026-11-16 05:00", **arguments):
    out = run(name, now, **arguments)
    assert "result" in out, out
    return out["result"]


def times(data):
    return [d["time"] for d in data["departures"]]


# --------------------------------------------------------------------- next_departures


def test_next_departures_line_10_at_beta_from_early_morning(dataset):
    data = result("next_departures", stop_id="tt_main:S2", line="10")
    assert data["stop"] == "Beta"
    assert times(data)[:7] == ["05:17", "06:10", "09:00", "10:00", "11:10", "23:55", "00:20"]


def test_pickup_none_and_missing_departure_are_excluded(dataset):
    # m2 has pickup_type=1 at S2 (06:05); m3 has no departure time at S2 (07:05).
    shown = times(result("next_departures", stop_id="tt_main:S2", line="10"))
    assert "06:05" not in shown
    assert "07:05" not in shown
    assert "07:00" not in shown


def test_last_stop_of_a_trip_is_excluded(dataset):
    # Line 10 direction 0 ends at S4 (m1 arrives 05:27); only direction 1 starts there.
    data = result("next_departures", stop_id="tt_main:S4", line="10", now="2026-11-16 00:00")
    assert times(data)[0] == "06:00"
    assert "05:27" not in times(data)
    assert {d["headsign"] for d in data["departures"]} == {"Start place"}


def test_upcoming_departures_honours_the_limit(dataset):
    ctx = make_ctx("2026-11-16 00:00")
    rows = upcoming_departures(ctx.city, ctx.feeds, _pks(ctx, "S1", "S2"), ctx.now, limit=4)
    assert len(rows) == 4
    assert len({(r["trip_id"], r["date"], r["stop_id"]) for r in rows}) == 4


def _pks(ctx, *gtfs_ids):
    from transit_data.models import Stop

    return list(
        Stop.objects.filter(
            gtfs_id__in=gtfs_ids, feed_version_id__in=ctx.feeds.version_ids
        ).values_list("pk", flat=True)
    )


def test_ten_departures_never_more_and_ascending_by_instant(dataset):
    data = result("next_departures", stop_id="tt_main:S2", limit=1000, now="2026-11-16 00:00")
    assert len(data["departures"]) == 10
    # A day of trips at S2 across two lines is in clock order on the first service day.
    first_day = [
        d
        for d in data["departures"]
        if d["service_date"] == "2026-11-16" and not d["after_midnight"]
    ]
    assert times({"departures": first_day}) == sorted(times({"departures": first_day}))


@pytest.mark.parametrize(("limit", "expected"), [(1, 1), (3, 3), (1000, 10), (0, 10), (-5, 1)])
def test_limit_is_clamped(dataset, limit, expected):
    data = result("next_departures", stop_id="tt_main:S2", limit=limit)
    assert len(data["departures"]) == expected


def test_limit_that_is_not_a_number_is_an_error(dataset):
    assert run("next_departures", stop_id="tt_main:S2", limit="many")["error"] == (
        "invalid_argument"
    )


def test_after_midnight_trip_of_yesterdays_service_day(dataset):
    # Tuesday 00:10: trip m5 of Monday's service day leaves S1 at 24:15 = 00:15 Tuesday.
    data = result("next_departures", stop_id="tt_main:S1", line="10", now="2026-11-17 00:10")
    first = data["departures"][0]
    assert first["time"] == "00:15"
    assert first["after_midnight"] is True
    assert first["service_date"] == "2026-11-16"


def test_after_midnight_departures_carry_the_service_date_in_the_card(dataset):
    ctx = make_ctx("2026-11-17 00:10")
    rows = upcoming_departures(ctx.city, ctx.feeds, _pks(ctx, "S1"), ctx.now, 3)
    assert rows[0]["next_day"] is True
    assert rows[0]["date"] == "2026-11-16"
    assert rows[0]["time"] == "00:15"


def test_late_evening_question_gets_tonight_and_after_midnight(dataset):
    data = result("next_departures", stop_id="tt_main:S1", line="10", now="2026-11-16 23:00")
    assert times(data)[:2] == ["23:50", "00:15"]
    assert data["departures"][1]["service_date"] == "2026-11-16"
    assert data["departures"][1]["after_midnight"] is True


def test_departure_exactly_now_is_included_and_past_ones_are_not(dataset):
    assert (
        times(result("next_departures", stop_id="tt_main:S1", line="10", now="2026-11-16 05:12"))[0]
        == "05:12"
    )
    assert (
        times(result("next_departures", stop_id="tt_main:S1", line="10", now="2026-11-16 05:13"))[0]
        != "05:12"
    )


def test_service_day_follows_the_calendar(dataset):
    # Saturday: only sa1 (07:00) runs on line 10, Sunday only su1 (08:00).
    sat = result("next_departures", stop_id="tt_main:S1", line="10", now="2026-11-21 00:30")
    assert times(sat)[0] == "07:00"
    sun = result("next_departures", stop_id="tt_main:S1", line="10", now="2026-11-22 00:30")
    assert times(sun)[0] == "08:00"


def test_holiday_runs_the_sunday_timetable(dataset):
    data = result("next_departures", stop_id="tt_main:S1", line="10", now="2026-11-11 00:30")
    assert times(data)[0] == "08:00"


def test_departures_use_the_city_time_zone_not_utc(dataset):
    # 2026-11-16 05:00 Warsaw is 04:00 UTC; the same instant given in UTC gives the same result.
    from datetime import UTC

    ctx = make_ctx("2026-11-16 05:00")
    ctx.now = ctx.now.astimezone(UTC)
    rows = upcoming_departures(ctx.city, ctx.feeds, _pks(ctx, "S2"), ctx.now, 1)
    assert rows[0]["time"] == "05:17"


def test_summer_time_day_is_handled(dataset):
    # 2026-03-29 is the DST switch (a Sunday): the Sunday service still gives 08:00 local.
    data = result("next_departures", stop_id="tt_main:S1", line="10", now="2026-03-29 00:30")
    assert times(data)[0] == "08:00"


def test_stop_group_includes_all_platforms_but_not_far_namesakes(dataset):
    data = result("next_departures", stop_id="tt_main:S3", now="2026-11-16 07:30")
    lines = {d["line"] for d in data["departures"]}
    assert "52" in lines  # leaves from platform S3b, same name ~100 m away
    assert "99" not in lines  # S3far is a different stop group
    assert "77" not in lines  # different name


def test_card_departures_know_their_own_platform(dataset):
    ctx = make_ctx("2026-11-16 07:30")
    out = run_tool(ctx, call("next_departures", stop_id="tt_main:S3"))["result"]
    assert out["stop"] == "Gamma"
    card = ctx.final_cards()[0]
    by_line = {d["line"]["short_name"]: d["stop_id"] for d in card["departures"]}
    assert by_line["52"] == "tt_main:S3b"
    assert by_line["10"] == "tt_main:S3"
    assert card["stop"]["name"] == "Gamma"
    assert card["stop"]["stop_id"] in {"tt_main:S3", "tt_main:S3b"}


def test_asking_for_a_platform_of_the_group_gives_the_whole_group(dataset):
    via_s3b = result("next_departures", stop_id="tt_main:S3b", now="2026-11-16 07:30")
    via_s3 = result("next_departures", stop_id="tt_main:S3", now="2026-11-16 07:30")
    assert via_s3b["departures"] == via_s3["departures"]


def test_unknown_line_filter_is_an_error(dataset):
    assert run("next_departures", stop_id="tt_main:S2", line="ZZZ")["error"] == "unknown_line"


def test_line_filter_accepts_the_line_id(dataset):
    data = result("next_departures", stop_id="tt_main:S2", line="tt_main:R10")
    assert {d["line"] for d in data["departures"]} == {"10"}


def test_old_feed_versions_and_unconfigured_feeds_never_appear(dataset):
    data = result("next_departures", stop_id="tt_main:S2", now="2026-11-16 00:00", limit=10)
    assert "OLD" not in {d["line"] for d in data["departures"]}
    assert run("list_lines")["result"]["count"] >= 1
    assert "ZZ" not in {line["name"] for line in result("list_lines")["lines"]}


def test_stop_without_service_returns_empty_list_and_no_card(dataset):
    ctx = make_ctx("2026-11-16 23:59")
    out = run_tool(ctx, call("next_departures", stop_id="tt_main:S4", line="N1"))["result"]
    # N1 runs 01:00-01:05 on service days; a late-evening look still finds tomorrow's trip,
    # so use a date outside the calendar to get nothing at all.
    assert isinstance(out["departures"], list)
    ctx = make_ctx("2027-06-01 12:00")
    out = run_tool(ctx, call("next_departures", stop_id="tt_main:S2"))["result"]
    assert out["departures"] == []
    assert ctx.final_cards() == []


def test_unknown_stop_is_an_error(dataset):
    assert run("next_departures", stop_id="tt_main:NOPE")["error"] == "unknown_stop"


def test_blank_headsign_falls_back_to_the_last_stop_name(dataset):
    data = result("next_departures", stop_id="tt_main:S1", line="BLK", now="2026-11-16 12:00")
    assert data["departures"][0]["headsign"] == "Beta"


def test_trip_without_direction_id_gets_direction_zero(dataset):
    ctx = make_ctx("2026-11-16 07:00")
    out = run_tool(ctx, call("next_departures", stop_id="tt_main:S1", line="20"))
    assert out["result"]["departures"][0]["time"] == "08:00"
    assert ctx.final_cards()[0]["departures"][0]["direction"] == 0


# -------------------------------------------------------------------- argument checks


def test_unknown_tool_name(dataset):
    assert run_tool(make_ctx(), call("drop_database")) == {"error": "unknown_tool"}


def test_missing_required_arguments(dataset):
    assert run("search_stops") == {"error": "missing_argument", "argument": "query"}
    assert run("search_stops", query="   ")["error"] == "missing_argument"
    assert run("next_departures")["error"] == "missing_argument"
    assert run("plan_journey", from_stop_id="tt_main:S1")["error"] == "missing_argument"
    assert run("get_line_route")["error"] == "missing_argument"
    assert run("get_stop_timetable", line="10")["error"] == "missing_argument"


def test_arguments_of_the_wrong_type_are_rejected(dataset):
    assert run("search_stops", query={"$ne": 1})["error"] == "invalid_argument"
    assert run("search_stops", query=["a", "b"])["error"] == "invalid_argument"
    assert run("get_line_route", line="10", direction="sideways")["error"] == "invalid_argument"


def test_none_arguments_are_treated_as_empty(dataset):
    assert run_tool(make_ctx(), call("list_lines"))["result"]["count"] > 0


def test_short_search_query_is_rejected(dataset):
    assert run("search_stops", query="a")["error"] == "query_too_short"


def test_overlong_argument_is_capped_not_crashing(dataset):
    assert run("search_stops", query="a" * 100_000)["result"] == {"stops": []}


def test_sql_like_input_is_just_text(dataset):
    out = run("search_stops", query="'; DROP TABLE transit_data_stop; --")
    assert out["result"] == {"stops": []}
    assert result("search_stops", query="Alpha")["stops"]


def test_search_stops_returns_at_most_five(dataset):
    assert len(result("search_stops", query="ta")["stops"]) <= 5


def test_search_stops_ignores_case_and_diacritics(dataset):
    assert result("search_stops", query="ALPHA")["stops"][0]["name"] == "Alpha"


def test_get_line_route_checks_direction_and_date(dataset):
    assert run("get_line_route", line="10", direction=7)["error"] == "invalid_argument"
    assert run("get_line_route", line="10", date="16-11-2026")["error"] == "invalid_argument"
    assert run("get_line_route", line="10", date="2026-02-30")["error"] == "invalid_argument"
    assert run("get_line_route", line="nope")["error"] == "unknown_line"


def test_get_line_route_lists_stops_in_order(dataset):
    data = result("get_line_route", line="10", direction=0, date="2026-11-16")
    names = [s["name"] for s in data["stops"]]
    assert names[-1] == "Delta"
    assert names.index("Alpha") < names.index("Beta")
    assert names.index("Beta") < names.index("Gamma")


def test_list_lines_validates_vehicle_type_and_filters(dataset):
    assert run("list_lines", vehicle_type="spaceship")["error"] == "invalid_argument"
    trams = result("list_lines", vehicle_type="tram")["lines"]
    assert trams and {line["vehicle_type"] for line in trams} == {"tram"}
    assert [line["name"] for line in result("list_lines", query="52")["lines"]] == ["52"]


def test_stop_timetable_covers_both_directions_and_marks_after_midnight(dataset):
    data = result("get_stop_timetable", line="10", stop_id="tt_main:S2", date="2026-11-16")
    assert data["stop"] == "Beta"
    assert {t["direction"] for t in data["timetables"]} == {0, 1}
    forward = next(t for t in data["timetables"] if t["direction"] == 0)
    assert forward["date"] == "2026-11-16"
    assert any(item.endswith("(+1 day)") for item in forward["departures"])
    assert "06:05" not in forward["departures"]  # no pickup


def test_stop_timetable_errors(dataset):
    assert run("get_stop_timetable", line="10", stop_id="tt_main:S2", date="x")["error"] == (
        "invalid_argument"
    )
    assert run("get_stop_timetable", line="10", stop_id="tt_main:NOPE")["error"] == "unknown_stop"
    assert run("get_stop_timetable", line="52", stop_id="tt_main:S1")["error"] == (
        "line_does_not_stop_here"
    )


def test_plan_journey_argument_errors(dataset, fake_otp):
    base = {"from_stop_id": "tt_main:S1", "to_stop_id": "tt_main:S4"}
    assert run("plan_journey", **{**base, "from_stop_id": "tt_main:NOPE"})["error"] == (
        "unknown_stop"
    )
    assert run("plan_journey", from_stop_id="tt_main:S1", to_stop_id="tt_main:S1")["error"] == (
        "same_start_and_destination"
    )
    assert run("plan_journey", **base, time="tomorrow")["error"] == "invalid_argument"
    assert fake_otp.calls == []


def test_plan_journey_naive_time_is_city_local_time(dataset, fake_otp):
    result(
        "plan_journey", from_stop_id="tt_main:S1", to_stop_id="tt_main:S4", time="2026-11-16T08:00"
    )
    sent = str(fake_otp.transit_call)
    assert "08:00" in sent or "2026-11-16" in sent


def test_plan_journey_result_for_the_model_is_compact(dataset, fake_otp):
    from journeys.tests.conftest import itinerary, place, plan, route, transit_leg

    s1 = place("Alpha", 50.06, 19.94, "tt_main:S1")
    s4 = place("Delta", 50.0627, 19.94, "tt_main:S4")
    leg = transit_leg("2026-11-16T07:00:00Z", "2026-11-16T07:20:00Z", s1, s4, route())
    fake_otp.transit = plan(*[itinerary("2026-11-16T07:00:00Z", "2026-11-16T07:20:00Z", [leg])] * 5)
    data = result("plan_journey", from_stop_id="tt_main:S1", to_stop_id="tt_main:S4")
    assert len(data["itineraries"]) <= 3
    first = data["itineraries"][0]
    assert first["departure"] == "08:00"  # 07:00Z is 08:00 in Warsaw in November
    assert first["legs"][0]["line"] == "10"


# ----------------------------------------------------------------- chat loop details


def test_extra_tool_calls_in_one_round_get_an_error_result(dataset):
    provider = ScriptedProvider(
        ask(*[call("search_stops", query="Alpha") for _ in range(7)]), say("done")
    )
    chat_module.answer(get_city(CITY), [{"role": "user", "text": "hi"}], "en", provider=provider)
    results = provider.tool_results
    assert len(results) == 7
    assert [r.get("error") for r in results[5:]] == ["too_many_tool_calls"] * 2
    assert all("result" in r for r in results[:5])


def test_answer_accepts_an_explicit_provider_and_clock(dataset):
    provider = ScriptedProvider(
        ask(call("next_departures", stop_id="tt_main:S1", line="10")), say("ok")
    )
    out = chat_module.answer(
        get_city(CITY),
        [{"role": "user", "text": "x"}],
        "pl",
        provider=provider,
        now=at("2026-11-16 05:00"),
    )
    assert out["cards"][0]["departures"][0]["time"] == "05:12"
    assert "2026-11-16 05:00" in provider.calls[0]["system"]
    assert "Monday" in provider.calls[0]["system"]


def test_feeds_helper_sees_only_active_configured_versions(dataset):
    feeds = Feeds(get_city(CITY))
    assert len(feeds.version_ids) == 2  # tt_main and tt_second, not superseded / unconfigured
