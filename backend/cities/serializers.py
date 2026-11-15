"""Public representation of a city. Internal config fields are never serialised."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .registry import VEHICLE_TYPES


class MapCenterSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lon = serializers.FloatField()


class MapSerializer(serializers.Serializer):
    center = MapCenterSerializer(source="*")
    zoom = serializers.IntegerField()


class LineGroupSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.SerializerMethodField()
    colour = serializers.RegexField(r"^#[0-9a-f]{6}$")

    def get_name(self, obj) -> str:
        return obj.names.get()


class RealtimeSerializer(serializers.Serializer):
    departures = serializers.BooleanField()
    vehicles = serializers.BooleanField()


class CitySerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    map = MapSerializer()


class CityDetailSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    timezone = serializers.CharField()
    map = MapSerializer()
    vehicle_types = serializers.ListField(child=serializers.ChoiceField(choices=VEHICLE_TYPES))
    line_groups = LineGroupSerializer(many=True)
    realtime = RealtimeSerializer()


# ------------------------------------------------------------------ data sources


def parse_http_date(value: str | None) -> datetime | None:
    """An HTTP-date (``Last-Modified``) as an aware datetime, or None if empty or unparsable."""
    if not value or not value.strip():
        return None
    try:
        parsed = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:  # "-0000": UTC without source zone information (RFC 5322)
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


class DataSourceSerializer(serializers.Serializer):
    """One attribution from city config. Proper names, licences and URLs are not translated."""

    name = serializers.CharField()
    url = serializers.URLField()
    licence = serializers.CharField(allow_null=True)
    licence_url = serializers.URLField(allow_null=True)
    description = serializers.CharField(allow_null=True)


class FeedSourceSerializer(serializers.Serializer):
    """When one active static GTFS feed version was created and retrieved.

    Source URLs, hashes, etags, sizes and other internal fields are never exposed.
    """

    feed_id = serializers.CharField()
    publisher_name = serializers.SerializerMethodField()
    last_modified = serializers.SerializerMethodField()
    downloaded_at = serializers.DateTimeField()
    imported_at = serializers.DateTimeField(allow_null=True)
    service_start_date = serializers.DateField(allow_null=True)
    service_end_date = serializers.DateField(allow_null=True)

    def get_publisher_name(self, obj) -> str | None:
        return obj.publisher_name.strip() or None

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_last_modified(self, obj) -> str | None:
        parsed = parse_http_date(obj.last_modified)
        if parsed is None:
            return None
        # Rendered in the current time zone, which CityDataSourcesSerializer sets to the city's.
        return serializers.DateTimeField().to_representation(parsed)


class CityDataSourcesSerializer(serializers.Serializer):
    """Attributions and active feed versions of one city.

    Expects ``context["feeds"]``: active FeedVersion rows (ordered by feed id) grouped by
    city id. Timestamps are rendered in the city time zone.
    """

    id = serializers.CharField()
    name = serializers.CharField()
    sources = DataSourceSerializer(source="attributions", many=True)
    feeds = serializers.SerializerMethodField()

    @extend_schema_field(FeedSourceSerializer(many=True))
    def get_feeds(self, obj) -> list:
        rows = self.context.get("feeds", {}).get(obj.id, [])
        return FeedSourceSerializer(rows, many=True).data

    def to_representation(self, instance):
        with timezone.override(instance.zoneinfo):
            return super().to_representation(instance)


class DataSourcesSerializer(serializers.Serializer):
    cities = CityDataSourcesSerializer(many=True)
