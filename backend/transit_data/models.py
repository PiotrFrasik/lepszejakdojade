"""Transit data: raw realtime data (StopEvent, FeedFetch) and static GTFS (FeedVersion etc.).

Realtime: GTFS ids (trip, route, stop) are stored as plain strings: they refer to the static
GTFS feed of the same city, but there are no foreign keys, so realtime data can be
collected before (and independently of) the static import.

Retention: raw stop events and fetch log rows are kept for
``RAW_EVENT_RETENTION_DAYS`` days. Aggregated statistics (built nightly from the raw
events) are kept indefinitely. The deletion job is part of the nightly statistics
task; until then rows simply accumulate.
"""

from django.contrib.gis.db import models as gis_models
from django.db import models

# How long raw realtime rows (StopEvent, FeedFetch) are kept before nightly deletion.
RAW_EVENT_RETENTION_DAYS = 60


class ScheduleRelationship(models.IntegerChoices):
    """GTFS-RT ``StopTimeUpdate.ScheduleRelationship`` (same numeric values)."""

    SCHEDULED = 0, "scheduled"
    SKIPPED = 1, "skipped"
    NO_DATA = 2, "no data"
    UNSCHEDULED = 3, "unscheduled"


class StopEvent(models.Model):
    """The latest known arrival/departure of one trip at one stop on one service day.

    One row per (city, feed, service_date, trip_id, stop_id, stop_sequence). Each poll
    upserts the row with the newest prediction and moves ``last_seen``. Feeds drop a
    stop from the trip update once the vehicle has passed it, so the last stored value
    (with ``arrival_time``/``departure_time`` <= ``last_seen``) is the closest thing to
    the observed time the feed gives us.

    Nulls are honest: a null (or an empty string for text ids) means the feed did not
    provide the value. Scheduled times are only filled when the feed gives both an
    absolute time and a delay (scheduled = time - delay); otherwise they stay null
    until static GTFS matching exists.

    Known limitation: feeds without stop_sequence (Kraków trams) key on stop_id, so a
    loop trip that serves the same stop twice keeps only its latest visit.
    """

    city_id = models.CharField(max_length=32)
    feed_id = models.CharField(max_length=64)
    # Service day of the trip: the feed's start_date if present, otherwise inferred
    # from the event times (see ``service_date_inferred``).
    service_date = models.DateField()
    service_date_inferred = models.BooleanField(default=False)
    trip_id = models.CharField(max_length=128)
    route_id = models.CharField(max_length=64, blank=True, default="")
    direction_id = models.PositiveSmallIntegerField(null=True, blank=True)
    vehicle_id = models.CharField(max_length=64, blank=True, default="")
    stop_id = models.CharField(max_length=64)
    stop_sequence = models.PositiveIntegerField(null=True, blank=True)
    schedule_relationship = models.PositiveSmallIntegerField(
        choices=ScheduleRelationship.choices, default=ScheduleRelationship.SCHEDULED
    )

    # Latest predicted (or, once passed, observed) times and delays in seconds.
    arrival_time = models.DateTimeField(null=True, blank=True)
    arrival_delay = models.IntegerField(null=True, blank=True)
    scheduled_arrival = models.DateTimeField(null=True, blank=True)
    departure_time = models.DateTimeField(null=True, blank=True)
    departure_delay = models.IntegerField(null=True, blank=True)
    scheduled_departure = models.DateTimeField(null=True, blank=True)

    # Feed header timestamp of the message that produced the latest values.
    feed_timestamp = models.DateTimeField(null=True, blank=True)
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "city_id",
                    "feed_id",
                    "service_date",
                    "trip_id",
                    "stop_id",
                    "stop_sequence",
                ],
                name="transit_stop_event_unique",
                # Feeds without stop_sequence (Kraków trams) must still deduplicate.
                nulls_distinct=False,
            ),
        ]
        indexes = [
            # Retention deletion and "recent events" queries.
            models.Index(fields=["last_seen"], name="transit_stop_event_last_seen"),
            # Statistics: per city/route over a date range.
            models.Index(
                fields=["city_id", "service_date", "route_id"],
                name="transit_stop_event_route",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.city_id}/{self.feed_id} {self.service_date} {self.trip_id} @ {self.stop_id}"


class FeedFetch(models.Model):
    """One poll of one realtime feed: makes outages and stale feeds visible."""

    class Status(models.TextChoices):
        OK = "ok", "ok"
        UNCHANGED = "unchanged", "unchanged"  # same header timestamp as the last stored poll
        STALE = "stale", "stale"  # header timestamp too old; events not stored
        HTTP_ERROR = "http_error", "HTTP error"
        NETWORK_ERROR = "network_error", "network error"
        PARSE_ERROR = "parse_error", "parse error"
        ERROR = "error", "error"

    city_id = models.CharField(max_length=32)
    feed_id = models.CharField(max_length=64)
    fetched_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    feed_timestamp = models.DateTimeField(null=True, blank=True)
    entity_count = models.PositiveIntegerField(null=True, blank=True)
    stop_event_count = models.PositiveIntegerField(null=True, blank=True)
    # Entities / stop updates dropped because a value could not be stored (reasons in
    # ``error``); the rest of the poll is stored.
    skipped_count = models.PositiveIntegerField(null=True, blank=True)
    size_bytes = models.PositiveIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(
                fields=["city_id", "feed_id", "-fetched_at"],
                name="transit_feed_fetch_latest",
            ),
            models.Index(fields=["fetched_at"], name="transit_feed_fetch_at"),
        ]

    def __str__(self) -> str:
        return f"{self.city_id}/{self.feed_id} {self.fetched_at:%Y-%m-%d %H:%M:%S} {self.status}"


