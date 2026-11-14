"""Assemble the OpenTripPlanner input directory of one city: config, GTFS feeds, clipped OSM.

Examples:
    python manage.py prepare_otp_inputs --city krakow
    python manage.py prepare_otp_inputs --city warszawa --force
    python manage.py prepare_otp_inputs --city krakow --osm-file /data/malopolskie.osm.pbf

The result is ``<OTP_DATA_DIR>/<city>/``, ready for ``otp --build --save`` (see otp/README.md).
Exit status is 1 on error; download failures that kept a previous file are warnings.
"""

import shlex
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from transit_data.otp_inputs import BBox, OsmiumNotFound, PrepareError, prepare_city


class Command(BaseCommand):
    help = "Prepare the OpenTripPlanner graph build directory of a city from city config."

    def add_arguments(self, parser):
        parser.add_argument("--city", required=True, help="City id, e.g. krakow.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Download everything again (no conditional GET).",
        )
        parser.add_argument(
            "--no-clip",
            action="store_true",
            help="Use the whole regional OSM extract (no osmium-tool needed, more OTP heap).",
        )
        parser.add_argument(
            "--buffer-km",
            type=float,
            help="Buffer around the GTFS stops bbox (default: OTP_BBOX_BUFFER_KM or 3).",
        )
        parser.add_argument("--bbox", help="Override: min_lon,min_lat,max_lon,max_lat.")
        parser.add_argument("--osm-url", help="Override otp.osm_url from city config.")
        parser.add_argument(
            "--osm-file", type=Path, help="Use this local regional .osm.pbf instead of a URL."
        )

    def handle(self, *args, **options):
        try:
            bbox = BBox.parse(options["bbox"]) if options["bbox"] else None
            report = prepare_city(
                options["city"],
                force=options["force"],
                clip=not options["no_clip"],
                buffer_km=options["buffer_km"],
                osm_url=options["osm_url"],
                osm_file=options["osm_file"],
                bbox=bbox,
            )
        except OsmiumNotFound as exc:
            raise CommandError(
                f"{exc}. Install osmium-tool, run with --no-clip, or clip in another container:"
                f"\n  {shlex.join(exc.command)}\nthen run this command again."
            ) from exc
        except PrepareError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"OTP inputs for {report.city_id}: {report.directory}")
        for feed in report.feeds:
            size = feed.get("size_bytes")
            self.stdout.write(
                f"  gtfs {feed['id']}: {feed['status']}"
                + (f", {size / 1e6:.1f} MB" if size else "")
            )
        for feed_id in report.skipped_feeds:
            self.stdout.write(f"  gtfs {feed_id}: skipped (no URL in city config)")
        for name in report.removed_files:
            self.stdout.write(f"  removed stale {name}")
        osm = report.osm
        self.stdout.write(
            f"  osm {osm['file']}: {osm.get('status', osm['source'])}, "
            + (f"clipped to {osm['bbox']} ({osm['bbox_source']}), " if osm["clipped"] else "")
            + f"{osm['file_size_bytes'] / 1e6:.1f} MB"
        )
        for warning in report.warnings:
            self.stdout.write(self.style.WARNING(f"  warning: {warning}"))
        self.stdout.write(self.style.SUCCESS("ready for: otp --build --save"))
