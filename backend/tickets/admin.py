from django import forms
from django.contrib import admin
from django.db import models
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin

from cities.registry import all_cities

from .models import Ticket


def _city_choices() -> list[tuple[str, str]]:
    return [(city.id, city.name) for city in all_cities()]


def _zones_help() -> str:
    lines = [
        f"{city.id}: " + ", ".join(f"{zone.id} ({zone.names.get()})" for zone in city.ticket_zones)
        for city in all_cities()
    ]
    return str(_("Zone ids, comma separated. Zones per city: %(zones)s.")) % {
        "zones": "; ".join(lines)
    }


def _https_url_fields(db_field, **kwargs):
    """Form fields with URLField defaulting to https (Django 6 default, no deprecation warning)."""
    if isinstance(db_field, models.URLField):
        kwargs.setdefault("assume_scheme", "https")
    return db_field.formfield(**kwargs)


class TicketAdminForm(forms.ModelForm):
    # Choices from the city config, read when the form is built.
    city_id = forms.ChoiceField(label=_("city"), choices=_city_choices)

    class Meta:
        model = Ticket
        formfield_callback = _https_url_fields
        fields = [
            "id",
            "city_id",
            "name",
            "description",
            "active",
            "kind",
            "validity_minutes",
            "zones",
            "reduced",
            "price",
            "currency",
            "prices_as_of",
            "source_url",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "zones" in self.fields:
            self.fields["zones"].help_text = _zones_help()


@admin.register(Ticket)
class TicketAdmin(TabbedTranslationAdmin):
    """Ticket catalogue. Zone ids are checked against the city config in Ticket.clean()."""

    form = TicketAdminForm
    list_display = (
        "id",
        "name",
        "city_id",
        "kind",
        "validity_minutes",
        "zone_list",
        "reduced",
        "price",
        "currency",
        "prices_as_of",
        "active",
    )
    list_filter = ("city_id", "kind", "reduced", "active")
    list_editable = ("active",)
    search_fields = ("id", "name_pl", "name_en")
    ordering = ("city_id", "kind", "validity_minutes", "reduced", "id")
    fieldsets = (
        (None, {"fields": ("id", "city_id", "name", "description", "active")}),
        (_("Validity"), {"fields": ("kind", "validity_minutes", "zones", "reduced")}),
        (_("Price"), {"fields": ("price", "currency", "prices_as_of", "source_url")}),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # The admin builds its own form fields; keep the https default there too.
        if isinstance(db_field, models.URLField):
            kwargs.setdefault("assume_scheme", "https")
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        # The id is a stable public identifier: set once, never renamed.
        return ("id",) if obj is not None else ()

    @admin.display(description=_("zones"))
    def zone_list(self, obj: Ticket) -> str:
        return ", ".join(obj.zones)
