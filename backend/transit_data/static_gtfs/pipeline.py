"""Import one static GTFS feed end to end, or all static feeds of a city.

Per feed (``import_feed``):

1. Skip feeds without a URL in city config (e.g. rail feeds not chosen yet).
2. Take a PostgreSQL advisory lock for (city, feed), so a Celery run and a manual
   command never import the same feed at once. Versions left in ``importing`` by a
   crashed process are marked failed.
3. Download with a conditional GET (ETag / Last-Modified of the active version). A 304
   or an unchanged sha256 ends the run: only ``checked_at`` of the active version moves.
4. Validate the structure, then load everything into a new FeedVersion inside one
   transaction. Only if that succeeds is the new version marked active and the old one
   superseded, in the same transaction. Any failure rolls back the data; the active
   version stays untouched and the new version row is kept as ``failed`` with the error.
   A failure caused by the file (format, too many invalid rows, much smaller than the
   active version) sets ``data_error``: the same sha256 is then not imported again
   without ``force``. Interrupted or unexpected failures are retried on the next run.
5. After commit: ANALYZE the tables and delete versions beyond the previous one.

``--force`` (``force=True``) skips the conditional GET and the sha256 comparison.

Settings (optional, defaults in brackets):
- ``TRANSIT_GTFS_KEEP_SUPERSEDED`` [1] previous versions kept per feed with their data
  (for rollback). A kept version of a feed with ~7 M stop times costs about 1.4 GB.
- ``TRANSIT_GTFS_MIN_SHARE_OF_ACTIVE`` [0.5] reject a new version whose trips or stop
  times are below this share of the active version (a truncated or partial feed);
  ``force=True`` bypasses the check.
- ``TRANSIT_GTFS_KEEP_FAILED`` [5] failed version rows kept per feed (they hold no data).
- ``TRANSIT_GTFS_MAX_UNCOMPRESSED_BYTES`` [5 GB] limit for the unpacked archive.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from psycopg import sql

from cities.registry import City, Feed, get_city

from ..models import (
    Agency,
    Calendar,
    CalendarDate,
    FeedVersion,
    Frequency,
    Route,
    Shape,
    Stop,
    StopTime,
    Trip,
)
from .download import DownloadError, FetchedFeed, download_feed, local_feed
from .loader import FeedRejected, expiry_warning, load_feed
from .reader import GtfsFormatError, GtfsSource, validate_structure
from .report import ImportReport

logger = logging.getLogger(__name__)

STATIC_KIND = "gtfs_static"


class Outcome:
    IMPORTED = "imported"
    UNCHANGED = "unchanged"
    FAILED = "failed"
    SKIPPED = "skipped"  # no URL configured
    BUSY = "busy"  # another import of the same feed is running


@dataclass
class ImportResult:
    city_id: str
    feed_id: str
    outcome: str
    message: str = ""
    feed_version_id: int | None = None
    report: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "city_id": self.city_id,
            "feed_id": self.feed_id,
            "outcome": self.outcome,
            "message": self.message,
            "feed_version_id": self.feed_version_id,
        }


class ImportConfigError(Exception):
    """Unknown city or feed id."""


def static_feeds(city: City) -> list[Feed]:
    return [feed for feed in city.feeds if feed.kind == STATIC_KIND]


def import_city(
    city_id: str, feed_id: str | None = None, force: bool = False, file: Path | None = None
) -> list[ImportResult]:
    """Import the static feeds of one city (or one feed of it). Never raises for a
    feed-level failure; raises ImportConfigError for an unknown city or feed."""
    city = get_city(city_id)
    if city is None:
        raise ImportConfigError(f"unknown city {city_id!r}")
    feeds = static_feeds(city)
    if feed_id is not None:
        feeds = [feed for feed in feeds if feed.id == feed_id]
        if not feeds:
            raise ImportConfigError(f"city {city_id!r} has no static GTFS feed {feed_id!r}")
    if file is not None and len(feeds) != 1:
        raise ImportConfigError("--file needs exactly one feed; pass --feed")
    return [import_feed(city, feed, force=force, file=file) for feed in feeds]


def import_feed(
    city: City, feed: Feed, force: bool = False, file: Path | None = None
) -> ImportResult:
    """Import one feed. Never raises for download, format or data problems."""
    if file is None and not feed.url:
        logger.info("GTFS %s/%s: no URL configured, skipped", city.id, feed.id)
        return ImportResult(city.id, feed.id, Outcome.SKIPPED, "no URL configured")

    with _feed_lock(city.id, feed.id) as locked:
        if not locked:
            logger.warning("GTFS %s/%s: another import is running, skipped", city.id, feed.id)
            return ImportResult(city.id, feed.id, Outcome.BUSY, "another import is running")
        _fail_interrupted(city.id, feed.id)
        result = _import_locked(city, feed, force, file)
    log = logger.warning if result.outcome == Outcome.FAILED else logger.info
    log("GTFS %s/%s: %s %s", city.id, feed.id, result.outcome, result.message)
    return result


def _import_locked(city: City, feed: Feed, force: bool, file: Path | None) -> ImportResult:
    started = time.monotonic()
    now = timezone.now()
    report = ImportReport()
    active = FeedVersion.objects.filter(
        city_id=city.id, feed_id=feed.id, status=FeedVersion.Status.ACTIVE
    ).first()
    source_url = f"file:{file}" if file is not None else feed.url
    workdir = Path(tempfile.mkdtemp(prefix="gtfs-"))
    try:
        # ------------------------------------------------------------ download
        try:
            if file is not None:
                fetched = local_feed(Path(file))
            else:
                use_conditional = active is not None and not force
                fetched = download_feed(
                    feed.url,
                    workdir / "feed.zip",
                    etag=active.etag if use_conditional else "",
                    last_modified=active.last_modified if use_conditional else "",
                )
        except DownloadError as exc:
            version = _record_failure(city, feed, source_url, now, f"download failed: {exc}")
            return ImportResult(
                city.id, feed.id, Outcome.FAILED, f"download failed: {exc}", version.pk
            )
        report.timings_s["download"] = time.monotonic() - started

        unchanged = fetched.not_modified or (active is not None and fetched.sha256 == active.sha256)
        if not force and active is not None and unchanged:
            active.checked_at = now
            active.save(update_fields=["checked_at"])
            reason = "not modified (HTTP 304)" if fetched.not_modified else "same sha256"
            return ImportResult(
                city.id, feed.id, Outcome.UNCHANGED, reason, active.pk, active.report
            )
        if fetched.not_modified:
            # 304 without an active version cannot happen with our headers; be safe.
            return ImportResult(city.id, feed.id, Outcome.UNCHANGED, "not modified (HTTP 304)")
        if not force:
            # The same file was already rejected for its content: do not repeat the import
            # every night. Interrupted or unexpected failures (data_error=False) of the same
            # file are retried.
            last_failed = (
                FeedVersion.objects.filter(
                    city_id=city.id,
                    feed_id=feed.id,
                    status=FeedVersion.Status.FAILED,
                    sha256=fetched.sha256,
                )
                .order_by("-created_at", "-pk")
                .first()
            )
            if last_failed is not None and last_failed.data_error:
                return ImportResult(
                    city.id,
                    feed.id,
                    Outcome.UNCHANGED,
                    f"same file as failed version {last_failed.pk}; use --force to retry",
                    last_failed.pk,
                )

        # --------------------------------------------------------------- import
        version = FeedVersion.objects.create(
            city_id=city.id,
            feed_id=feed.id,
            status=FeedVersion.Status.IMPORTING,
            source_url=source_url,
            downloaded_at=now,
            checked_at=now,
            sha256=fetched.sha256,
            etag=fetched.etag,
            last_modified=fetched.last_modified,
            size_bytes=fetched.size_bytes,
        )
        return _load_version(city, version, fetched, report, started, None if force else active)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _check_against_active(active: FeedVersion | None, report: ImportReport) -> None:
    """Reject a version much smaller than the active one (truncated or partial feed)."""
    if active is None:
        return
    min_share = getattr(settings, "TRANSIT_GTFS_MIN_SHARE_OF_ACTIVE", 0.5)
    active_counts = (active.report or {}).get("counts") or {}
    comparison = {"active_feed_version_id": active.pk, "min_share": min_share}
    problems = []
    for table in ("trips", "stop_times"):
        new, old = report.counts.get(table, 0), active_counts.get(table)
        comparison[table] = {"new": new, "active": old}
        if old and new < old * min_share:
            problems.append(f"{table}: {new} vs {old} in active version {active.pk}")
    report.comparison = comparison
    if problems:
        raise FeedRejected(
            f"new version is below {min_share:.0%} of the active version ("
            + "; ".join(problems)
            + "); use --force to import anyway"
        )


def _load_version(
    city: City,
    version: FeedVersion,
    fetched: FetchedFeed,
    report: ImportReport,
    started: float,
    compare_with: FeedVersion | None,
) -> ImportResult:
    load_started = time.monotonic()
    max_uncompressed = getattr(
        settings, "TRANSIT_GTFS_MAX_UNCOMPRESSED_BYTES", 5 * 1024 * 1024 * 1024
    )
    try:
        with GtfsSource(fetched.path, max_uncompressed_bytes=max_uncompressed) as source:
            validate_structure(source)
            with transaction.atomic():
                load_feed(version, source, report)
                _check_against_active(compare_with, report)
                warning = expiry_warning(
                    version.service_end_date, timezone.now().astimezone(city.zoneinfo).date()
                )
                if warning:
                    report.warn(warning)
                FeedVersion.objects.filter(
                    city_id=version.city_id,
                    feed_id=version.feed_id,
                    status=FeedVersion.Status.ACTIVE,
                ).exclude(pk=version.pk).update(status=FeedVersion.Status.SUPERSEDED)
                report.timings_s["load"] = time.monotonic() - load_started
                report.timings_s["total"] = time.monotonic() - started
                version.status = FeedVersion.Status.ACTIVE
                version.imported_at = timezone.now()
                version.duration_ms = int((time.monotonic() - started) * 1000)
                version.report = report.as_dict()
                version.save()
    except (GtfsFormatError, FeedRejected) as exc:
        return _mark_failed(version, report, started, str(exc), data_error=True)
    except Exception as exc:
        # Database errors, time limits (SoftTimeLimitExceeded), disk full...: not the
        # file's fault, so the same file is retried on the next run.
        logger.exception("GTFS %s/%s: import failed", version.city_id, version.feed_id)
        return _mark_failed(
            version, report, started, f"{type(exc).__name__}: {exc}", data_error=False
        )

    # Post-commit housekeeping must not turn a successful import into a failure.
    try:
        _analyze()
        cleanup_feed(version.city_id, version.feed_id)
    except Exception:
        logger.exception(
            "GTFS %s/%s: cleanup after import failed", version.city_id, version.feed_id
        )
    counts = report.counts
    message = (
        f"version {version.pk}: {counts.get('stops', 0)} stops,"
        f" {counts.get('trips', 0)} trips, {counts.get('stop_times', 0)} stop times"
        f" in {version.duration_ms / 1000:.1f} s"
    )
    return ImportResult(
        version.city_id, version.feed_id, Outcome.IMPORTED, message, version.pk, version.report
    )


def _mark_failed(
    version: FeedVersion, report: ImportReport, started: float, error: str, data_error: bool
) -> ImportResult:
    """Store the failure on the version row. Never raises: a broken database connection
    here must not hide the original error (which the caller has already logged)."""
    # The in-memory instance may carry feed_info values from the rolled-back load; that
    # is fine, they describe the rejected file.
    report.timings_s["total"] = time.monotonic() - started
    version.status = FeedVersion.Status.FAILED
    version.error = error[:5000]
    version.data_error = data_error
    version.duration_ms = int((time.monotonic() - started) * 1000)
    version.report = report.as_dict()
    if not _save_failed(version):
        # Left as 'importing'; the next run marks it failed ("import interrupted").
        logger.error(
            "GTFS %s/%s: could not store failed version %s",
            version.city_id,
            version.feed_id,
            version.pk,
        )
    else:
        try:
            cleanup_feed(version.city_id, version.feed_id)
        except Exception:
            logger.exception("GTFS %s/%s: cleanup failed", version.city_id, version.feed_id)
    return ImportResult(
        version.city_id, version.feed_id, Outcome.FAILED, error, version.pk, version.report
    )


def _save_failed(version: FeedVersion) -> bool:
    """Save a failed version; on a database error reconnect once and retry."""
    for attempt in (1, 2):
        try:
            version.save()
            return True
        except Exception:
            logger.exception(
                "GTFS %s/%s: saving failed version %s (attempt %s)",
                version.city_id,
                version.feed_id,
                version.pk,
                attempt,
            )
            if attempt == 1 and not connection.in_atomic_block:
                # A dead connection (server restart, OOM kill) cannot be reused; Django
                # opens a new one on the next query. Inside an outer transaction (tests)
                # closing would break that transaction, so only retry as is.
                # Closing also releases the session advisory lock: harmless, the import
                # is already over and the failed row is the last write of this run.
                connection.close()
    return False


def _record_failure(city: City, feed: Feed, source_url: str, now, error: str) -> FeedVersion:
    version = FeedVersion.objects.create(
        city_id=city.id,
        feed_id=feed.id,
        status=FeedVersion.Status.FAILED,
        source_url=source_url or "",
        downloaded_at=now,
        checked_at=now,
        error=error[:5000],
    )
    cleanup_feed(city.id, feed.id)
    return version


def _fail_interrupted(city_id: str, feed_id: str) -> None:
    """Versions still 'importing' while we hold the lock belong to a dead process.

    ``data_error`` stays False, so the same file is retried.
    """
    FeedVersion.objects.filter(
        city_id=city_id, feed_id=feed_id, status=FeedVersion.Status.IMPORTING
    ).update(status=FeedVersion.Status.FAILED, error="import interrupted", data_error=False)


# ------------------------------------------------------------------ cleanup


# Child tables in deletion order. StopTime is deleted through its trips (its
# feed_version column is not indexed).
_PURGE_ORDER = (Frequency, Trip, Shape, CalendarDate, Calendar, Route, Stop, Agency)


def purge_feed_version(version_id: int) -> None:
    """Delete one feed version and all its rows with plain SQL (no ORM cascade)."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                "DELETE FROM {stop_time} WHERE trip_id IN"
                " (SELECT id FROM {trip} WHERE feed_version_id = %s)"
            ).format(
                stop_time=sql.Identifier(StopTime._meta.db_table),
                trip=sql.Identifier(Trip._meta.db_table),
            ),
            [version_id],
        )
        for model in _PURGE_ORDER:
            cursor.execute(
                sql.SQL("DELETE FROM {} WHERE feed_version_id = %s").format(
                    sql.Identifier(model._meta.db_table)
                ),
                [version_id],
            )
        cursor.execute(
            sql.SQL("DELETE FROM {} WHERE id = %s").format(
                sql.Identifier(FeedVersion._meta.db_table)
            ),
            [version_id],
        )


