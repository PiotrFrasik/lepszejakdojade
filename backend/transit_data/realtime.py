"""GTFS-Realtime TripUpdates collector: fetch, parse and store stop events.

The collector is generic: it polls every ``gtfs_rt`` feed with ``entity: trip_updates``
in every city config, so adding a city is a config change only.

Pipeline per feed: ``fetch_feed`` (HTTP) -> ``parse_feed`` (protobuf) ->
``extract_stop_events`` (pure, no database) -> ``upsert_stop_events`` (one SQL upsert
per batch). Every poll writes one ``FeedFetch`` row, including failures, and never
raises: a broken feed must not stop the other feeds or crash the worker.

Settings (all optional, defaults in brackets):
- ``TRANSIT_REALTIME_HTTP_TIMEOUT`` [10] seconds per HTTP request.
- ``TRANSIT_REALTIME_STALE_AFTER`` [300] seconds; a feed whose header timestamp is older
  is logged as stale and its events are not stored (they are not fresh observations).
- ``TRANSIT_REALTIME_MAX_BYTES`` [20 MB] upper bound for one feed download.
"""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Min
from django.utils import timezone
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from cities.registry import City, Feed, all_cities

from .models import FeedFetch, ScheduleRelationship, StopEvent

logger = logging.getLogger(__name__)

TRIP_UPDATES = "trip_updates"

# Trips without start_date get their service day from their event times shifted back by
# this many hours, so a trip running 23:50-00:20 belongs to the day it started on.
# A trip already running at 03:00 keeps the date it was first stored under
# (TRIP_DATE_MEMORY); only a trip first seen after 03:00 that started before it is wrong.
SERVICE_DAY_CUTOFF = timedelta(hours=3)

# A trip without start_date that was stored this recently keeps its stored service date
# (see _resolve_service_date). Must be well below one day: tram trip_ids repeat daily.
TRIP_DATE_MEMORY = timedelta(hours=4)

# Generic client name: no project or personal details are sent to publishers.
USER_AGENT = "gtfs-rt-collector/1.0"

UPSERT_BATCH_SIZE = 1000

_TRIP_CANCELED = gtfs_realtime_pb2.TripDescriptor.CANCELED


def _setting(name: str, default):
    return getattr(settings, name, default)


# ---------------------------------------------------------------------- feeds


def trip_update_feeds(cities: list[City] | None = None) -> list[tuple[City, Feed]]:
    """All (city, feed) pairs with a configured TripUpdates URL."""
    return [
        (city, feed)
        for city in (all_cities() if cities is None else cities)
        for feed in city.feeds
        if feed.kind == "gtfs_rt" and feed.entity == TRIP_UPDATES and feed.url
    ]


class FetchError(Exception):
    def __init__(self, status: str, message: str, http_status: int | None = None):
        super().__init__(message)
        self.status = status
        self.http_status = http_status


