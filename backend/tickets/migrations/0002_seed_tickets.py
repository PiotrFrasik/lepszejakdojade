"""Seed the ticket catalogue of Kraków and Warsaw (#14).

The rows are content, edited later in the Django admin. Re-running the migration
updates rows with these ids; reversing it deletes them.

Kraków: prices copied from the official ZTP price list on 2026-11-15
(https://ztp.krakow.pl/kmk/przewodnik-po-biletach-kmk, "Cennik i rodzaje biletów do kasowania").
Warsaw: the ZTM price page could not be read automatically on 2026-11-15; the prices are the
ZTM tariff as last known and MUST be checked by hand against the official price list.
"""

from datetime import date
from decimal import Decimal

from django.db import migrations

KRAKOW_SOURCE = "https://ztp.krakow.pl/kmk/przewodnik-po-biletach-kmk"
KRAKOW_AS_OF = date(2026, 11, 15)
WARSZAWA_SOURCE = "https://www.wtp.waw.pl/ceny-biletow/"
WARSZAWA_AS_OF = date(2026, 11, 15)

REDUCED_NOTE = {
    "pl": " Bilet ulgowy: tylko dla osób uprawnionych do ulgi.",
    "en": " Reduced fare: only for passengers entitled to a discount.",
}

# (id, kind, validity_minutes, zones, standard price, reduced price,
#  name pl, name en, description pl, description en). The reduced variant gets the id
# suffix "-reduced", "ulgowy" / "Reduced" in the name and REDUCED_NOTE in the description.
KRAKOW = [
    # The official "30-minutowy lub 1-przejazdowy" ticket is valid for 30 minutes OR for one
    # ride of any length. The contract has one kind per ticket, so it is listed twice: as a
    # single ride (here) and as a 30-minute time ticket (below), at the same price.
    (
        "krakow-single-z123", "single", None, ["1", "2", "3"], "6.00", "3.00",
        "Bilet 1-przejazdowy", "Single-ride ticket",
        "Jeden przejazd bez przesiadek, bez względu na czas, w strefach I+II+III "
        "(ten sam bilet co 30-minutowy).",
        "One ride without transfers, of any length, in Zones I+II+III "
        "(the same ticket as the 30-minute one).",
    ),
    (
        "krakow-time-15-z123", "time", 15, ["1", "2", "3"], "4.00", "2.00",
        "Bilet 15-minutowy", "15-minute ticket",
        "Dowolna liczba przejazdów przez 15 minut od skasowania, w strefach I+II+III.",
        "Unlimited rides for 15 minutes from validation in Zones I+II+III.",
    ),
    (
        "krakow-time-30-z123", "time", 30, ["1", "2", "3"], "6.00", "3.00",
        "Bilet 30-minutowy lub 1-przejazdowy", "30-minute or single-ride ticket",
        "Dowolna liczba przejazdów przez 30 minut od skasowania albo jeden przejazd bez "
        "względu na czas, w strefach I+II+III.",
        "Unlimited rides for 30 minutes from validation, or one ride of any length, "
        "in Zones I+II+III.",
    ),
    (
        "krakow-time-60-z123", "time", 60, ["1", "2", "3"], "8.00", "4.00",
        "Bilet 60-minutowy", "60-minute ticket",
        "Dowolna liczba przejazdów przez 60 minut od skasowania, w strefach I+II+III.",
        "Unlimited rides for 60 minutes from validation in Zones I+II+III.",
    ),
    (
        "krakow-time-90-z123", "time", 90, ["1", "2", "3"], "9.00", "4.50",
        "Bilet 90-minutowy", "90-minute ticket",
        "Dowolna liczba przejazdów przez 90 minut od skasowania, w strefach I+II+III.",
        "Unlimited rides for 90 minutes from validation in Zones I+II+III.",
    ),
    (
        "krakow-daily-24h-z1", "daily", 1440, ["1"], "20.00", "10.00",
        "Bilet 24-godzinny, strefa I", "24-hour ticket, Zone I",
        "Dowolna liczba przejazdów przez 24 godziny od skasowania, w strefie I.",
        "Unlimited rides for 24 hours from validation in Zone I.",
    ),
    (
        "krakow-daily-24h-z123", "daily", 1440, ["1", "2", "3"], "25.00", "12.50",
        "Bilet 24-godzinny, strefy I+II+III", "24-hour ticket, Zones I+II+III",
        "Dowolna liczba przejazdów przez 24 godziny od skasowania, w strefach I+II+III.",
        "Unlimited rides for 24 hours from validation in Zones I+II+III.",
    ),
    (
        "krakow-daily-48h-z123", "daily", 2880, ["1", "2", "3"], "40.00", "20.00",
        "Bilet 48-godzinny", "48-hour ticket",
        "Dowolna liczba przejazdów przez 48 godzin od skasowania, w strefach I+II+III.",
        "Unlimited rides for 48 hours from validation in Zones I+II+III.",
    ),
    (
        "krakow-daily-72h-z123", "daily", 4320, ["1", "2", "3"], "55.00", "27.50",
        "Bilet 72-godzinny", "72-hour ticket",
        "Dowolna liczba przejazdów przez 72 godziny od skasowania, w strefach I+II+III.",
        "Unlimited rides for 72 hours from validation in Zones I+II+III.",
    ),
    (
        "krakow-period-7d-z1", "period", 10080, ["1"], "65.00", "32.50",
        "Bilet 7-dniowy, strefa I", "7-day ticket, Zone I",
        "Dowolna liczba przejazdów przez 7 dni od skasowania, w strefie I.",
        "Unlimited rides for 7 days from validation in Zone I.",
    ),
    (
        "krakow-period-7d-z123", "period", 10080, ["1", "2", "3"], "80.00", "40.00",
        "Bilet 7-dniowy, strefy I+II+III", "7-day ticket, Zones I+II+III",
        "Dowolna liczba przejazdów przez 7 dni od skasowania, w strefach I+II+III.",
        "Unlimited rides for 7 days from validation in Zones I+II+III.",
    ),
]

