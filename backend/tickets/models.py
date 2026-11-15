"""Ticket catalogue (docs/api.md, "Tickets (#14)").

One row per ticket product and fare (standard and reduced are separate rows). Edited in
the Django admin; ``name`` and ``description`` are translated (see translation.py). Zone ids
refer to ``ticket_zones`` in the city config (cities.registry), so they are validated in
``clean()`` rather than by a foreign key.
"""

from __future__ import annotations

import re

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from cities.registry import get_city

MINUTES_PER_DAY = 24 * 60
# `period` tickets are valid for 7 days or longer; `daily` tickets for whole days below that.
PERIOD_MIN_MINUTES = 7 * MINUTES_PER_DAY

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class Ticket(models.Model):
    class Kind(models.TextChoices):
        SINGLE = "single", _("Single ride")
        TIME = "time", _("Time ticket")
        DAILY = "daily", _("Daily ticket")
        PERIOD = "period", _("Period ticket")

    id = models.SlugField(
        primary_key=True,
        max_length=64,
        verbose_name=_("id"),
        help_text=_("Stable slug, unique across cities, e.g. krakow-time-60-z123."),
    )
    city_id = models.CharField(_("city"), max_length=32, db_index=True)
    name = models.CharField(_("name"), max_length=120)
    description = models.TextField(_("description"), blank=True)
    kind = models.CharField(_("kind"), max_length=8, choices=Kind.choices, db_index=True)
    validity_minutes = models.PositiveIntegerField(
        _("validity (minutes)"),
        null=True,
        blank=True,
        help_text=_("Empty for single-ride tickets. Daily tickets: 1440 × number of days."),
    )
    zones = ArrayField(
        models.CharField(max_length=32),
        verbose_name=_("zones"),
        help_text=_("Zone ids from the city config, comma separated, e.g. 1,2."),
    )
    reduced = models.BooleanField(_("reduced fare"), default=False, db_index=True)
    price = models.DecimalField(_("price"), max_digits=8, decimal_places=2)
    currency = models.CharField(_("currency"), max_length=3, default="PLN")
    prices_as_of = models.DateField(_("price checked on"))
    source_url = models.URLField(_("official price list"), max_length=500)
    active = models.BooleanField(
        _("active"), default=True, db_index=True, help_text=_("Only active tickets are shown.")
    )

    class Meta:
        verbose_name = _("ticket")
        verbose_name_plural = _("tickets")
        ordering = ["city_id", "kind", "validity_minutes", "reduced", "id"]
        indexes = [
            models.Index(
                fields=["city_id", "active", "reduced"], name="tickets_city_active_reduced"
            ),
            GinIndex(fields=["zones"], name="tickets_zones_gin"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name="tickets_price_non_negative"),
            models.CheckConstraint(
                condition=(
                    Q(kind="single", validity_minutes__isnull=True)
                    # NULL > 0 is NULL, which a CHECK accepts: test for NULL explicitly.
                    | (
                        ~Q(kind="single")
                        & Q(validity_minutes__isnull=False, validity_minutes__gt=0)
                    )
                ),
                name="tickets_validity_matches_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.id} ({self.name})"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list] = {}

        city = get_city(self.city_id) if self.city_id else None
        if self.city_id and city is None:
            errors.setdefault("city_id", []).append(_("Unknown city."))

        zones = list(self.zones or [])
        if not zones:
            errors.setdefault("zones", []).append(_("A ticket must cover at least one zone."))
        elif len(set(zones)) != len(zones):
            errors.setdefault("zones", []).append(_("Each zone may be listed only once."))
        elif city is not None:
            known = [zone.id for zone in city.ticket_zones]
            unknown = [zone for zone in zones if zone not in known]
            if unknown:
                errors.setdefault("zones", []).append(
                    _("Unknown zones: %(zones)s. Zones of this city: %(known)s.")
                    % {"zones": ", ".join(unknown), "known": ", ".join(known)}
                )
            else:
                # Keep the config order, so equal zone sets look the same everywhere.
                self.zones = [zone for zone in known if zone in zones]

        minutes = self.validity_minutes
        if self.kind == self.Kind.SINGLE:
            if minutes is not None:
                errors.setdefault("validity_minutes", []).append(
                    _("Single-ride tickets have no validity period; leave it empty.")
                )
        elif self.kind:
            if not minutes:
                errors.setdefault("validity_minutes", []).append(
                    _("This kind of ticket needs a validity period.")
                )
            elif self.kind == self.Kind.DAILY and (
                minutes % MINUTES_PER_DAY or minutes >= PERIOD_MIN_MINUTES
            ):
                errors.setdefault("validity_minutes", []).append(
                    _("Daily tickets last whole days (1440 × days), shorter than 7 days.")
                )
            elif self.kind == self.Kind.PERIOD and minutes < PERIOD_MIN_MINUTES:
                errors.setdefault("validity_minutes", []).append(
                    _("Period tickets last at least 7 days (10080 minutes).")
                )

        if self.currency and not _CURRENCY_RE.match(self.currency):
            errors.setdefault("currency", []).append(
                _("Use a three-letter ISO 4217 code, e.g. PLN.")
            )
        if self.price is not None and self.price < 0:
            errors.setdefault("price", []).append(_("The price cannot be negative."))

        if errors:
            raise ValidationError(errors)
