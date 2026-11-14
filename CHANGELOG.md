# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Entries are written from Conventional Commit messages.

## [Unreleased]

### Added

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
