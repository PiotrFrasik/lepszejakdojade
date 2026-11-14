"""Celery tasks of the transit_data app.

``collect_trip_updates`` is scheduled by Celery beat (``CELERY_BEAT_SCHEDULE`` in
settings, interval ``REALTIME_POLL_INTERVAL_SECONDS``, about 30 s).
"""

from celery import shared_task

from .realtime import collect_all_trip_updates


@shared_task(name="transit_data.collect_trip_updates", ignore_result=True)
def collect_trip_updates() -> None:
    """Poll all configured GTFS-RT TripUpdates feeds and store stop events.

    Failures are logged and recorded as FeedFetch rows; the task itself does not fail,
    so one broken feed never blocks the others or triggers retries that pile up.
    """
    collect_all_trip_updates()
