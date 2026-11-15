"""Ticket catalogue queries and the ticket suggestion (docs/api.md, "Tickets (#14)")."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from django.utils.translation import gettext as _

from cities.registry import City

from .models import Ticket

# Catalogue order of `kind` (docs/api.md).
KIND_ORDER = {
    Ticket.Kind.SINGLE: 0,
    Ticket.Kind.TIME: 1,
    Ticket.Kind.DAILY: 2,
    Ticket.Kind.PERIOD: 3,
}
# Only these kinds are suggested for one journey.
SUGGESTED_KINDS = (Ticket.Kind.SINGLE, Ticket.Kind.TIME)


def _catalogue_key(ticket: Ticket) -> tuple:
    return (
        KIND_ORDER.get(ticket.kind, len(KIND_ORDER)),
        # `single` has no validity; it is the only kind in its group anyway.
        ticket.validity_minutes or 0,
        len(ticket.zones),
        ticket.reduced,
        ticket.id,
    )


def catalogue(city: City, reduced: bool | None = None) -> list[Ticket]:
    """Active tickets of a city in catalogue order; ``reduced=None`` returns both fares."""
    tickets = Ticket.objects.filter(city_id=city.id, active=True)
    if reduced is not None:
        tickets = tickets.filter(reduced=reduced)
    return sorted(tickets, key=_catalogue_key)


@dataclass(frozen=True)
class Suggestion:
    ticket: Ticket | None
    reason: str


def _suggestion_key(ticket: Ticket) -> tuple:
    # Lowest price; ties: shorter validity (a single ride counts as the shortest), fewer zones, id.
    return (ticket.price, ticket.validity_minutes or 0, len(ticket.zones), ticket.id)


def _covers(ticket: Ticket, duration_seconds: int, transfers: int) -> bool:
    if ticket.kind == Ticket.Kind.SINGLE:
        return transfers == 0
    return ticket.validity_minutes is not None and ticket.validity_minutes * 60 >= duration_seconds


def pick_ticket(
    candidates: Iterable[Ticket], duration_seconds: int, transfers: int
) -> Ticket | None:
    matching = [t for t in candidates if _covers(t, duration_seconds, transfers)]
    return min(matching, key=_suggestion_key) if matching else None


def zone_names(city: City, zone_ids: Sequence[str]) -> str:
    """Names of the given zones in the active language, in config order."""
    return ", ".join(zone.names.get() for zone in city.ticket_zones if zone.id in zone_ids)


def suggest(
    city: City, duration_seconds: int, transfers: int, zones: Sequence[str], reduced: bool
) -> Suggestion:
    """The cheapest single or time ticket that covers the whole journey."""
    candidates = Ticket.objects.filter(
        city_id=city.id,
        active=True,
        reduced=reduced,
        kind__in=SUGGESTED_KINDS,
        zones__contains=list(zones),
    )
    ticket = pick_ticket(candidates, duration_seconds, transfers)
    params = {
        "minutes": math.ceil(duration_seconds / 60),
        "zones": zone_names(city, zones),
    }
    if ticket is None:
        reason = (
            _("No single or time ticket covers this %(minutes)d-minute journey in %(zones)s.")
            % params
        )
    elif ticket.kind == Ticket.Kind.SINGLE:
        reason = _("%(ticket)s covers this journey without transfers in %(zones)s.") % {
            **params,
            "ticket": ticket.name,
        }
    else:
        reason = _("%(ticket)s covers this %(minutes)d-minute journey in %(zones)s.") % {
            **params,
            "ticket": ticket.name,
        }
    return Suggestion(ticket=ticket, reason=reason)
