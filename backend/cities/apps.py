from django.apps import AppConfig


class CitiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cities"

    def ready(self) -> None:
        # Fail fast: a malformed city config stops startup with a clear error.
        from .registry import all_cities

        all_cities()
