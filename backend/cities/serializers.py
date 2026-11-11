"""Public representation of a city. Internal config fields are never serialised."""

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
