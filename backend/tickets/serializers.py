from django.utils.translation import gettext as _
from rest_framework import serializers

from core.serializers import TranslatedModelSerializer

from .models import Ticket

# Upper limit of `duration_seconds` in the suggestion request (24 hours).
MAX_DURATION_SECONDS = 86400


class TicketSerializer(TranslatedModelSerializer):
    """Ticket object; `name` and `description` in the request language."""

    zones = serializers.ListField(child=serializers.CharField())
    price = serializers.DecimalField(
        max_digits=8, decimal_places=2, coerce_to_string=True, help_text="Decimal string."
    )
    currency = serializers.CharField(help_text="ISO 4217 code.")
    validity_minutes = serializers.IntegerField(
        allow_null=True, help_text="Null for single-ride tickets."
    )

    class Meta:
        model = Ticket
        fields = [
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
        ]
        read_only_fields = fields


class TicketZoneSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.SerializerMethodField()

    def get_name(self, zone) -> str:
        return zone.names.get()


class TicketCatalogueSerializer(serializers.Serializer):
    zones = TicketZoneSerializer(many=True, help_text="The city's ticket zones in config order.")
    tickets = TicketSerializer(many=True)


class TicketCatalogueQuerySerializer(serializers.Serializer):
    # A choice (not BooleanField): only `true` and `false` are valid, and an omitted value
    # stays omitted (DRF turns a missing BooleanField in query params into False).
    reduced = serializers.ChoiceField(choices=["true", "false"], required=False)


class TicketSuggestRequestSerializer(serializers.Serializer):
    """Needs `city` (cities.registry.City) in the context to validate zone ids."""

    duration_seconds = serializers.IntegerField(min_value=1, max_value=MAX_DURATION_SECONDS)
    transfers = serializers.IntegerField(min_value=0, required=False, default=0)
    zones = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        required=False,
        help_text="Zone ids from the city config. Default: the city's first zone.",
    )
    reduced = serializers.BooleanField(required=False, default=False)

    def validate_zones(self, value: list[str]) -> list[str]:
        city = self.context["city"]
        known = [zone.id for zone in city.ticket_zones]
        unknown = [zone for zone in value if zone not in known]
        if unknown:
            raise serializers.ValidationError(
                _("Unknown zone: %(zones)s.") % {"zones": ", ".join(unknown)}
            )
        return [zone for zone in known if zone in value]

    def validate(self, attrs: dict) -> dict:
        if "zones" not in attrs:
            city = self.context["city"]
            if not city.ticket_zones:
                raise serializers.ValidationError({"zones": [_("This city has no ticket zones.")]})
            attrs["zones"] = [city.ticket_zones[0].id]
        return attrs


class TicketSuggestionSerializer(serializers.Serializer):
    ticket = TicketSerializer(allow_null=True, help_text="Null when no ticket covers the journey.")
    reason = serializers.CharField(help_text="One sentence in the request language.")
