"""POST /cities/{city}/tickets/suggest/ (docs/api.md, "Tickets (#14)")."""

import pytest

from .conftest import NO_ZONES, OTHER, make_ticket

pytestmark = pytest.mark.django_db


def suggested(api, body, **kwargs):
    response = api.suggest(body, **kwargs)
    assert response.status_code == 200, response.json()
    ticket = response.json()["ticket"]
    return ticket["id"] if ticket else None


# --- validation ---------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, -1, 86401, 1.5, "abc", None, []])
def test_invalid_duration_is_400(api, value):
    response = api.suggest({"duration_seconds": value})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "duration_seconds" in error["details"]


def test_duration_is_required(api):
    response = api.suggest({})
    assert response.status_code == 400
    assert "duration_seconds" in response.json()["error"]["details"]


@pytest.mark.parametrize("duration", [1, 86400])
def test_duration_bounds_are_accepted(api, duration):
    assert api.suggest({"duration_seconds": duration}).status_code == 200


def test_negative_transfers_is_400(api):
    response = api.suggest({"duration_seconds": 600, "transfers": -1})
    assert response.status_code == 400
    assert "transfers" in response.json()["error"]["details"]


def test_non_integer_transfers_is_400(api):
    assert api.suggest({"duration_seconds": 600, "transfers": "x"}).status_code == 400


def test_unknown_zone_is_400_with_details(api):
    make_ticket("t")
    response = api.suggest({"duration_seconds": 600, "zones": ["1", "9"]})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "zones" in error["details"]


def test_empty_zones_is_400(api):
    response = api.suggest({"duration_seconds": 600, "zones": []})
    assert response.status_code == 400
    assert "zones" in response.json()["error"]["details"]


def test_zone_of_another_city_is_unknown(api):
    # "otherville" has only zone 1; zone 3 exists in "tkville" only.
    response = api.suggest({"duration_seconds": 600, "zones": ["3"]}, city=OTHER)
    assert response.status_code == 400


def test_unknown_city_is_404(api):
    response = api.suggest({"duration_seconds": 600}, city="atlantis")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_not_allowed(api):
    assert api.client.get(api.url("suggest/")).status_code == 405


# --- selection ----------------------------------------------------------------------------------


def test_response_shape(api):
    make_ticket("t60", name_en="60-minute ticket", price="6.00")
    response = api.suggest({"duration_seconds": 1680, "transfers": 1}, lang="en")
    body = response.json()
    assert set(body) == {"ticket", "reason"}
    assert body["ticket"]["id"] == "t60"
    assert body["ticket"]["price"] == "6.00"
    assert isinstance(body["reason"], str) and body["reason"]
    assert response["Content-Language"] == "en"


def test_default_zone_is_first_zone_of_city(api):
    make_ticket("z1", zones=("1",), price="6.00")
    make_ticket("z2-only", zones=("2",), price="1.00")
    assert suggested(api, {"duration_seconds": 600}) == "z1"
    assert suggested(api, {"duration_seconds": 600, "zones": ["2"]}) == "z2-only"


def test_ticket_must_cover_all_requested_zones(api):
    make_ticket("z1", zones=("1",), price="1.00")
    make_ticket("z12", zones=("1", "2"), price="2.00")
    make_ticket("z123", zones=("1", "2", "3"), price="3.00")
    assert suggested(api, {"duration_seconds": 600, "zones": ["1", "2"]}) == "z12"
    assert suggested(api, {"duration_seconds": 600, "zones": ["2", "3"]}) == "z123"
    assert suggested(api, {"duration_seconds": 600, "zones": ["3"]}) == "z123"


def test_zone_order_in_request_does_not_matter(api):
    make_ticket("z12", zones=("1", "2"))
    assert suggested(api, {"duration_seconds": 600, "zones": ["2", "1"]}) == "z12"


def test_duplicate_zones_in_request_are_tolerated(api):
    make_ticket("z1")
    response = api.suggest({"duration_seconds": 600, "zones": ["1", "1"]})
    assert response.status_code == 200
    assert response.json()["ticket"]["id"] == "z1"


def test_validity_must_cover_duration(api):
    make_ticket("t20", minutes=20, price="3.00")
    make_ticket("t60", minutes=60, price="6.00")
    make_ticket("t90", minutes=90, price="8.00")
    assert suggested(api, {"duration_seconds": 1200}) == "t20"  # exactly 20 minutes
    assert suggested(api, {"duration_seconds": 1201}) == "t60"
    assert suggested(api, {"duration_seconds": 3600}) == "t60"
    assert suggested(api, {"duration_seconds": 3601}) == "t90"
    assert suggested(api, {"duration_seconds": 5401}) is None


def test_cheapest_wins_even_if_longer(api):
    make_ticket("t20", minutes=20, price="4.00")
    make_ticket("t60", minutes=60, price="3.00")  # odd, but cheaper
    assert suggested(api, {"duration_seconds": 600}) == "t60"


def test_single_only_without_transfers(api):
    make_ticket("single", kind="single", price="4.00")
    make_ticket("t60", minutes=60, price="6.00")
    assert suggested(api, {"duration_seconds": 600, "transfers": 0}) == "single"
    assert suggested(api, {"duration_seconds": 600}) == "single"  # default transfers = 0
    assert suggested(api, {"duration_seconds": 600, "transfers": 1}) == "t60"
    assert suggested(api, {"duration_seconds": 600, "transfers": 5}) == "t60"


