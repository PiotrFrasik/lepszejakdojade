"""Download and import the static GTFS feeds of one city.

Examples:
    python manage.py import_gtfs krakow
    python manage.py import_gtfs krakow --feed ztp_tram --force
    python manage.py import_gtfs krakow --feed ztp_tram --file transit_data/fixtures/gtfs/minimal

Exit status is 1 when any feed failed (skipped, unchanged and busy feeds are not errors).
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from transit_data.static_gtfs.pipeline import ImportConfigError, Outcome, import_city
from transit_data.static_gtfs.report import format_report


class Command(BaseCommand):
    help = "Download and import static GTFS feeds of a city from city config."

    def add_arguments(self, parser):
        parser.add_argument("city", help="City id, e.g. krakow.")
        parser.add_argument("--feed", help="Only this static feed id.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Import even if the feed is unchanged (no conditional GET, no sha256 check).",
        )
        parser.add_argument(
            "--file",
            type=Path,
            help="Import a local GTFS zip or directory instead of downloading (needs --feed"
            " when the city has several static feeds).",
        )

    def handle(self, *args, **options):
        try:
            results = import_city(
                options["city"],
                feed_id=options["feed"],
                force=options["force"],
                file=options["file"],
            )
        except ImportConfigError as exc:
            raise CommandError(str(exc)) from exc

        failed = False
        for result in results:
            style = {
                Outcome.IMPORTED: self.style.SUCCESS,
                Outcome.FAILED: self.style.ERROR,
            }.get(result.outcome, self.style.WARNING)
            self.stdout.write(
                style(f"{result.city_id}/{result.feed_id}: {result.outcome}")
                + (f" - {result.message}" if result.message else "")
            )
            if result.outcome in (Outcome.IMPORTED, Outcome.FAILED):
                for line in format_report(result.report):
                    self.stdout.write(line)
            failed = failed or result.outcome == Outcome.FAILED
        if failed:
            raise CommandError("at least one feed failed to import", returncode=1)
