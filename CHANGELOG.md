# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Entries are written from Conventional Commit messages.

## [Unreleased]

### Added

- Static GTFS import (#7): `FeedVersion`, `Agency`, `Stop`, `Route`, `Calendar`, `CalendarDate`,
  `Shape`, `Trip`, `StopTime` and `Frequency` models in `transit_data`. Each import is a new version
  loaded with PostgreSQL `COPY` and switched to active in one transaction. Includes the
  `import_gtfs` management command, the nightly Celery beat task `transit_data.import_all_gtfs`
  (`GTFS_IMPORT_HOUR` and `GTFS_IMPORT_MINUTE`), size and bad-row checks, an import report, and
  read-only admin.
- Feed sources (#38): Kraków Mobilis agglomeration bus feeds (static and GTFS-RT, the collector
  polls its TripUpdates), optional `licence_url` on city attributions, OpenStreetMap attribution for
  both cities, and `UM_WARSZAWA_API_KEY` in `.env.example` and `docker-compose.yml` (empty, used by
  #20). Feed URLs were checked live; licences are listed in `docs/decisions.md`.
- Polish and English support (#28, #30): `Accept-Language` negotiation with `Content-Language` on every
  response, translated API errors (`error.code` stays untranslated), translated database content via
  django-modeltranslation, browser language detection, and locale-aware dates, times and numbers in the
  city's timezone.
- Realtime collector for Kraków trip updates (#6): new `transit_data` app, Celery beat task
  `transit_data.collect_trip_updates` every `REALTIME_POLL_INTERVAL_SECONDS` (default 30),
  `StopEvent` and `FeedFetch` models, read-only admin, and the `collect_trip_updates` management
  command.
- Bad values in a realtime feed skip only the affected entity or stop update, not the whole poll.
- `REALTIME_POLL_INTERVAL_SECONDS` in `.env.example` and `docker-compose.yml`.
- `gtfs-realtime-bindings` and `protobuf` backend dependencies.