# =============================================================================
# Static GTFS
#
# Every static row belongs to one FeedVersion (one import of one feed of one city).
# GTFS ids are kept as strings (``gtfs_id``) and are unique only within a feed version:
# different feeds of the same city (e.g. tram and bus) may reuse ids, and one physical
# stop may appear in several feeds. Queries for current data filter on
# ``feed_version__status == FeedVersion.Status.ACTIVE``.
#
# The tables are bulk loaded with PostgreSQL COPY by ``transit_data.static_gtfs`` and
# deleted with raw SQL (``static_gtfs.pipeline.purge_feed_version``), never through the
# ORM cascade, which would load millions of stop times into memory. For the same reason
# the StopTime foreign keys have no database constraint: the importer resolves and
# validates them itself.
# =============================================================================


class FeedVersion(models.Model):
    """One downloaded and imported version of one static GTFS feed of one city."""

    class Status(models.TextChoices):
        IMPORTING = "importing", "importing"
        ACTIVE = "active", "active"  # the version served to users; at most one per feed
        SUPERSEDED = "superseded", "superseded"  # previous version, kept for rollback
        FAILED = "failed", "failed"  # download or import failed; holds no data rows

    city_id = models.CharField(max_length=32)
    feed_id = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices)

    # A URL from city config, or ``file:<path>`` for local imports.
    source_url = models.TextField(blank=True, default="")
    downloaded_at = models.DateTimeField()
    # Last time the source was checked; also moved when the feed was unchanged.
    checked_at = models.DateTimeField(null=True, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    etag = models.TextField(blank=True, default="")
    last_modified = models.CharField(max_length=64, blank=True, default="")
    size_bytes = models.BigIntegerField(null=True, blank=True)

    # feed_info.txt (optional in GTFS; empty when absent).
    publisher_name = models.TextField(blank=True, default="")
    publisher_url = models.TextField(blank=True, default="")
    feed_lang = models.CharField(max_length=35, blank=True, default="")
    feed_info_version = models.TextField(blank=True, default="")
    feed_start_date = models.DateField(null=True, blank=True)
    feed_end_date = models.DateField(null=True, blank=True)
    # First and last day with service, computed from calendar.txt and calendar_dates.txt.
    service_start_date = models.DateField(null=True, blank=True)
    service_end_date = models.DateField(null=True, blank=True)

    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    # Counts per table, skipped rows with reasons, warnings and timings.
    report = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")
    # For failed versions: True when the feed content caused the failure (bad structure,
    # too many invalid rows, too small compared with the active version). The same file
    # (sha256) is then not imported again without --force. False for interrupted or
    # unexpected failures (database errors, time limits), which are retried next run.
    data_error = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["city_id", "feed_id"],
                condition=models.Q(status="active"),
                name="transit_feed_version_one_active",
            ),
        ]
        indexes = [
            models.Index(fields=["city_id", "feed_id", "status"], name="transit_feed_version_feed"),
        ]

    def __str__(self) -> str:
        return f"{self.city_id}/{self.feed_id} #{self.pk} {self.status}"