def fetch_feed(url: str) -> tuple[bytes, int]:
    """Download a feed. Returns (body, http_status); raises FetchError."""
    timeout = _setting("TRANSIT_REALTIME_HTTP_TIMEOUT", 10)
    max_bytes = _setting("TRANSIT_REALTIME_MAX_BYTES", 20 * 1024 * 1024)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/x-protobuf, application/octet-stream",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read(max_bytes + 1)
            status = response.status
    except urllib.error.HTTPError as exc:
        raise FetchError(FeedFetch.Status.HTTP_ERROR, f"HTTP {exc.code}", exc.code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise FetchError(FeedFetch.Status.NETWORK_ERROR, str(reason)) from exc
    if len(body) > max_bytes:
        raise FetchError(FeedFetch.Status.ERROR, f"feed larger than {max_bytes} bytes", status)
    return body, status


def parse_feed(body: bytes) -> gtfs_realtime_pb2.FeedMessage:
    """Parse a protobuf FeedMessage; raises FetchError on invalid data."""
    message = gtfs_realtime_pb2.FeedMessage()
    try:
        message.ParseFromString(body)
    except (DecodeError, ValueError) as exc:
        raise FetchError(FeedFetch.Status.PARSE_ERROR, f"invalid protobuf: {exc}") from exc
    # The protobuf runtime accepts an empty body as an empty message; an outage page or
    # truncated download must not count as "feed OK with zero vehicles".
    if not message.IsInitialized():
        raise FetchError(
            FeedFetch.Status.PARSE_ERROR,
            "missing required fields: " + ", ".join(message.FindInitializationErrors()),
        )
    return message


# ---------------------------------------------------------------- extraction


@dataclass
class StopEventRow:
    """One stop event as extracted from a feed (no database access)."""

    city_id: str
    feed_id: str
    service_date: date
    service_date_inferred: bool
    trip_id: str
    stop_id: str
    stop_sequence: int | None
    route_id: str = ""
    direction_id: int | None = None
    vehicle_id: str = ""
    schedule_relationship: int = ScheduleRelationship.SCHEDULED
    arrival_time: datetime | None = None
    arrival_delay: int | None = None
    scheduled_arrival: datetime | None = None
    departure_time: datetime | None = None
    departure_delay: int | None = None
    scheduled_departure: datetime | None = None
    feed_timestamp: datetime | None = None

    @property
    def key(self) -> tuple:
        return (
            self.city_id,
            self.feed_id,
            self.service_date,
            self.trip_id,
            self.stop_id,
            self.stop_sequence,
        )


def _from_epoch(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


class InvalidValue(ValueError):
    """A value in one entity / stop update that cannot be stored; it is skipped."""


# Column limits, so one oversized value skips one entity instead of failing the upsert.
_MAX_LENGTH = {
    name: StopEvent._meta.get_field(name).max_length
    for name in ("trip_id", "route_id", "vehicle_id", "stop_id")
}
_MAX_STOP_SEQUENCE = 2**31 - 1  # PositiveIntegerField is a signed 32-bit column
_MAX_DIRECTION_ID = 2**15 - 1  # PositiveSmallIntegerField
# Event times outside this range are nonsense (and could overflow datetime arithmetic).
_MIN_EVENT_TIME = datetime(2000, 1, 1, tzinfo=UTC)
_MAX_EVENT_TIME = datetime(2100, 1, 1, tzinfo=UTC)


def _check_id(name: str, value: str) -> str:
    if len(value) > _MAX_LENGTH[name]:
        raise InvalidValue(f"{name} longer than {_MAX_LENGTH[name]}")
    if "\x00" in value:
        raise InvalidValue(f"{name} contains NUL")
    return value


def _stop_time_event(stu, name: str) -> tuple[datetime | None, int | None, datetime | None]:
    """(time, delay, scheduled) of a StopTimeEvent; nulls when the feed gives nothing.

    ``time: 0`` is not a valid timestamp (ZTP sends ``time: 0, delay: 0`` on some last
    stops); the whole event is then treated as missing. Raises InvalidValue for times
    outside a plausible range.
    """
    if not stu.HasField(name):
        return None, None, None
    event = getattr(stu, name)
    if event.HasField("time") and event.time <= 0:
        return None, None, None
    try:
        event_time = _from_epoch(event.time) if event.HasField("time") else None
        delay = event.delay if event.HasField("delay") else None
        scheduled = None
        if event_time is not None and delay is not None:
            scheduled = event_time - timedelta(seconds=delay)
    except (OverflowError, ValueError, OSError) as exc:
        raise InvalidValue(f"{name} time out of range") from exc
    for value in (event_time, scheduled):
        if value is not None and not _MIN_EVENT_TIME <= value < _MAX_EVENT_TIME:
            raise InvalidValue(f"{name} time out of range")
    return event_time, delay, scheduled


def _parse_start_date(value: str) -> date | None:
    if len(value) != 8 or not value.isdigit():
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None


def infer_service_date(moment: datetime, tz: ZoneInfo) -> date:
    """Service day of a trip with no start_date, from any time during the trip."""
    return (moment.astimezone(tz) - SERVICE_DAY_CUTOFF).date()


def _first_event_time(trip_update) -> datetime | None:
    times = []
    for stu in trip_update.stop_time_update:
        for name in ("arrival", "departure"):
            if not stu.HasField(name) or getattr(stu, name).time <= 0:
                continue
            try:
                moment = _from_epoch(getattr(stu, name).time)
            except (OverflowError, ValueError, OSError):
                continue
            if _MIN_EVENT_TIME <= moment < _MAX_EVENT_TIME:
                times.append(moment)
    return min(times) if times else None


def _resolve_service_date(
    known: date | None, first_event: datetime | None, fallback: datetime, tz: ZoneInfo
) -> date:
    """Service date of a trip without start_date.

    Passed stops drop out of the feed, so inferring from the earliest *remaining* event
    would move a trip running across the cutoff (03:00) to the next day mid-trip. A date
    already stored for the same trip shortly before wins, as long as it is the inferred
    day or the day before (anything else is an older run of a daily-repeated trip_id).
    """
    inferred = infer_service_date(first_event or fallback, tz)
    if known is not None and inferred - timedelta(days=1) <= known <= inferred:
        return known
    return inferred


def extract_stop_events(
    message: gtfs_realtime_pb2.FeedMessage,
    city: City,
    feed: Feed,
    fetched_at: datetime,
    known_service_dates: dict[str, date] | None = None,
    skipped: Counter | None = None,
) -> list[StopEventRow]:
    """Turn a TripUpdates FeedMessage into deduplicated stop event rows.

    ``known_service_dates`` maps trip_id -> service_date of trips without start_date
    stored by recent polls (see ``recent_service_dates``). Entities and stop updates that
    cannot be stored (oversized ids, absurd times) are skipped and counted by reason in
    ``skipped``; the rest of the message is still returned.
    """
    tz = city.zoneinfo
    known_service_dates = known_service_dates or {}
    if skipped is None:
        skipped = Counter()
    header_ts = message.header.timestamp if message.header.HasField("timestamp") else 0
    feed_timestamp = _from_epoch(header_ts) if header_ts > 0 else None
    rows: dict[tuple, StopEventRow] = {}

    for entity in message.entity:
        if entity.is_deleted or not entity.HasField("trip_update"):
            continue
        trip_update = entity.trip_update
        trip = trip_update.trip
        if not trip.trip_id or trip.schedule_relationship == _TRIP_CANCELED:
            continue
        try:
            trip_id = _check_id("trip_id", trip.trip_id)
            route_id = _check_id("route_id", trip.route_id)
            vehicle_id = (
                _check_id("vehicle_id", trip_update.vehicle.id)
                if trip_update.HasField("vehicle")
                else ""
            )
            direction_id = trip.direction_id if trip.HasField("direction_id") else None
            if direction_id is not None and direction_id > _MAX_DIRECTION_ID:
                raise InvalidValue("direction_id out of range")
        except InvalidValue as exc:
            skipped[f"entity: {exc}"] += 1
            continue

        service_date = _parse_start_date(trip.start_date) if trip.start_date else None
        inferred = service_date is None
        if inferred:
            service_date = _resolve_service_date(
                known_service_dates.get(trip_id),
                _first_event_time(trip_update),
                feed_timestamp or fetched_at,
                tz,
            )

        for stu in trip_update.stop_time_update:
            if not stu.stop_id:
                # Without stop_id we cannot identify the stop before static GTFS matching.
                continue
            try:
                stop_id = _check_id("stop_id", stu.stop_id)
                stop_sequence = stu.stop_sequence if stu.HasField("stop_sequence") else None
                if stop_sequence is not None and stop_sequence > _MAX_STOP_SEQUENCE:
                    raise InvalidValue("stop_sequence out of range")
                arrival = _stop_time_event(stu, "arrival")
                departure = _stop_time_event(stu, "departure")
            except InvalidValue as exc:
                skipped[f"stop update: {exc}"] += 1
                continue
            relationship = stu.schedule_relationship
            has_data = any(v is not None for v in (*arrival, *departure))
            if not has_data and relationship != ScheduleRelationship.SKIPPED:
                continue
            row = StopEventRow(
                city_id=city.id,
                feed_id=feed.id,
                service_date=service_date,
                service_date_inferred=inferred,
                trip_id=trip_id,
                stop_id=stop_id,
                stop_sequence=stop_sequence,
                route_id=route_id,
                direction_id=direction_id,
                vehicle_id=vehicle_id,
                schedule_relationship=relationship,
                arrival_time=arrival[0],
                arrival_delay=arrival[1],
                scheduled_arrival=arrival[2],
                departure_time=departure[0],
                departure_delay=departure[1],
                scheduled_departure=departure[2],
                feed_timestamp=feed_timestamp,
            )
            rows[row.key] = row  # last one wins within a message
    return list(rows.values())


def recent_service_dates(city_id: str, feed_id: str, now: datetime) -> dict[str, date]:
    """trip_id -> service_date for inferred-date trips seen within TRIP_DATE_MEMORY.

    One query per poll. If a trip was stored under two dates, the earlier one wins.
    """
    rows = (
        StopEvent.objects.filter(
            city_id=city_id,
            feed_id=feed_id,
            service_date_inferred=True,
            last_seen__gte=now - TRIP_DATE_MEMORY,
        )
        .values("trip_id")
        .annotate(service_date=Min("service_date"))
        .values_list("trip_id", "service_date")
    )
    return dict(rows)


# ------------------------------------------------------------------- storage

_KEY_COLUMNS = ("city_id", "feed_id", "service_date", "trip_id", "stop_id", "stop_sequence")
_INSERT_COLUMNS = (
    *_KEY_COLUMNS,
    "service_date_inferred",
    "route_id",
    "direction_id",
    "vehicle_id",
    "schedule_relationship",
    "arrival_time",
    "arrival_delay",
    "scheduled_arrival",
    "departure_time",
    "departure_delay",
    "scheduled_departure",
    "feed_timestamp",
    "first_seen",
    "last_seen",
)


def _event_group_update(prefix: str, scheduled: str) -> list[str]:
    """Keep the previous arrival/departure when the new message has none for it.

    Values move as a group so time, delay and scheduled time always come from the same
    message.
    """
    empty = f"EXCLUDED.{prefix}_time IS NULL AND EXCLUDED.{prefix}_delay IS NULL"
    return [
        f"{col} = CASE WHEN {empty} THEN t.{col} ELSE EXCLUDED.{col} END"
        for col in (f"{prefix}_time", f"{prefix}_delay", scheduled)
    ]


_UPDATE_SET = ",\n    ".join(
    [
        "route_id = COALESCE(NULLIF(EXCLUDED.route_id, ''), t.route_id)",
        "direction_id = COALESCE(EXCLUDED.direction_id, t.direction_id)",
        "vehicle_id = COALESCE(NULLIF(EXCLUDED.vehicle_id, ''), t.vehicle_id)",
        "schedule_relationship = EXCLUDED.schedule_relationship",
        *_event_group_update("arrival", "scheduled_arrival"),
        *_event_group_update("departure", "scheduled_departure"),
        "feed_timestamp = EXCLUDED.feed_timestamp",
        "last_seen = EXCLUDED.last_seen",
    ]
)


def _upsert_sql(row_count: int) -> str:
    placeholders = "(" + ", ".join(["%s"] * len(_INSERT_COLUMNS)) + ")"
    return (
        f"INSERT INTO {StopEvent._meta.db_table} AS t ({', '.join(_INSERT_COLUMNS)})\n"
        f"VALUES {', '.join([placeholders] * row_count)}\n"
        f"ON CONFLICT ON CONSTRAINT transit_stop_event_unique DO UPDATE SET\n"
        f"    {_UPDATE_SET}"
    )


def upsert_stop_events(rows: list[StopEventRow], seen_at: datetime) -> int:
    """Insert new stop events and refresh existing ones. Returns the row count."""
    with transaction.atomic(), connection.cursor() as cursor:
        for start in range(0, len(rows), UPSERT_BATCH_SIZE):
            batch = rows[start : start + UPSERT_BATCH_SIZE]
            params: list = []
            for row in batch:
                values = asdict(row)
                values["first_seen"] = seen_at
                values["last_seen"] = seen_at
                params.extend(values[col] for col in _INSERT_COLUMNS)
            cursor.execute(_upsert_sql(len(batch)), params)
    return len(rows)


# ---------------------------------------------------------------- collection


def _feed_lock_key(city_id: str, feed_id: str) -> str:
    return f"transit_data.trip_updates:{city_id}:{feed_id}"


def _try_lock(key: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", [key])
        return bool(cursor.fetchone()[0])


def _unlock(key: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [key])


def _last_stored_timestamp(city_id: str, feed_id: str) -> datetime | None:
    return (
        FeedFetch.objects.filter(
            city_id=city_id,
            feed_id=feed_id,
            status__in=[FeedFetch.Status.OK, FeedFetch.Status.UNCHANGED],
        )
        .order_by("-fetched_at")
        .values_list("feed_timestamp", flat=True)
        .first()
    )


def collect_feed(city: City, feed: Feed, dump_dir: Path | None = None) -> FeedFetch | None:
    """Poll one TripUpdates feed and store its stop events. Never raises.

    Returns the FeedFetch log row, or None when another worker is already polling
    this feed (overlapping beat runs are skipped, not queued).
    """
    lock_key = _feed_lock_key(city.id, feed.id)
    try:
        if not _try_lock(lock_key):
            logger.info("Skipping %s/%s: previous poll still running", city.id, feed.id)
            return None
    except Exception:
        logger.exception("Cannot lock %s/%s (database unavailable?)", city.id, feed.id)
        return None

    started = time.monotonic()
    fetched_at = timezone.now()
    log = FeedFetch(city_id=city.id, feed_id=feed.id, fetched_at=fetched_at)
    try:
        body, log.http_status = fetch_feed(feed.url)
        log.size_bytes = len(body)
        if dump_dir is not None:
            dump_dir.mkdir(parents=True, exist_ok=True)
            name = f"{city.id}_{feed.id}_{fetched_at:%Y%m%dT%H%M%SZ}.pb"
            (dump_dir / name).write_bytes(body)
        message = parse_feed(body)
        log.entity_count = len(message.entity)
        header_ts = message.header.timestamp if message.header.HasField("timestamp") else 0
        log.feed_timestamp = _from_epoch(header_ts) if header_ts > 0 else None

        stale_after = timedelta(seconds=_setting("TRANSIT_REALTIME_STALE_AFTER", 300))
        if log.feed_timestamp is not None and fetched_at - log.feed_timestamp > stale_after:
            log.status = FeedFetch.Status.STALE
            logger.warning(
                "Feed %s/%s is stale: header timestamp %s",
                city.id,
                feed.id,
                log.feed_timestamp.isoformat(),
            )
        elif log.feed_timestamp is not None and log.feed_timestamp == _last_stored_timestamp(
            city.id, feed.id
        ):
            log.status = FeedFetch.Status.UNCHANGED
        else:
            skipped: Counter = Counter()
            rows = extract_stop_events(
                message,
                city,
                feed,
                fetched_at,
                known_service_dates=recent_service_dates(city.id, feed.id, fetched_at),
                skipped=skipped,
            )
            log.stop_event_count = upsert_stop_events(rows, fetched_at)
            log.skipped_count = sum(skipped.values())
            log.status = FeedFetch.Status.OK
            if skipped:
                # Partial data is still OK; the reasons go to the log row, once per poll.
                summary = "; ".join(f"{reason} x{n}" for reason, n in skipped.most_common())
                log.error = f"skipped: {summary}"[:500]
                logger.warning("Feed %s/%s: %s", city.id, feed.id, log.error)
    except FetchError as exc:
        log.status = exc.status
        log.http_status = exc.http_status or log.http_status
        log.error = str(exc)[:500]
        logger.warning("Feed %s/%s failed: %s: %s", city.id, feed.id, exc.status, exc)
    except Exception as exc:
        log.status = FeedFetch.Status.ERROR
        log.error = f"{type(exc).__name__}: {exc}"[:500]
        logger.exception("Feed %s/%s failed", city.id, feed.id)
    finally:
        log.duration_ms = int((time.monotonic() - started) * 1000)
        try:
            log.save()
        except Exception:
            logger.exception("Cannot save fetch log for %s/%s", city.id, feed.id)
        try:
            _unlock(lock_key)
        except Exception:
            logger.exception("Cannot release lock for %s/%s", city.id, feed.id)
    logger.info(
        "Feed %s/%s: %s, %s entities, %s stop events, %s ms",
        city.id,
        feed.id,
        log.status,
        log.entity_count,
        log.stop_event_count,
        log.duration_ms,
    )
    return log


def collect_all_trip_updates(
    city_id: str | None = None,
    feed_id: str | None = None,
    dump_dir: Path | None = None,
) -> list[FeedFetch]:
    """Poll every configured TripUpdates feed (optionally filtered). Never raises."""
    results = []
    for city, feed in trip_update_feeds():
        if city_id and city.id != city_id:
            continue
        if feed_id and feed.id != feed_id:
            continue
        log = collect_feed(city, feed, dump_dir=dump_dir)
        if log is not None:
            results.append(log)
    return results
