"""Static GTFS import: download, validate and bulk load feeds from city config.

Modules:
- ``download``: conditional HTTP download to a temporary file, sha256.
- ``reader``: stream rows from a GTFS zip (or directory) with the csv module.
- ``report``: per-file counts, skipped rows with reasons, warnings.
- ``loader``: parse, validate and COPY rows into the database for one FeedVersion.
- ``pipeline``: one feed end to end (lock, download, import, activate, clean up).

Entry points: ``pipeline.import_city`` / ``pipeline.import_feed``, the management command
``import_gtfs`` and the Celery task ``transit_data.import_city_gtfs``.
"""
