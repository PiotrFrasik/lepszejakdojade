"""Fictional cities "tkville" (zones 1, 2, 3) and "otherville" (zone 1) with their own tickets."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from django.core.cache import cache
from rest_framework.test import APIClient

from cities import registry
from tickets.models import Ticket

CITY = "tkville"
OTHER = "otherville"
NO_ZONES = "emptyville"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def city_config(tmp_path, settings):
    real = Path(settings.CITY_CONFIG_DIR)
    config_dir = tmp_path / "cities"
    config_dir.mkdir()
    base = yaml.safe_load((real / "krakow.yaml").read_text(encoding="utf-8"))
    zones = {
        CITY: [
            {"id": "1", "names": {"pl": "Pierscien I", "en": "Ring I"}},
            {"id": "2", "names": {"pl": "Pierscien II", "en": "Ring II"}},
            {"id": "3", "names": {"pl": "Pierscien III", "en": "Ring III"}},
        ],
        OTHER: [{"id": "1", "names": {"pl": "Centrum", "en": "Centre"}}],
        NO_ZONES: [],
    }
    for city_id, city_zones in zones.items():
        data = dict(base)
        data["id"] = city_id
        data["names"] = {"pl": city_id, "en": city_id}
        data["ticket_zones"] = city_zones
        (config_dir / f"{city_id}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    settings.CITY_CONFIG_DIR = config_dir
    registry.clear_cache()
    yield
    registry.clear_cache()


def make_ticket(
    id,
    *,
    city=CITY,
    kind="time",
    minutes=60,
    zones=("1",),
    reduced=False,
    price="6.00",
    active=True,
    name_pl=None,
    name_en=None,
    description_pl="Opis",
    description_en="Description",
    currency="PLN",
):
    if kind == "single":
        minutes = None
    return Ticket.objects.create(
        id=id,
        city_id=city,
        kind=kind,
        validity_minutes=minutes,
        zones=list(zones),
        reduced=reduced,
        price=Decimal(price),
        currency=currency,
        active=active,
        name_pl=name_pl if name_pl is not None else f"Bilet {id}",
        name_en=name_en if name_en is not None else f"Ticket {id}",
        description_pl=description_pl,
        description_en=description_en,
        prices_as_of=date(2026, 11, 1),
        source_url="https://tickets.invalid/prices",
    )


class Api:
    def __init__(self, city=CITY):
        self.client = APIClient()
        self.city = city

    def url(self, suffix="", city=None):
        return f"/api/v1/cities/{city or self.city}/tickets/{suffix}"

    def catalogue(self, lang=None, city=None, **params):
        extra = {"headers": {"Accept-Language": lang}} if lang else {}
        return self.client.get(self.url(city=city), params, **extra)

    def suggest(self, body, lang=None, city=None):
        extra = {"headers": {"Accept-Language": lang}} if lang else {}
        return self.client.post(self.url("suggest/", city=city), body, format="json", **extra)


@pytest.fixture
def api(city_config):
    return Api()
