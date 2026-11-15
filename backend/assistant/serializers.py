"""Request and response of ``POST /api/v1/assistant/chat/`` (docs/api.md, "Assistant (#18)").

The response is built as a dict by ``assistant.chat``; the response serializers describe it
for the OpenAPI schema.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import PolymorphicProxySerializer
from rest_framework import serializers

from cities.registry import get_city
from journeys.serializers import (
    ComparisonSerializer,
    ItinerarySerializer,
    PlaceSerializer,
    _KeywordFieldsMixin,
)
from timetable.serializers import (
    DIRECTIONS,
    LineSummarySerializer,
    StopRefSerializer,
    StopSearchResultSerializer,
)

ROLES = ("user", "assistant")
MAX_MESSAGES = 20
MAX_TEXT_LENGTH = 1000

# ------------------------------------------------------------------------ request


class ChatMessageInputSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=ROLES)
    text = serializers.CharField(
        max_length=MAX_TEXT_LENGTH, help_text="1-1000 characters after trimming."
    )


class ChatRequestSerializer(serializers.Serializer):
    city = serializers.CharField(max_length=50, help_text="City id from `GET /cities/`.")
    messages = ChatMessageInputSerializer(
        many=True,
        min_length=1,
        max_length=MAX_MESSAGES,
        help_text="1-20 messages, oldest first; the last one must be from the user.",
    )

    def validate_city(self, value: str) -> str:
        if get_city(value) is None:
            raise serializers.ValidationError(_("Unknown city."))
        return value

    def validate_messages(self, value: list[dict]) -> list[dict]:
        if value and value[-1]["role"] != "user":
            raise serializers.ValidationError(_("The last message must be from the user."))
        return value


# ----------------------------------------------------------------------- response


class ChatMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["assistant"])
    text = serializers.CharField(help_text="Plain text (no Markdown, no HTML).")


class JourneyCardSerializer(_KeywordFieldsMixin, serializers.Serializer):
    type = serializers.ChoiceField(choices=["journey"])
    from_ = PlaceSerializer()
    to = PlaceSerializer()
    itinerary = ItinerarySerializer()
    comparison = ComparisonSerializer()


class CardDepartureSerializer(serializers.Serializer):
    line = LineSummarySerializer()
    stop_id = serializers.CharField(
        help_text="Platform the departure leaves from (timetable stop id of this line)."
    )
    direction = serializers.ChoiceField(choices=DIRECTIONS)
    headsign = serializers.CharField(allow_blank=True)
    time = serializers.CharField(help_text="Local clock time HH:MM.")
    next_day = serializers.BooleanField()
    date = serializers.DateField(help_text="Service date.")
    trip_id = serializers.CharField()


class DeparturesCardSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["departures"])
    stop = StopRefSerializer(help_text="The stop group; `stop_id` is its representative platform.")
    departures = CardDepartureSerializer(many=True, help_text="Up to 10, ascending.")


class StopsCardSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["stops"])
    stops = StopSearchResultSerializer(many=True, help_text="Up to 5.")


CARD_SERIALIZER = PolymorphicProxySerializer(
    component_name="AssistantCard",
    serializers={
        "journey": JourneyCardSerializer,
        "departures": DeparturesCardSerializer,
        "stops": StopsCardSerializer,
    },
    resource_type_field_name="type",
    many=True,
)


class ChatResponseSerializer(serializers.Serializer):
    message = ChatMessageSerializer()
    cards = CARD_SERIALIZER