def cleanup_feed(city_id: str, feed_id: str) -> list[int]:
    """Keep the active version, the newest superseded one(s) and the newest failed rows.

    Returns the ids of the deleted versions.
    """
    versions = FeedVersion.objects.filter(city_id=city_id, feed_id=feed_id)
    superseded = list(
        versions.filter(status=FeedVersion.Status.SUPERSEDED)
        .order_by("-imported_at", "-pk")
        .values_list("pk", flat=True)
    )
    keep_failed = getattr(settings, "TRANSIT_GTFS_KEEP_FAILED", 5)
    failed = list(
        versions.filter(status=FeedVersion.Status.FAILED)
        .order_by("-created_at", "-pk")
        .values_list("pk", flat=True)
    )
    keep_superseded = getattr(settings, "TRANSIT_GTFS_KEEP_SUPERSEDED", 1)
    doomed = superseded[keep_superseded:] + failed[keep_failed:]
    for version_id in doomed:
        purge_feed_version(version_id)
    if doomed:
        logger.info("GTFS %s/%s: deleted old versions %s", city_id, feed_id, doomed)
    return doomed


def _analyze() -> None:
    """Refresh planner statistics after a bulk load (autovacuum would lag behind)."""
    with connection.cursor() as cursor:
        for model in (Stop, Route, Trip, StopTime, CalendarDate, Calendar, Shape, Frequency):
            cursor.execute(sql.SQL("ANALYZE {}").format(sql.Identifier(model._meta.db_table)))


# --------------------------------------------------------------------- lock


class _feed_lock:  # noqa: N801 - used as a context manager
    """Session-level PostgreSQL advisory lock for one (city, feed)."""

    def __init__(self, city_id: str, feed_id: str):
        digest = hashlib.sha256(f"gtfs-import:{city_id}:{feed_id}".encode()).digest()
        self.key = int.from_bytes(digest[:8], "big", signed=True)
        self.locked = False

    def __enter__(self) -> bool:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [self.key])
            self.locked = bool(cursor.fetchone()[0])
        return self.locked

    def __exit__(self, *exc) -> None:
        if not self.locked:
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [self.key])
        except Exception:
            # Never mask the original exception. A session lock dies with its connection,
            # so a broken connection has released it anyway.
            logger.exception("GTFS import: releasing advisory lock %s failed", self.key)
