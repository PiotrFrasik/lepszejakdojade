"""Raw realtime data collected from GTFS-Realtime feeds.

GTFS ids (trip, route, stop) are stored as plain strings: they refer to the static
GTFS feed of the same city, but there are no foreign keys, so realtime data can be
collected before (and independently of) the static import.

Retention: raw stop events and fetch log rows are kept for
``RAW_EVENT_RETENTION_DAYS`` days. Aggregated statistics (built nightly from the raw
events) are kept indefinitely. The deletion job is part of the nightly statistics
task; until then rows simply accumulate.
"""

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