def _feed_version_fk(**kwargs):
    """FK to FeedVersion without its own index: each table has a unique constraint that
    starts with feed_version, which serves the same lookups."""
    return models.ForeignKey(
        FeedVersion, on_delete=models.CASCADE, related_name="+", db_index=False, **kwargs
    )


class Agency(models.Model):
    feed_version = _feed_version_fk()
    gtfs_id = models.TextField(blank=True, default="")  # agency_id may be empty in GTFS
    name = models.TextField(blank=True, default="")
    url = models.TextField(blank=True, default="")
    timezone = models.CharField(max_length=64, blank=True, default="")
    lang = models.CharField(max_length=35, blank=True, default="")
    phone = models.TextField(blank=True, default="")

    class Meta:
        verbose_name_plural = "agencies"
        constraints = [
            models.UniqueConstraint(
                fields=["feed_version", "gtfs_id"], name="transit_agency_unique"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class LocationType(models.IntegerChoices):
    """GTFS ``stops.location_type``."""

    STOP = 0, "stop / platform"
    STATION = 1, "station"
    ENTRANCE = 2, "entrance / exit"
    GENERIC_NODE = 3, "generic node"
    BOARDING_AREA = 4, "boarding area"


class Accessibility(models.IntegerChoices):
    """GTFS ``wheelchair_boarding`` / ``wheelchair_accessible`` / ``bikes_allowed``."""

    UNKNOWN = 0, "unknown"
    YES = 1, "yes"
    NO = 2, "no"


class Stop(gis_models.Model):
    feed_version = _feed_version_fk()
    # Denormalised from the feed version for "stop by city + GTFS id" lookups.
    city_id = models.CharField(max_length=32)
    gtfs_id = models.TextField()
    code = models.TextField(blank=True, default="")
    name = models.TextField(blank=True, default="")
    desc = models.TextField(blank=True, default="")
    # Null only for generic nodes and boarding areas, where GTFS coordinates are optional.
    point = gis_models.PointField(srid=4326, null=True, blank=True)
    location_type = models.PositiveSmallIntegerField(
        choices=LocationType.choices, default=LocationType.STOP
    )
    parent_station = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children"
    )
    wheelchair_boarding = models.PositiveSmallIntegerField(
        choices=Accessibility.choices, default=Accessibility.UNKNOWN
    )
    platform_code = models.TextField(blank=True, default="")
    zone_id = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["feed_version", "gtfs_id"], name="transit_stop_unique"),
        ]
        indexes = [
            models.Index(fields=["city_id", "gtfs_id"], name="transit_stop_city_gtfs"),
            # Not declared here: the trigram index ``transit_stop_name_trgm`` on
            # ``UPPER(name) gin_trgm_ops`` is created with RunSQL in migration 0002
            # (Django 5.2 renders OpClass over a function as invalid SQL). It serves
            # ``name__icontains``, which compiles to ``UPPER(name) LIKE UPPER(%s)``.
            # ``point`` has its own GiST index (spatial_index=True by default).
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.gtfs_id})"


class VehicleType(models.TextChoices):
    """App-level vehicle types (the ``vehicle_types`` of city config, plus "other")."""

    TRAM = "tram", "tram"
    BUS = "bus", "bus"
    METRO = "metro", "metro"
    RAIL = "rail", "rail"
    OTHER = "other", "other"


