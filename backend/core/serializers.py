from modeltranslation.translator import NotRegistered, translator
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
    code = serializers.CharField(help_text="Stable, untranslated error code.")
    message = serializers.CharField(help_text="Message in the request language.")
    details = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField()),
        required=False,
        help_text="Validation errors only: field name -> messages in the request language.",
    )


class ErrorSerializer(serializers.Serializer):
    """Contract error body: {"error": {"code": ..., "message": ..., "details"?: ...}}."""

    error = ErrorDetailSerializer()


def translation_column_names(model) -> set[str]:
    """Per-language columns added by django-modeltranslation, e.g. {"name_pl", "name_en"}."""
    try:
        options = translator.get_options_for_model(model)
    except NotRegistered:
        return set()
    return {field.name for fields in options.all_fields.values() for field in fields}


class TranslatedModelSerializer(serializers.ModelSerializer):
    """ModelSerializer for models with fields registered in django-modeltranslation.

    Convention for translatable database content (ticket names, descriptions, ...):

    1. Register the fields in ``<app>/translation.py``::

           @register(Ticket)
           class TicketTranslationOptions(TranslationOptions):
               fields = ("name", "description")

       Keep translated text fields non-nullable (``blank=True`` is fine), so an
       empty translation falls back to Polish.
    2. Serialize with this class and list the base names only (``"name"``).
       Reading ``name`` returns one string in the request language; an empty
       translation returns the Polish value (MODELTRANSLATION_FALLBACK_LANGUAGES).
    3. Per-language columns (``name_pl``, ``name_en``) are never part of the
       output, even with ``fields = "__all__"``. They are edited in Django admin.

    Meant for reading. Translated content is edited in admin; writing ``name``
    through this serializer only sets the active language's column.
    """

    def get_field_names(self, declared_fields, info):
        names = super().get_field_names(declared_fields, info)
        hidden = translation_column_names(self.Meta.model) - set(declared_fields)
        return [name for name in names if name not in hidden]
