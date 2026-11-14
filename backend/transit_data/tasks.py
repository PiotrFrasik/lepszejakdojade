"""Celery tasks of the transit_data app.

``collect_trip_updates`` is scheduled by Celery beat (``CELERY_BEAT_SCHEDULE`` in
settings, interval ``REALTIME_POLL_INTERVAL_SECONDS``, about 30 s).
``import_all_gtfs`` is meant to run nightly; it queues ``import_city_gtfs`` per city.
"""

import logging

from celery import shared_task

from cities.registry import all_cities

from .realtime import collect_all_trip_updates
from .static_gtfs.pipeline import import_city

logger = logging.getLogger(__name__)


@shared_task(name="transit_data.collect_trip_updates", ignore_result=True)
def collect_trip_updates() -> None:
    """Poll all configured GTFS-RT TripUpdates feeds and store stop events.

    Failures are logged and recorded as FeedFetch rows; the task itself does not fail,
    so one broken feed never blocks the others or triggers retries that pile up.
    """
    collect_all_trip_updates()


# A large feed (millions of stop times) takes minutes to import; never let a hung download
# or import hold a worker forever.
GTFS_IMPORT_SOFT_TIME_LIMIT = 60 * 60
GTFS_IMPORT_TIME_LIMIT = GTFS_IMPORT_SOFT_TIME_LIMIT + 5 * 60


@shared_task(
    name="transit_data.import_city_gtfs",
    soft_time_limit=GTFS_IMPORT_SOFT_TIME_LIMIT,
    time_limit=GTFS_IMPORT_TIME_LIMIT,
)
def import_city_gtfs(city_id: str, force: bool = False) -> list[dict]:
    """Download and import every static GTFS feed of one city.

    Feeds without a URL are skipped; a failed feed keeps its previous active version and
    does not stop the other feeds. Returns one summary dict per feed.
    """
    results = [result.as_dict() for result in import_city(city_id, force=force)]
    logger.info("GTFS import %s: %s", city_id, [(r["feed_id"], r["outcome"]) for r in results])
    return results


@shared_task(name="transit_data.import_all_gtfs", ignore_result=True)
def import_all_gtfs() -> None:
    """Queue ``import_city_gtfs`` for every configured city (for the nightly schedule)."""
    for city in all_cities():
        import_city_gtfs.delay(city.id)
