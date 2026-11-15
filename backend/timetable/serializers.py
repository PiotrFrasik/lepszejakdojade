"""Query parameters and responses of the timetable API (docs/api.md, "Timetable (#10)")."""

from datetime import date, timedelta

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from cities.registry import VEHICLE_TYPES

from .calendar import DAY_TYPES
from .variants import DEPOT, MAIN, OTHER, SHORT_TURN

VARIANT_KINDS = (MAIN, SHORT_TURN, DEPOT, OTHER)
MARKERS = ("low_floor", "short_turn", "variant")
LINE_NOTICE_KINDS = ("detour", "timetable_change")
DIRECTIONS = (0, 1)

# Dates near date.min or date.max would overflow the look-back and look-ahead windows.
_FIRST_SUPPORTED_DATE = date.min + timedelta(days=366)
_LAST_SUPPORTED_DATE = date.max - timedelta(days=366)


# ------------------------------------------------------------------- query params


class _DateParam(serializers.DateField):
    def __init__(self, **kwargs):
        super().__init__(input_formats=["%Y-%m-%d"], required=False, **kwargs)

    def to_internal_value(self, value):
        parsed = super().to_internal_value(value)
        if not _FIRST_SUPPORTED_DATE <= parsed <= _LAST_SUPPORTED_DATE:
            raise serializers.ValidationError(_("Date is out of range."))
        return parsed


class LinesQuerySerializer(serializers.Serializer):
    vehicle_type = serializers.ChoiceField(choices=VEHICLE_TYPES, required=False)


class DirectionDateQuerySerializer(serializers.Serializer):
    # Omitted: the lowest direction the line has (resolved in services.direction_context).
    direction = serializers.ChoiceField(choices=DIRECTIONS, required=False)
    date = _DateParam()


class DateQuerySerializer(serializers.Serializer):
    date = _DateParam()


# ---------------------------------------------------------------------- responses


class LineSummarySerializer(serializers.Serializer):
    id = serializers.CharField(help_text="Line id `{feed_id}:{gtfs_route_id}`; opaque.")
    short_name = serializers.CharField()
    vehicle_type = serializers.ChoiceField(choices=VEHICLE_TYPES)
    group = serializers.CharField(help_text="One of the city's `line_groups[].id`.")
    colour = serializers.RegexField(r"^#[0-9a-f]{6}$")
    text_colour = serializers.RegexField(r"^#[0-9a-f]{6}$")


class LineNoticeSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=LINE_NOTICE_KINDS)
    text = serializers.CharField()


class LineListItemSerializer(LineSummarySerializer):
    long_name = serializers.CharField(allow_blank=True)
    notice = LineNoticeSerializer(
        allow_null=True, help_text="Always null until live alerts exist (#20)."
    )


class DirectionSerializer(serializers.Serializer):
    direction = serializers.ChoiceField(choices=DIRECTIONS)
    headsign = serializers.CharField(allow_blank=True)


class RouteStopSerializer(serializers.Serializer):
    stop_id = serializers.CharField()
    name = serializers.CharField(allow_blank=True)
    code = serializers.CharField(allow_null=True)
    lat = serializers.FloatField(allow_null=True)
    lon = serializers.FloatField(allow_null=True)
    wheelchair_boarding = serializers.BooleanField(allow_null=True)
    variant_only = serializers.BooleanField()
    transfers = LineSummarySerializer(many=True)


class RouteVariantSerializer(serializers.Serializer):
    id = serializers.CharField()
    kind = serializers.ChoiceField(choices=VARIANT_KINDS)
    headsign = serializers.CharField(allow_blank=True)
    trip_count = serializers.IntegerField()
    stop_ids = serializers.ListField(child=serializers.CharField())


class LineStringSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["LineString"])
    coordinates = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
        help_text="[lon, lat] pairs.",
    )


class LineRouteSerializer(serializers.Serializer):
    line = LineSummarySerializer()
    direction = serializers.ChoiceField(choices=DIRECTIONS)
    date = serializers.DateField()
    directions = DirectionSerializer(many=True)
    stops = RouteStopSerializer(many=True)
    variants = RouteVariantSerializer(many=True)
    shape = LineStringSerializer()


class StopRefSerializer(serializers.Serializer):
    stop_id = serializers.CharField()
    name = serializers.CharField(allow_blank=True)


class TimetableStopSerializer(StopRefSerializer):
    code = serializers.CharField(allow_null=True)


class DepartureSerializer(serializers.Serializer):
    minute = serializers.IntegerField(min_value=0, max_value=59)
    time = serializers.CharField(help_text="Local clock time HH:MM.")
    next_day = serializers.BooleanField()
    trip_id = serializers.CharField()
    headsign = serializers.CharField(allow_blank=True)
    markers = serializers.ListField(child=serializers.ChoiceField(choices=MARKERS))
    variant = serializers.CharField(allow_null=True)


class TimetableHourSerializer(serializers.Serializer):
    hour = serializers.IntegerField(min_value=0, max_value=23)
    departures = DepartureSerializer(many=True)


class TimetableColumnSerializer(serializers.Serializer):
    day_type = serializers.ChoiceField(choices=DAY_TYPES)
    date = serializers.DateField()
    hours = TimetableHourSerializer(many=True)


class TimetableVariantSerializer(serializers.Serializer):
    id = serializers.CharField()
    kind = serializers.ChoiceField(choices=VARIANT_KINDS)
    headsign = serializers.CharField(allow_blank=True)


class StopTimetableSerializer(serializers.Serializer):
    line = LineSummarySerializer()
    stop = TimetableStopSerializer()
    direction = serializers.ChoiceField(choices=DIRECTIONS)
    headsign = serializers.CharField(allow_blank=True)
    date = serializers.DateField()
    day_type = serializers.ChoiceField(choices=DAY_TYPES)
    previous_stop = StopRefSerializer(allow_null=True)
    next_stop = StopRefSerializer(allow_null=True)
    columns = TimetableColumnSerializer(many=True)
    variants = TimetableVariantSerializer(many=True)


class TripStopSerializer(serializers.Serializer):
    stop_id = serializers.CharField()
    name = serializers.CharField(allow_blank=True)
    arrival = serializers.CharField(allow_null=True, help_text="ISO 8601 with offset.")
    departure = serializers.CharField(allow_null=True, help_text="ISO 8601 with offset.")


class TripSerializer(serializers.Serializer):
    trip_id = serializers.CharField()
    date = serializers.DateField()
    line = LineSummarySerializer()
    direction = serializers.ChoiceField(choices=DIRECTIONS)
    headsign = serializers.CharField(allow_blank=True)
    wheelchair_accessible = serializers.BooleanField(allow_null=True)
    stops = TripStopSerializer(many=True)
