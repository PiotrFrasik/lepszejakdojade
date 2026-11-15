"""GET /cities/{city}/trips/{trip_id}/ and translated errors (docs/api.md, #10)."""

import pytest

from .conftest import DST_START_SUNDAY, MAIN, MONDAY, SATURDAY, SUNDAY, Builder

pytestmark = pytest.mark.django_db

LINE = f"{MAIN}:R10"


def sid(gtfs_id):
    return f"{MAIN}:{gtfs_id}"


def trip(api, gtfs_id, **params):
    return api.get(f"trips/{sid(gtfs_id)}/", **params)


def test_trip_response_shape_and_content(api, dataset):
    response = trip(api, "m1", date=MONDAY)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "trip_id", "date", "line", "direction", "headsign", "wheelchair_accessible", "stops"
    }  # fmt: skip
    assert body["trip_id"] == sid("m1")
    assert body["date"] == MONDAY
    assert body["line"]["id"] == LINE
    assert body["direction"] == 0
    assert body["headsign"] == "Terminus A"
    assert body["wheelchair_accessible"] is True
    assert [s["stop_id"] for s in body["stops"]] == [sid(x) for x in ("S1", "S2", "S3", "S4")]
    assert body["stops"][0] == {
        "stop_id": sid("S1"),
        "name": "Alpha",
        "arrival": "2026-11-16T05:12:00+01:00",
        "departure": "2026-11-16T05:12:00+01:00",
    }


def test_times_have_summer_offset_in_summer(api, dataset):
    body = trip(api, "m1", date="2026-07-06").json()  # Monday in July
    assert body["stops"][0]["departure"] == "2026-07-06T05:12:00+02:00"


def test_times_past_midnight_roll_into_next_calendar_day(api, dataset):
    stops = trip(api, "m5", date=MONDAY).json()["stops"]
    assert stops[0]["departure"] == "2026-11-17T00:15:00+01:00"
    assert stops[-1]["arrival"] == "2026-11-17T00:30:00+01:00"


def test_spring_forward_day_uses_new_offset(api, dataset):
    stops = trip(api, "su1", date=DST_START_SUNDAY).json()["stops"]
    assert stops[0]["departure"] == "2026-03-29T08:00:00+02:00"


def test_missing_times_are_null(api, dataset):
    stops = trip(api, "m3", date=MONDAY).json()["stops"]
    s2 = next(s for s in stops if s["stop_id"] == sid("S2"))
    assert s2["arrival"] == "2026-11-16T07:05:00+01:00"
    assert s2["departure"] is None


def test_wheelchair_accessible_true_false_null(api, dataset):
    dataset.simple_trip("wc_no", "R10", "WK", ["S1", "S2"], "16:00", wheelchair=2)
    assert trip(api, "m1", date=MONDAY).json()["wheelchair_accessible"] is True
    assert trip(api, "wc_no", date=MONDAY).json()["wheelchair_accessible"] is False
    assert trip(api, "m2", date=MONDAY).json()["wheelchair_accessible"] is None


def test_trip_without_direction_id_reports_direction_zero(api, dataset):
    assert trip(api, "n1", date=MONDAY).json()["direction"] == 0


def test_direction_one_trip(api, dataset):
    body = trip(api, "d1", date=MONDAY).json()
    assert body["direction"] == 1
    assert body["headsign"] == "Start place"


def test_blank_headsign_falls_back_to_last_stop_name(api, dataset):
    assert trip(api, "blk1", date=MONDAY).json()["headsign"] == "Beta"


def test_trip_not_running_on_date_is_404(api, dataset):
    for day in (SATURDAY, SUNDAY):
        response = trip(api, "m1", date=day)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    assert trip(api, "sa1", date=SATURDAY).status_code == 200


def test_trip_on_holiday_follows_sunday_service(api, dataset):
    assert trip(api, "m1", date="2026-11-11").status_code == 404
    assert trip(api, "su1", date="2026-11-11").status_code == 200


def test_trip_outside_calendar_range_is_404(api, dataset):
    assert trip(api, "m1", date="2027-02-01").status_code == 404


def test_unknown_trip_is_404(api, dataset):
    assert trip(api, "nope", date=MONDAY).status_code == 404
    assert api.get("trips/garbage/", date=MONDAY).status_code == 404


def test_trip_of_superseded_feed_version_is_404(api, dataset):
    old = Builder(MAIN, status="superseded")
    old.calendar("WK", ["monday"])
    old.stop("S1", "Alpha")
    old.stop("S2", "Beta")
    old.route("R10", "10")
    old.simple_trip("only_old", "R10", "WK", ["S1", "S2"], "03:33")
    assert trip(api, "only_old", date=MONDAY).status_code == 404


def test_trip_of_feed_outside_city_is_404(api, dataset):
    b = Builder("unlisted_feed")
    b.calendar("WK", ["monday"])
    b.stop("S1", "Alpha")
    b.stop("S2", "Beta")
    b.route("ZZ", "ZZ")
    b.simple_trip("foreign", "ZZ", "WK", ["S1", "S2"], "03:33")
    assert api.get("trips/unlisted_feed:foreign/", date=MONDAY).status_code == 404


@pytest.mark.parametrize("value", ["2026-13-01", "x", "01-01-2026", "9999-12-31"])
def test_bad_date_is_400(api, dataset, value):
    response = trip(api, "m1", date=value)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert "date" in response.json()["error"]["details"]


