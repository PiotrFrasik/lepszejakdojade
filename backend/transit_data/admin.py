from django.contrib import admin

from .models import FeedFetch, StopEvent


class ReadOnlyAdmin(admin.ModelAdmin):
    """Collected data is written by the collector only."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(FeedFetch)
class FeedFetchAdmin(ReadOnlyAdmin):
    list_display = (
        "fetched_at",
        "city_id",
        "feed_id",
        "status",
        "feed_timestamp",
        "entity_count",
        "stop_event_count",
        "skipped_count",
        "duration_ms",
    )
    list_filter = ("status", "city_id", "feed_id")
    date_hierarchy = "fetched_at"


@admin.register(StopEvent)
class StopEventAdmin(ReadOnlyAdmin):
    list_display = (
        "service_date",
        "city_id",
        "feed_id",
        "route_id",
        "trip_id",
        "stop_sequence",
        "stop_id",
        "arrival_time",
        "arrival_delay",
        "departure_time",
        "departure_delay",
        "last_seen",
    )
    list_filter = ("city_id", "feed_id", "service_date")
    search_fields = ("trip_id", "stop_id", "route_id", "vehicle_id")
    show_full_result_count = False
