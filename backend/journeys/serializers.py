"""Request and response of the journey search (docs/api.md, "POST .../journeys/search/").

``from`` is a Python keyword, so such fields are declared with a trailing underscore
(``from_``) and renamed by ``_KeywordFieldsMixin``.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from timetable.serializers import LineStringSerializer, LineSummarySerializer

TIME_MODES = ("depart", "arrive")
LEG_MODES = ("walk", "tram", "bus", "metro", "rail")


class _KeywordFieldsMixin:
    """Expose fields declared as ``name_`` under ``name`` (for keywords such as ``from``)."""

    def get_fields(self):
        return {
            (name[:-1] if name.endswith("_") else name): field
            for name, field in super().get_fields().items()
        }


# ------------------------------------------------------------------------ request


class _NaiveAwareDateTimeField(serializers.DateTimeField):
    """Keeps a time without offset naive; the view interprets it in the city time zone."""

    def enforce_timezone(self, value):
        return value


class PlaceInputSerializer(serializers.Serializer):
    stop_id = serializers.CharField(required=False, max_length=255)
    lat = serializers.FloatField(required=False, min_value=-90, max_value=90)
    lon = serializers.FloatField(required=False, min_value=-180, max_value=180)
    name = serializers.CharField(required=False, allow_blank=True, max_length=200)

    def validate(self, attrs):
        has_stop = "stop_id" in attrs
        has_point = "lat" in attrs and "lon" in attrs
        if has_stop == has_point or (not has_point and ("lat" in attrs or "lon" in attrs)):
            raise serializers.ValidationError(_("Give either a stop_id or both lat and lon."))
        return attrs


class PreferencesSerializer(serializers.Serializer):
    fewer_transfers = serializers.BooleanField(default=False)
    less_walking = serializers.BooleanField(default=False)
    wheelchair = serializers.BooleanField(default=False)


class JourneySearchRequestSerializer(_KeywordFieldsMixin, serializers.Serializer):
    """Journey search request."""

    from_ = PlaceInputSerializer(help_text="Start: `stop_id` or `lat` + `lon`.")
    to = PlaceInputSerializer(help_text="Destination: `stop_id` or `lat` + `lon`.")
    time = _NaiveAwareDateTimeField(
        required=False,
        help_text="ISO 8601; without an offset it is local time of the city. Default: now.",
    )
    time_mode = serializers.ChoiceField(choices=TIME_MODES, default="depart")
    preferences = PreferencesSerializer(required=False)


# ----------------------------------------------------------------------- response


class PlaceSerializer(serializers.Serializer):
    name = serializers.CharField(allow_null=True)
    lat = serializers.FloatField()
    lon = serializers.FloatField()


class LegPlaceSerializer(serializers.Serializer):
    name = serializers.CharField(allow_null=True)
    stop_id = serializers.CharField(allow_null=True)
    lat = serializers.FloatField()
    lon = serializers.FloatField()


class IntermediateStopSerializer(serializers.Serializer):
    name = serializers.CharField(allow_null=True)
    stop_id = serializers.CharField(allow_null=True)


class LegSerializer(_KeywordFieldsMixin, serializers.Serializer):
    """One leg of an itinerary: a walk or a ride on one transit trip."""

    mode = serializers.ChoiceField(choices=LEG_MODES)
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    duration = serializers.IntegerField(help_text="Seconds.")
    distance = serializers.IntegerField(help_text="Metres.")
    from_ = LegPlaceSerializer()
    to = LegPlaceSerializer()
    line = LineSummarySerializer(allow_null=True, help_text="Null for walking legs.")
    headsign = serializers.CharField(allow_null=True)
    trip_id = serializers.CharField(allow_null=True)
    intermediate_stops = IntermediateStopSerializer(many=True)
    geometry = LineStringSerializer()


class ItinerarySerializer(serializers.Serializer):
    id = serializers.CharField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    duration = serializers.IntegerField(help_text="Seconds.")
    transfers = serializers.IntegerField()
    walk_distance = serializers.IntegerField(help_text="Metres.")
    walk_duration = serializers.IntegerField(help_text="Seconds.")
    legs = LegSerializer(many=True)


class ComparisonItemSerializer(serializers.Serializer):
    duration = serializers.IntegerField(help_text="Seconds.")
    distance = serializers.IntegerField(help_text="Metres.")


class ComparisonSerializer(serializers.Serializer):
    walk = ComparisonItemSerializer(allow_null=True)
    bike = ComparisonItemSerializer(allow_null=True)


class JourneySearchResponseSerializer(_KeywordFieldsMixin, serializers.Serializer):
    """Journey search result with walk and bike comparison."""

    from_ = PlaceSerializer()
    to = PlaceSerializer()
    itineraries = ItinerarySerializer(many=True)
    comparison = ComparisonSerializer()
