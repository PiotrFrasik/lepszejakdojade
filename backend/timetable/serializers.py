"""Query parameters and responses of the timetable API (docs/api.md, "Timetable (#10)")."""

from datetime import date, timedelta

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from cities.registry import VEHICLE_TYPES

from .calendar import DAY_TYPES
from .departures import DEFAULT_LIMIT as DEFAULT_DEPARTURES_LIMIT
from .departures import MAX_LIMIT as MAX_DEPARTURES_LIMIT
from .departures import STATUSES as DEPARTURE_STATUSES
from .stops import MIN_QUERY_LENGTH
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


class StopSearchQuerySerializer(serializers.Serializer):
    # CharField trims whitespace before the length check.
    q = serializers.CharField(
        min_length=MIN_QUERY_LENGTH,
        error_messages={
            # Literal "2" (not "{min_length}"): the blank error is raised without kwargs.
            "min_length": _("Enter at least 2 characters."),
            "blank": _("Enter at least 2 characters."),
        },
    )


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


class StopSearchResultSerializer(serializers.Serializer):
    stop_id = serializers.CharField(
        help_text="Representative platform (the one closest to the group centroid); opaque."
    )
    name = serializers.CharField()
    lat = serializers.FloatField(help_text="Group centroid.")
    lon = serializers.FloatField(help_text="Group centroid.")
    vehicle_types = serializers.ListField(
        child=serializers.ChoiceField(choices=VEHICLE_TYPES),
        help_text="Vehicle types serving the group.",
    )
    stop_ids = serializers.ListField(
        child=serializers.CharField(), help_text="All platforms of the group."
    )


# ------------------------------------------------------------------ stop departures


class StopDeparturesQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(
        min_value=1, max_value=MAX_DEPARTURES_LIMIT, default=DEFAULT_DEPARTURES_LIMIT
    )


class DeparturesStopSerializer(serializers.Serializer):
    id = serializers.CharField(help_text="The requested stop id.")
    name = serializers.CharField()
    stop_ids = serializers.ListField(
        child=serializers.CharField(), help_text="All platforms of the stop group."
    )


class StopDepartureSerializer(serializers.Serializer):
    line = LineSummarySerializer()
    trip_id = serializers.CharField()
    headsign = serializers.CharField(allow_blank=True)
    platform_id = serializers.CharField()
    platform_code = serializers.CharField(allow_null=True)
    scheduled = serializers.CharField(help_text="ISO 8601 with offset.")
    expected = serializers.CharField(
        allow_null=True, help_text="ISO 8601 with offset; null unless status is live."
    )
    delay_seconds = serializers.IntegerField(
        allow_null=True, help_text="May be negative (early) or 0; null unless status is live."
    )
    status = serializers.ChoiceField(choices=DEPARTURE_STATUSES)


class StopDeparturesSerializer(serializers.Serializer):
    stop = DeparturesStopSerializer()
    generated_at = serializers.CharField(help_text="ISO 8601 with offset, city time zone.")
    realtime_available = serializers.BooleanField()
    departures = StopDepartureSerializer(many=True)