def test_default_date_is_accepted(api, dataset):
    assert trip(api, "m1").status_code in (200, 404)


def test_unknown_city_is_404(api, dataset):
    assert api.get(f"trips/{sid('m1')}/", city="atlantis").status_code == 404


def test_slash_in_trip_id_resolves(api, dataset):
    dataset.simple_trip("x/y", "R10", "WK", ["S1", "S2"], "17:00")
    response = api.client.get(f"/api/v1/cities/ttville/trips/{MAIN}:x%2Fy/", {"date": MONDAY})
    assert response.status_code == 200
    assert response.json()["trip_id"] == f"{MAIN}:x/y"


def test_line_id_with_slash_resolves_in_route(api, dataset):
    dataset.route("a/b", "SL", 0)
    dataset.simple_trip("slash", "a/b", "WK", ["S1", "S2"], "14:00")
    response = api.client.get(f"/api/v1/cities/ttville/lines/{MAIN}:a%2Fb/route/", {"date": MONDAY})
    assert response.status_code == 200
    assert response.json()["line"]["id"] == f"{MAIN}:a/b"


# ----------------------------------------------------------------- translated errors

ERROR_CASES = [
    # (path, params, english message, polish message)
    (f"lines/{MAIN}:nope/route/", {}, "Line not found.", "Nie znaleziono linii."),
    (
        f"lines/{LINE}/route/",
        {"direction": 1, "date": MONDAY},
        None,
        None,
    ),
    (
        f"lines/{LINE}/stops/{MAIN}:nope/timetable/",
        {},
        "Stop not found.",
        "Nie znaleziono przystanku.",
    ),
    (
        f"lines/{LINE}/stops/{MAIN}:S3far/timetable/",
        {},
        "This line does not stop here in this direction.",
        "Ta linia nie zatrzymuje się na tym przystanku w tym kierunku.",
    ),
    (f"trips/{MAIN}:nope/", {}, "Trip not found.", "Nie znaleziono kursu."),
    (
        f"trips/{MAIN}:m1/",
        {"date": SUNDAY},
        "This trip does not run on this date.",
        "Ten kurs nie odbywa się w tym dniu.",
    ),
    ("lines/", {"vehicle_type": "boat"}, None, None),
]


@pytest.mark.parametrize("path,params,english,polish", [c for c in ERROR_CASES if c[2]])
def test_not_found_messages_translated(api, dataset, path, params, english, polish):
    for lang, expected in (("en", english), ("pl", polish), (None, polish)):
        response = api.get(path, lang=lang, **params)
        assert response.status_code == 404
        assert response.json()["error"] == {"code": "not_found", "message": expected}
        assert response["Content-Language"] == (lang or "pl")


def test_direction_not_served_message_translated(api, dataset):
    path = f"lines/{MAIN}:R52/route/"
    en = api.get(path, lang="en", direction=1, date=MONDAY).json()["error"]["message"]
    pl = api.get(path, lang="pl", direction=1, date=MONDAY).json()["error"]["message"]
    assert en == "This line does not run in this direction."
    assert pl == "Ta linia nie kursuje w tym kierunku."


def test_stop_not_in_direction_message_translated(api, dataset):
    path = f"lines/{LINE}/stops/{sid('D')}/timetable/"
    en = api.get(path, lang="en", direction=1).json()["error"]["message"]
    pl = api.get(path, lang="pl", direction=1).json()["error"]["message"]
    assert en == "This line does not stop here in this direction."
    assert pl == "Ta linia nie zatrzymuje się na tym przystanku w tym kierunku."


def test_unknown_city_message_translated(api, dataset):
    assert api.get("lines/", lang="en", city="atlantis").json()["error"]["message"] == (
        "City not found."
    )
    assert api.get("lines/", lang="pl", city="atlantis").json()["error"]["message"] == (
        "Nie znaleziono miasta."
    )


def test_validation_message_and_details_language(api, dataset):
    en = api.get("lines/", lang="en", vehicle_type="boat")
    pl = api.get("lines/", lang="pl", vehicle_type="boat")
    assert en.status_code == pl.status_code == 400
    assert en.json()["error"]["code"] == pl.json()["error"]["code"] == "validation_error"
    assert en.json()["error"]["message"] != pl.json()["error"]["message"]
    assert en["Content-Language"] == "en" and pl["Content-Language"] == "pl"


def test_date_out_of_range_message_translated(api, dataset):
    en = api.get("trips/x:y/", lang="en", date="9999-12-31").json()["error"]
    pl = api.get("trips/x:y/", lang="pl", date="9999-12-31").json()["error"]
    assert "Date is out of range." in str(en["details"]) or en["message"] == "Date is out of range."
    assert "poza" in str(pl["details"]) + pl["message"]


def test_successful_response_has_content_language(api, dataset):
    assert api.get("lines/", lang="en")["Content-Language"] == "en"
    assert api.get("lines/", lang="pl")["Content-Language"] == "pl"


def test_proper_names_are_not_translated(api, dataset):
    en = api.get(f"lines/{LINE}/route/", lang="en", date=MONDAY).json()
    pl = api.get(f"lines/{LINE}/route/", lang="pl", date=MONDAY).json()
    assert en == pl
