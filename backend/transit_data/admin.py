import json

from django.contrib import admin
from django.core.paginator import Paginator
from django.utils.functional import cached_property
from django.utils.html import format_html

from cities.registry import all_cities

from .models import (
    Agency,
    Calendar,
    CalendarDate,
    FeedFetch,
    FeedVersion,
    Frequency,
    Route,
    Shape,
    Stop,
    StopEvent,
    StopTime,
    Trip,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Collected data is written by the collector only."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class LimitedCountPaginator(Paginator):
    """Counts at most COUNT_LIMIT rows: an exact count of millions of stop times on
    every admin page load is too slow."""

    COUNT_LIMIT = 10_000

    @cached_property
    def count(self):
        return self.object_list[: self.COUNT_LIMIT].count()


class StaticReadOnlyAdmin(ReadOnlyAdmin):
    """Static GTFS rows are written and deleted by the importer only (raw SQL purge)."""

    paginator = LimitedCountPaginator
    show_full_result_count = False

    def has_delete_permission(self, request, obj=None):
        return False


class CityFilter(admin.SimpleListFilter):
    """City from city config (no DISTINCT over large tables)."""

    title = "city"
    parameter_name = "city"
    field_path = "feed_version__city_id"

    def lookups(self, request, model_admin):
        return [(city.id, city.id) for city in all_cities()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{self.field_path: self.value()})
        return queryset


class FeedVersionFilter(admin.SimpleListFilter):
    title = "feed version"
    parameter_name = "feed_version"

    def lookups(self, request, model_admin):
        versions = FeedVersion.objects.exclude(status=FeedVersion.Status.FAILED).order_by(
            "city_id", "feed_id", "-pk"
        )
        return [(str(v.pk), str(v)) for v in versions]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(feed_version_id=self.value())
        return queryset


GTFS_FILTERS = (CityFilter, FeedVersionFilter)


@admin.register(FeedVersion)
class FeedVersionAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "city_id",
        "feed_id",
        "status",
        "data_error",
        "downloaded_at",
        "checked_at",
        "service_start_date",
        "service_end_date",
        "size_bytes",
        "duration_ms",
    )
    list_filter = ("status", "city_id", "feed_id")
    date_hierarchy = "downloaded_at"
    exclude = ("report",)
    readonly_fields = ("report_pretty",)

    def has_delete_permission(self, request, obj=None):
        # Deleting through the ORM would cascade over millions of rows in memory;
        # old versions are purged by the importer.
        return False

    @admin.display(description="import report")
    def report_pretty(self, obj):
        return format_html("<pre>{}</pre>", json.dumps(obj.report, indent=2, ensure_ascii=False))


@admin.register(Agency)
class AgencyAdmin(StaticReadOnlyAdmin):
    list_display = ("name", "gtfs_id", "feed_version", "url")
    list_filter = GTFS_FILTERS
    list_select_related = ("feed_version",)


@admin.register(Stop)
class StopAdmin(StaticReadOnlyAdmin):
    list_display = (
        "name",
        "gtfs_id",
        "code",
        "location_type",
        "platform_code",
        "wheelchair_boarding",
        "feed_version",
    )
    list_filter = (*GTFS_FILTERS, "location_type")
    list_select_related = ("feed_version",)
    search_fields = ("name", "=gtfs_id", "=code")
    raw_id_fields = ("parent_station",)


@admin.register(Route)
class RouteAdmin(StaticReadOnlyAdmin):
    list_display = ("short_name", "long_name", "gtfs_id", "route_type", "color", "feed_version")
    list_filter = (*GTFS_FILTERS, "route_type")
    list_select_related = ("feed_version",)
    search_fields = ("=short_name", "long_name", "=gtfs_id")


@admin.register(Calendar)
class CalendarAdmin(StaticReadOnlyAdmin):
    list_display = (
        "service_id",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "start_date",
        "end_date",
        "feed_version",
    )
    list_filter = GTFS_FILTERS
    list_select_related = ("feed_version",)
    search_fields = ("=service_id",)


@admin.register(CalendarDate)
class CalendarDateAdmin(StaticReadOnlyAdmin):
    list_display = ("service_id", "date", "exception_type", "feed_version")
    list_filter = (*GTFS_FILTERS, "exception_type")
    list_select_related = ("feed_version",)
    search_fields = ("=service_id",)


@admin.register(Shape)
class ShapeAdmin(StaticReadOnlyAdmin):
    list_display = ("gtfs_id", "feed_version")
    list_filter = GTFS_FILTERS
    list_select_related = ("feed_version",)
    search_fields = ("=gtfs_id",)


@admin.register(Trip)
class TripAdmin(StaticReadOnlyAdmin):
    list_display = ("gtfs_id", "route", "service_id", "headsign", "direction_id", "feed_version")
    list_filter = GTFS_FILTERS
    list_select_related = ("feed_version", "route")
    search_fields = ("=gtfs_id", "=service_id", "=block_id")
    raw_id_fields = ("route", "shape")


@admin.register(StopTime)
class StopTimeAdmin(StaticReadOnlyAdmin):
    list_display = (
        "trip",
        "stop_sequence",
        "stop",
        "arrival_time",
        "departure_time",
        "pickup_type",
        "drop_off_type",
    )
    list_filter = GTFS_FILTERS
    list_select_related = ("trip", "stop")
    search_fields = ("=trip__gtfs_id",)
    raw_id_fields = ("trip", "stop")


@admin.register(Frequency)
class FrequencyAdmin(StaticReadOnlyAdmin):
    list_display = ("trip", "start_time", "end_time", "headway_secs", "exact_times")
    list_filter = GTFS_FILTERS
    list_select_related = ("trip",)
    raw_id_fields = ("trip",)


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
