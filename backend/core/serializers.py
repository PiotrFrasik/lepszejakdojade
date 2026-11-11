from rest_framework import serializers

# Values of `status` and `checks.<name>` in the health response.
HEALTH_STATUS_CHOICES = ["ok", "error"]


class HealthChecksSerializer(serializers.Serializer):
    database = serializers.ChoiceField(choices=HEALTH_STATUS_CHOICES)
    redis = serializers.ChoiceField(choices=HEALTH_STATUS_CHOICES)


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=HEALTH_STATUS_CHOICES)
    checks = HealthChecksSerializer()
    version = serializers.CharField()


class ErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()


class ErrorSerializer(serializers.Serializer):
    """Contract error body: {"error": {"code": ..., "message": ...}}."""

    error = ErrorDetailSerializer()
