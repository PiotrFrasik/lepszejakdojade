"""Poll GTFS-RT TripUpdates feeds once (or in a loop) without Celery.

Examples:
    python manage.py collect_trip_updates
    python manage.py collect_trip_updates --city krakow --feed ztp_tram_trip_updates
    python manage.py collect_trip_updates --loop 30 --count 10
    python manage.py collect_trip_updates --dump-dir /tmp/feeds   # also save raw .pb files
"""

import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from cities.registry import get_city
from transit_data.realtime import collect_all_trip_updates, trip_update_feeds


class Command(BaseCommand):
    help = "Poll GTFS-Realtime TripUpdates feeds from city config and store stop events."

    def add_arguments(self, parser):
        parser.add_argument("--city", help="Only this city id.")
        parser.add_argument("--feed", help="Only this feed id.")
        parser.add_argument(
            "--loop", type=float, metavar="SECONDS", help="Repeat with this interval."
        )
        parser.add_argument(
            "--count", type=int, default=0, help="Number of polls with --loop (0 = forever)."
        )
        parser.add_argument(
            "--dump-dir", type=Path, help="Save each downloaded feed as a .pb file here."
        )

    def handle(self, *args, **options):
        feeds = [
            (city, feed)
            for city, feed in trip_update_feeds()
            if (not options["city"] or city.id == options["city"])
            and (not options["feed"] or feed.id == options["feed"])
        ]
        if not feeds:
            raise CommandError("No matching TripUpdates feeds in city config.")

        polls = 0
        while True:
            for log in collect_all_trip_updates(
                city_id=options["city"], feed_id=options["feed"], dump_dir=options["dump_dir"]
            ):
                self.stdout.write(
                    f"{log.fetched_at.astimezone(get_city(log.city_id).zoneinfo):%H:%M:%S}"
                    f" {log.city_id}/{log.feed_id}: {log.status}"
                    f" entities={log.entity_count} stop_events={log.stop_event_count}"
                    f" bytes={log.size_bytes} {log.duration_ms} ms"
                    + (f" error={log.error}" if log.error else "")
                )
            polls += 1
            if not options["loop"] or (options["count"] and polls >= options["count"]):
                break
            time.sleep(options["loop"])