WARSZAWA = [
    (
        "warszawa-time-20-z12", "time", 20, ["1", "2"], "3.40", "1.70",
        "Bilet 20-minutowy", "20-minute ticket",
        "Dowolna liczba przejazdów przez 20 minut od skasowania, w strefach 1 i 2.",
        "Unlimited rides for 20 minutes from validation in Zones 1 and 2.",
    ),
    (
        "warszawa-time-75-z1", "time", 75, ["1"], "4.40", "2.20",
        "Bilet 75-minutowy", "75-minute ticket",
        "Dowolna liczba przejazdów z przesiadkami przez 75 minut od skasowania, w strefie 1.",
        "Unlimited rides with transfers for 75 minutes from validation in Zone 1.",
    ),
    (
        "warszawa-time-90-z12", "time", 90, ["1", "2"], "7.00", "3.50",
        "Bilet 90-minutowy", "90-minute ticket",
        "Dowolna liczba przejazdów z przesiadkami przez 90 minut od skasowania, "
        "w strefach 1 i 2.",
        "Unlimited rides with transfers for 90 minutes from validation in Zones 1 and 2.",
    ),
    (
        "warszawa-daily-24h-z1", "daily", 1440, ["1"], "15.00", "7.50",
        "Bilet 24-godzinny, strefa 1", "24-hour ticket, Zone 1",
        "Dowolna liczba przejazdów przez 24 godziny od skasowania, w strefie 1.",
        "Unlimited rides for 24 hours from validation in Zone 1.",
    ),
    (
        "warszawa-daily-24h-z12", "daily", 1440, ["1", "2"], "26.00", "13.00",
        "Bilet 24-godzinny, strefy 1 i 2", "24-hour ticket, Zones 1 and 2",
        "Dowolna liczba przejazdów przez 24 godziny od skasowania, w strefach 1 i 2.",
        "Unlimited rides for 24 hours from validation in Zones 1 and 2.",
    ),
    (
        "warszawa-daily-72h-z1", "daily", 4320, ["1"], "36.00", "18.00",
        "Bilet 72-godzinny, strefa 1", "72-hour ticket, Zone 1",
        "Dowolna liczba przejazdów przez 72 godziny od skasowania, w strefie 1.",
        "Unlimited rides for 72 hours from validation in Zone 1.",
    ),
    (
        "warszawa-daily-72h-z12", "daily", 4320, ["1", "2"], "57.00", "28.50",
        "Bilet 72-godzinny, strefy 1 i 2", "72-hour ticket, Zones 1 and 2",
        "Dowolna liczba przejazdów przez 72 godziny od skasowania, w strefach 1 i 2.",
        "Unlimited rides for 72 hours from validation in Zones 1 and 2.",
    ),
    (
        "warszawa-period-30d-z1", "period", 43200, ["1"], "110.00", "55.00",
        "Bilet 30-dniowy imienny, strefa 1", "30-day personal ticket, Zone 1",
        "Imienny bilet na dowolną liczbę przejazdów przez 30 kolejnych dni, w strefie 1.",
        "Personal ticket: unlimited rides for 30 consecutive days in Zone 1.",
    ),
]


def _reduced_name_pl(name: str) -> str:
    # "Bilet 24-godzinny, strefa I" -> "Bilet 24-godzinny ulgowy, strefa I"
    head, sep, tail = name.partition(",")
    return f"{head} ulgowy{sep}{tail}"


def _rows(city_id, source_url, as_of, tickets):
    for (
        ticket_id, kind, minutes, zones, price, reduced_price,
        name_pl, name_en, description_pl, description_en,
    ) in tickets:
        common = {
            "city_id": city_id,
            "kind": kind,
            "validity_minutes": minutes,
            "zones": zones,
            "currency": "PLN",
            "prices_as_of": as_of,
            "source_url": source_url,
            "active": True,
        }
        yield ticket_id, {
            **common,
            "reduced": False,
            "price": Decimal(price),
            "name_pl": name_pl,
            "name_en": name_en,
            "description_pl": description_pl,
            "description_en": description_en,
        }
        yield f"{ticket_id}-reduced", {
            **common,
            "reduced": True,
            "price": Decimal(reduced_price),
            "name_pl": _reduced_name_pl(name_pl),
            "name_en": f"Reduced {name_en[0].lower()}{name_en[1:]}",
            "description_pl": description_pl + REDUCED_NOTE["pl"],
            "description_en": description_en + REDUCED_NOTE["en"],
        }


def _all_rows():
    yield from _rows("krakow", KRAKOW_SOURCE, KRAKOW_AS_OF, KRAKOW)
    yield from _rows("warszawa", WARSZAWA_SOURCE, WARSZAWA_AS_OF, WARSZAWA)


def seed(apps, schema_editor):
    Ticket = apps.get_model("tickets", "Ticket")
    for ticket_id, values in _all_rows():
        # The untranslated columns hold the default (Polish) value, as modeltranslation does.
        values = {**values, "name": values["name_pl"], "description": values["description_pl"]}
        Ticket.objects.update_or_create(id=ticket_id, defaults=values)


def unseed(apps, schema_editor):
    Ticket = apps.get_model("tickets", "Ticket")
    Ticket.objects.filter(id__in=[ticket_id for ticket_id, _ in _all_rows()]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