_BASIC_ROUTE_TYPES = {
    0: VehicleType.TRAM,
    1: VehicleType.METRO,
    2: VehicleType.RAIL,
    3: VehicleType.BUS,
    5: VehicleType.TRAM,  # cable tram
    11: VehicleType.BUS,  # trolleybus
    12: VehicleType.RAIL,  # monorail
}

# Extended GTFS route types ("Hierarchical Vehicle Type"), inclusive ranges.
_EXTENDED_ROUTE_TYPES = (
    (100, 199, VehicleType.RAIL),  # railway services
    (200, 299, VehicleType.BUS),  # coach services
    (300, 399, VehicleType.RAIL),  # suburban railway
    (400, 499, VehicleType.METRO),  # urban railway / metro / underground
    (700, 799, VehicleType.BUS),  # bus services
    (800, 899, VehicleType.BUS),  # trolleybus
    (900, 999, VehicleType.TRAM),  # tram services
)


def vehicle_type_for_route_type(route_type: int) -> str:
    """Map a basic or extended GTFS ``route_type`` to an app vehicle type."""
    if route_type in _BASIC_ROUTE_TYPES:
        return _BASIC_ROUTE_TYPES[route_type]
    for low, high, vehicle_type in _EXTENDED_ROUTE_TYPES:
        if low <= route_type <= high:
            return vehicle_type
    return VehicleType.OTHER


class Route(models.Model):
    feed_version = _feed_version_fk()
    city_id = models.CharField(max_length=32)
    gtfs_id = models.TextField()
    agency = models.ForeignKey(Agency, on_delete=models.SET_NULL, null=True, blank=True)
    short_name = models.TextField(blank=True, default="")
    long_name = models.TextField(blank=True, default="")
    desc = models.TextField(blank=True, default="")
    # Stored as in the feed; may be an extended type (e.g. 900 for trams).
    # ``vehicle_type`` gives the app-level type.
    route_type = models.PositiveSmallIntegerField()
    # Uppercase hex without '#'; empty when absent or invalid in the feed.
    color = models.CharField(max_length=6, blank=True, default="")
    text_color = models.CharField(max_length=6, blank=True, default="")
    sort_order = models.IntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["feed_version", "gtfs_id"], name="transit_route_unique"
            ),
        ]
        indexes = [
            models.Index(fields=["city_id", "gtfs_id"], name="transit_route_city_gtfs"),
            models.Index(fields=["city_id", "short_name"], name="transit_route_city_short"),
        ]

    def __str__(self) -> str:
        return f"{self.short_name or self.long_name} ({self.gtfs_id})"

    @property
    def vehicle_type(self) -> str:
        return vehicle_type_for_route_type(self.route_type)


class Calendar(models.Model):
    """calendar.txt: weekly pattern of one service in a date range."""

    feed_version = _feed_version_fk()
    service_id = models.TextField()
    monday = models.BooleanField()
    tuesday = models.BooleanField()
    wednesday = models.BooleanField()
    thursday = models.BooleanField()
    friday = models.BooleanField()
    saturday = models.BooleanField()
    sunday = models.BooleanField()
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["feed_version", "service_id"], name="transit_calendar_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.service_id} {self.start_date}..{self.end_date}"


class CalendarDate(models.Model):
    """calendar_dates.txt: a service added (1) or removed (2) on one date."""

    class ExceptionType(models.IntegerChoices):
        ADDED = 1, "added"
        REMOVED = 2, "removed"

    feed_version = _feed_version_fk()
    service_id = models.TextField()
    date = models.DateField()
    exception_type = models.PositiveSmallIntegerField(choices=ExceptionType.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["feed_version", "service_id", "date"],
                name="transit_calendar_date_unique",
            ),
        ]
        indexes = [
            # "Which services run on date D?"
            models.Index(fields=["feed_version", "date"], name="transit_calendar_date_date"),
        ]

    def __str__(self) -> str:
        return f"{self.service_id} {self.date} {self.get_exception_type_display()}"


class Shape(gis_models.Model):
    """shapes.txt: the points of one shape_id as a line, ordered by shape_pt_sequence."""

    feed_version = _feed_version_fk()
    gtfs_id = models.TextField()
    geometry = gis_models.LineStringField(srid=4326)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["feed_version", "gtfs_id"], name="transit_shape_unique"
            ),
        ]

    def __str__(self) -> str:
        return self.gtfs_id


