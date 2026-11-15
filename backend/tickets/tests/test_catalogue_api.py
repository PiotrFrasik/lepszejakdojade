"""GET /cities/{city}/tickets/ (docs/api.md, "Tickets (#14)")."""

import pytest

from .conftest import OTHER, make_ticket

pytestmark = pytest.mark.django_db

TICKET_FIELDS = {
    "id",
    "name",
    "description",
    "kind",
    "validity_minutes",
    "zones",
    "reduced",
    "price",
    "currency",
    "prices_as_of",
    "source_url",
}


def ids(response):
    return [t["id"] for t in response.json()["tickets"]]


def test_response_shape(api):
    make_ticket("t60", price="6.00")
    response = api.catalogue()
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"zones", "tickets"}
    assert isinstance(body["tickets"], list)  # not paginated
    assert body["tickets"][0] == {
        "id": "t60",
        "name": "Bilet t60",
        "description": "Opis",
        "kind": "time",
        "validity_minutes": 60,
        "zones": ["1"],
        "reduced": False,
        "price": "6.00",
        "currency": "PLN",
        "prices_as_of": "2026-11-01",
        "source_url": "https://tickets.invalid/prices",
    }
    assert set(body["tickets"][0]) == TICKET_FIELDS


def test_price_is_decimal_string_with_two_places(api):
    make_ticket("a", price="6")
    make_ticket("b", price="3.5", reduced=True)
    prices = {t["id"]: t["price"] for t in api.catalogue().json()["tickets"]}
    assert prices == {"a": "6.00", "b": "3.50"}


def test_single_has_null_validity(api):
    make_ticket("s", kind="single")
    assert api.catalogue().json()["tickets"][0]["validity_minutes"] is None


def test_empty_catalogue_still_lists_zones(api):
    body = api.catalogue().json()
    assert body["tickets"] == []
    assert [z["id"] for z in body["zones"]] == ["1", "2", "3"]


def test_zones_in_config_order_with_names_per_language(api):
    assert api.catalogue(lang="en").json()["zones"] == [
        {"id": "1", "name": "Ring I"},
        {"id": "2", "name": "Ring II"},
        {"id": "3", "name": "Ring III"},
    ]
    assert [z["name"] for z in api.catalogue(lang="pl").json()["zones"]] == [
        "Pierscien I",
        "Pierscien II",
        "Pierscien III",
    ]


def test_sort_order_kind_validity_zones_reduced_id(api):
    make_ticket("period30", kind="period", minutes=30 * 1440)
    make_ticket("daily1", kind="daily", minutes=1440)
    make_ticket("daily2", kind="daily", minutes=2880)
    make_ticket("t90", minutes=90)
    make_ticket("t60-z12", minutes=60, zones=("1", "2"))
    make_ticket("t60-z1-red", minutes=60, reduced=True)
    make_ticket("t60-z1-b", minutes=60)
    make_ticket("t60-z1-a", minutes=60)
    make_ticket("t20", minutes=20)
    make_ticket("single-z2", kind="single", zones=("1", "2"))
    make_ticket("single-z1", kind="single")
    assert ids(api.catalogue()) == [
        "single-z1",
        "single-z2",
        "t20",
        "t60-z1-a",
        "t60-z1-b",
        "t60-z1-red",
        "t60-z12",
        "t90",
        "daily1",
        "daily2",
        "period30",
    ]


def test_period_7_days_sorts_before_30_days(api):
    make_ticket("p30", kind="period", minutes=30 * 1440)
    make_ticket("p7", kind="period", minutes=7 * 1440)
    assert ids(api.catalogue()) == ["p7", "p30"]


def test_reduced_filter(api):
    make_ticket("std")
    make_ticket("red", reduced=True)
    assert ids(api.catalogue()) == ["std", "red"]
    assert ids(api.catalogue(reduced="true")) == ["red"]
    assert ids(api.catalogue(reduced="false")) == ["std"]


@pytest.mark.parametrize("value", ["yes", "1", "TRUE", "maybe", "0"])
def test_invalid_reduced_is_400(api, value):
    make_ticket("std")
    response = api.catalogue(reduced=value)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "reduced" in error["details"]


def test_only_active_tickets(api):
    make_ticket("on")
    make_ticket("off", active=False)
    make_ticket("off-red", active=False, reduced=True)
    assert ids(api.catalogue()) == ["on"]
    assert ids(api.catalogue(reduced="true")) == []


def test_only_tickets_of_the_requested_city(api):
    make_ticket("mine")
    make_ticket("theirs", city=OTHER)
    assert ids(api.catalogue()) == ["mine"]
    assert ids(api.catalogue(city=OTHER)) == ["theirs"]


def test_unknown_city_is_404(api):
    response = api.catalogue(city="atlantis")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_cache_control_max_age_300(api):
    response = api.catalogue()
    assert "max-age=300" in response["Cache-Control"]


def test_no_authentication_needed(api):
    assert api.catalogue().status_code == 200


def test_post_on_catalogue_not_allowed(api):
    assert api.client.post(api.url(), {}, format="json").status_code == 405


# --- language -----------------------------------------------------------------------------------


def test_translated_name_and_description_follow_accept_language(api):
    make_ticket(
        "t",
        name_pl="Bilet 60",
        name_en="60-minute ticket",
        description_pl="PL opis",
        description_en="EN description",
    )
    en = api.catalogue(lang="en").json()["tickets"][0]
    pl = api.catalogue(lang="pl").json()["tickets"][0]
    assert (en["name"], en["description"]) == ("60-minute ticket", "EN description")
    assert (pl["name"], pl["description"]) == ("Bilet 60", "PL opis")


def test_default_language_is_polish(api):
    make_ticket("t", name_pl="Bilet 60", name_en="60-minute ticket")
    assert api.catalogue().json()["tickets"][0]["name"] == "Bilet 60"


def test_empty_english_falls_back_to_polish(api):
    make_ticket("t", name_pl="Bilet 60", name_en="", description_pl="PL opis", description_en="")
    ticket = api.catalogue(lang="en").json()["tickets"][0]
    assert ticket["name"] == "Bilet 60"
    assert ticket["description"] == "PL opis"


def test_content_language_header(api):
    assert api.catalogue(lang="en")["Content-Language"] == "en"
    assert api.catalogue(lang="pl")["Content-Language"] == "pl"
    assert api.catalogue()["Content-Language"] == "pl"


def test_empty_reduced_is_treated_as_omitted(api):
    make_ticket("std")
    make_ticket("red", reduced=True)
    response = api.catalogue(reduced="")
    assert response.status_code == 200
    assert ids(response) == ["std", "red"]