def test_single_covers_any_duration_without_transfers(api):
    make_ticket("single", kind="single", price="4.00")
    assert suggested(api, {"duration_seconds": 86400}) == "single"


def test_single_with_transfers_and_nothing_else_gives_null(api):
    make_ticket("single", kind="single")
    response = api.suggest({"duration_seconds": 600, "transfers": 1})
    assert response.status_code == 200
    assert response.json()["ticket"] is None


def test_never_daily_or_period(api):
    make_ticket("daily", kind="daily", minutes=1440, price="0.50")
    make_ticket("period", kind="period", minutes=7 * 1440, price="0.10")
    make_ticket("t60", minutes=60, price="6.00")
    assert suggested(api, {"duration_seconds": 600}) == "t60"
    assert suggested(api, {"duration_seconds": 4000}) is None


def test_reduced_matching(api):
    make_ticket("std", price="6.00")
    make_ticket("red", price="3.00", reduced=True)
    assert suggested(api, {"duration_seconds": 600}) == "std"  # default reduced=false
    assert suggested(api, {"duration_seconds": 600, "reduced": False}) == "std"
    assert suggested(api, {"duration_seconds": 600, "reduced": True}) == "red"


def test_reduced_only_catalogue_gives_null_for_standard(api):
    make_ticket("red", reduced=True)
    assert suggested(api, {"duration_seconds": 600}) is None


def test_inactive_tickets_ignored(api):
    make_ticket("off", price="1.00", active=False)
    make_ticket("on", price="6.00")
    assert suggested(api, {"duration_seconds": 600}) == "on"


def test_other_city_tickets_ignored(api):
    make_ticket("theirs", city=OTHER, price="1.00")
    assert suggested(api, {"duration_seconds": 600}) is None
    assert suggested(api, {"duration_seconds": 600}, city=OTHER) == "theirs"


def test_tie_prefers_shorter_validity(api):
    make_ticket("t90", minutes=90, price="6.00")
    make_ticket("t60", minutes=60, price="6.00")
    assert suggested(api, {"duration_seconds": 600}) == "t60"


def test_tie_single_beats_time_ticket(api):
    make_ticket("t60", minutes=60, price="6.00")
    make_ticket("single", kind="single", price="6.00")
    assert suggested(api, {"duration_seconds": 600}) == "single"


def test_tie_prefers_fewer_zones(api):
    make_ticket("z12", zones=("1", "2"), minutes=60, price="6.00")
    make_ticket("z1", zones=("1",), minutes=60, price="6.00")
    assert suggested(api, {"duration_seconds": 600}) == "z1"


def test_tie_falls_back_to_id(api):
    make_ticket("b", price="6.00")
    make_ticket("a", price="6.00")
    assert suggested(api, {"duration_seconds": 600}) == "a"


# --- reason -------------------------------------------------------------------------------------


def test_reason_mentions_ticket_and_zone_in_english(api):
    make_ticket("t60", name_en="60-minute ticket")
    reason = api.suggest({"duration_seconds": 1680}, lang="en").json()["reason"]
    assert "60-minute ticket" in reason
    assert "Ring I" in reason
    assert "28" in reason


def test_reason_in_polish_differs_and_uses_polish_names(api):
    make_ticket("t60", name_pl="Bilet 60-minutowy", name_en="60-minute ticket")
    en = api.suggest({"duration_seconds": 1680}, lang="en").json()["reason"]
    pl = api.suggest({"duration_seconds": 1680}, lang="pl").json()["reason"]
    assert pl != en
    assert "Bilet 60-minutowy" in pl
    assert "Pierscien I" in pl
    assert "Ring" not in pl


def test_reason_rounds_duration_up_to_whole_minutes(api):
    make_ticket("t60")
    reason = api.suggest({"duration_seconds": 1681}, lang="en").json()["reason"]
    assert "29" in reason


def test_reason_for_no_ticket_in_both_languages(api):
    make_ticket("t20", minutes=20)
    body = {"duration_seconds": 7200, "zones": ["1", "2"]}
    en = api.suggest(body, lang="en").json()
    pl = api.suggest(body, lang="pl").json()
    assert en["ticket"] is None and pl["ticket"] is None
    assert en["reason"] and pl["reason"]
    assert en["reason"] != pl["reason"]
    assert "120" in en["reason"]
    assert "Ring I, Ring II" in en["reason"]
    assert "Pierscien I, Pierscien II" in pl["reason"]


def test_reason_for_single_mentions_no_transfers(api):
    make_ticket("single", kind="single", name_en="Single ride")
    reason = api.suggest({"duration_seconds": 600}, lang="en").json()["reason"]
    assert "Single ride" in reason
    assert "transfer" in reason.lower()


def test_reason_falls_back_to_polish_name_when_english_empty(api):
    make_ticket("t60", name_pl="Bilet 60", name_en="")
    reason = api.suggest({"duration_seconds": 600}, lang="en").json()["reason"]
    assert "Bilet 60" in reason


def test_city_without_zones_and_omitted_zones_is_400(api):
    response = api.suggest({"duration_seconds": 600}, city=NO_ZONES)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "zones" in error["details"]