class Trip(models.Model):
    feed_version = _feed_version_fk()
    gtfs_id = models.TextField()
    route = models.ForeignKey(Route, on_delete=models.CASCADE, db_index=False)
    # Refers to Calendar.service_id and/or CalendarDate.service_id of the same version.
    service_id = models.TextField()
    headsign = models.TextField(blank=True, default="")
    short_name = models.TextField(blank=True, default="")
    direction_id = models.PositiveSmallIntegerField(null=True, blank=True)
    block_id = models.TextField(blank=True, default="")
    shape = models.ForeignKey(Shape, on_delete=models.SET_NULL, null=True, blank=True)
    wheelchair_accessible = models.PositiveSmallIntegerField(
        choices=Accessibility.choices, default=Accessibility.UNKNOWN
    )
    bikes_allowed = models.PositiveSmallIntegerField(
        choices=Accessibility.choices, default=Accessibility.UNKNOWN
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["feed_version", "gtfs_id"], name="transit_trip_unique"),
        ]
        indexes = [
            models.Index(fields=["route", "direction_id"], name="transit_trip_route_dir"),
            models.Index(fields=["feed_version", "service_id"], name="transit_trip_service"),
        ]

    def __str__(self) -> str:
        return self.gtfs_id


class PickupDropOff(models.IntegerChoices):
    """GTFS ``pickup_type`` / ``drop_off_type``."""

    REGULAR = 0, "regular"
    NONE = 1, "none"
    PHONE = 2, "phone agency"
    COORDINATE = 3, "coordinate with driver"


class StopTime(models.Model):
    """stop_times.txt. Times are seconds since service-day midnight (may exceed 86400).

    Strictly, GTFS times count from "noon minus 12 h" of the service day, which differs
    from midnight on DST change days; consumers converting to wall-clock time should
    apply that rule.

    No database foreign key constraints (see the comment above FeedVersion), and
    ``feed_version`` is not indexed: rows are reached through their trip or stop.
    """

    feed_version = models.ForeignKey(
        FeedVersion,
        on_delete=models.DO_NOTHING,
        related_name="+",
        db_index=False,
        db_constraint=False,
    )
    trip = models.ForeignKey(Trip, on_delete=models.DO_NOTHING, db_index=False, db_constraint=False)
    stop = models.ForeignKey(Stop, on_delete=models.DO_NOTHING, db_index=False, db_constraint=False)
    stop_sequence = models.PositiveIntegerField()
    # Null for non-timepoint stops without times (consumers interpolate).
    arrival_time = models.IntegerField(null=True, blank=True)
    departure_time = models.IntegerField(null=True, blank=True)
    stop_headsign = models.TextField(blank=True, default="")
    pickup_type = models.PositiveSmallIntegerField(
        choices=PickupDropOff.choices, default=PickupDropOff.REGULAR
    )
    drop_off_type = models.PositiveSmallIntegerField(
        choices=PickupDropOff.choices, default=PickupDropOff.REGULAR
    )
    shape_dist_traveled = models.FloatField(null=True, blank=True)
    timepoint = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["trip", "stop_sequence"], name="transit_stop_time_trip_seq"),
            models.Index(fields=["stop", "trip"], name="transit_stop_time_stop_trip"),
        ]

    def __str__(self) -> str:
        return f"{self.trip_id}#{self.stop_sequence} @ {self.stop_id}"


class Frequency(models.Model):
    """frequencies.txt: a trip repeated every ``headway_secs`` within a time window."""

    feed_version = models.ForeignKey(FeedVersion, on_delete=models.CASCADE, related_name="+")
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE)
    start_time = models.IntegerField()  # seconds since service-day midnight
    end_time = models.IntegerField()
    headway_secs = models.PositiveIntegerField()
    exact_times = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "frequencies"

    def __str__(self) -> str:
        return f"{self.trip_id} every {self.headway_secs}s"
