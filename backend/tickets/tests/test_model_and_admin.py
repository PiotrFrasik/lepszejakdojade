"""Ticket model validation, DB constraints and the admin pages."""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from tickets.models import Ticket

from .conftest import CITY, make_ticket

pytestmark = pytest.mark.django_db


def build(**overrides):
    fields = {
        "id": "x",
        "city_id": CITY,
        "name": "X",
        "kind": "time",
        "validity_minutes": 60,
        "zones": ["1"],
        "price": Decimal("6.00"),
        "currency": "PLN",
        "prices_as_of": date(2026, 11, 1),
        "source_url": "https://tickets.invalid/prices",
    }
    fields.update(overrides)
    return Ticket(**fields)


def errors_of(ticket):
    with pytest.raises(ValidationError) as info:
        ticket.clean()
    return info.value.message_dict


def test_valid_tickets_pass_clean(city_config):
    build().clean()
    build(kind="single", validity_minutes=None).clean()
    build(kind="daily", validity_minutes=2880).clean()
    build(kind="period", validity_minutes=7 * 1440).clean()
    build(kind="period", validity_minutes=30 * 1440).clean()


def test_unknown_city(city_config):
    assert "city_id" in errors_of(build(city_id="atlantis"))


def test_empty_zones(city_config):
    assert "zones" in errors_of(build(zones=[]))


def test_unknown_zone(city_config):
    assert "zones" in errors_of(build(zones=["1", "9"]))


def test_duplicate_zones(city_config):
    assert "zones" in errors_of(build(zones=["1", "1"]))


def test_zone_of_other_city_is_unknown(city_config):
    assert "zones" in errors_of(build(city_id="otherville", zones=["2"]))


def test_zones_are_normalised_to_config_order(city_config):
    ticket = build(zones=["3", "1"])
    ticket.clean()
    assert ticket.zones == ["1", "3"]


def test_single_must_not_have_validity(city_config):
    assert "validity_minutes" in errors_of(build(kind="single", validity_minutes=60))


@pytest.mark.parametrize("kind", ["time", "daily", "period"])
def test_non_single_needs_validity(city_config, kind):
    assert "validity_minutes" in errors_of(build(kind=kind, validity_minutes=None))


@pytest.mark.parametrize("minutes", [1000, 10080, 1440 * 8])
def test_daily_must_be_whole_days_below_seven(city_config, minutes):
    assert "validity_minutes" in errors_of(build(kind="daily", validity_minutes=minutes))


def test_period_at_least_seven_days(city_config):
    assert "validity_minutes" in errors_of(build(kind="period", validity_minutes=1440))


@pytest.mark.parametrize("currency", ["pln", "PL", "12A"])
def test_currency_must_be_iso_code(city_config, currency):
    assert "currency" in errors_of(build(currency=currency))


def test_negative_price(city_config):
    assert "price" in errors_of(build(price=Decimal("-1")))


def test_db_rejects_negative_price(city_config):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_ticket("neg", price="-1.00")


def _raw(**overrides):
    fields = {
        "id": "bad",
        "city_id": CITY,
        "zones": ["1"],
        "price": Decimal("1"),
        "prices_as_of": date(2026, 11, 1),
        "source_url": "https://a.invalid/",
    }
    fields.update(overrides)
    return Ticket.objects.create(**fields)


def test_db_rejects_single_with_validity(city_config):
    with pytest.raises(IntegrityError), transaction.atomic():
        _raw(kind="single", validity_minutes=10)


def test_db_rejects_time_without_validity(city_config):
    with pytest.raises(IntegrityError), transaction.atomic():
        _raw(kind="time", validity_minutes=None)


def test_id_is_unique(city_config):
    make_ticket("dup")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_ticket("dup")


# --- admin --------------------------------------------------------------------------------------


@pytest.fixture
def admin_client(client, city_config):
    user = get_user_model().objects.create_superuser("root", "root@example.invalid", "pw")
    client.force_login(user)
    return client


def test_admin_changelist_loads(admin_client):
    make_ticket("listed")
    response = admin_client.get("/admin/tickets/ticket/")
    assert response.status_code == 200
    assert b"listed" in response.content


def test_admin_add_page_loads(admin_client):
    assert admin_client.get("/admin/tickets/ticket/add/").status_code == 200


def test_admin_change_page_loads(admin_client):
    make_ticket("edit-me")
    assert admin_client.get("/admin/tickets/ticket/edit-me/change/").status_code == 200


def test_admin_requires_login(client, city_config):
    response = client.get("/admin/tickets/ticket/")
    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


def test_admin_add_rejects_unknown_zone_then_creates(admin_client):
    data = {
        "id": "new-one",
        "city_id": CITY,
        "name_pl": "Nowy",
        "name_en": "New",
        "description_pl": "",
        "description_en": "",
        "active": "on",
        "kind": "time",
        "validity_minutes": "60",
        "zones": "1,9",
        "price": "6.00",
        "currency": "PLN",
        "prices_as_of": "2026-11-01",
        "source_url": "https://tickets.invalid/prices",
    }
    response = admin_client.post("/admin/tickets/ticket/add/", data)
    assert response.status_code == 200  # form re-rendered with errors
    assert not Ticket.objects.filter(id="new-one").exists()

    data["zones"] = "1"
    response = admin_client.post("/admin/tickets/ticket/add/", data)
    assert response.status_code == 302
    assert Ticket.objects.get(id="new-one").zones == ["1"]
