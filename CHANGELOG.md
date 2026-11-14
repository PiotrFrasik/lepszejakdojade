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
- OpenTripPlanner graphs for Kraków and Warsaw (#8): one OTP 2.6 service per city (`otp-krakow`,
  `otp-warszawa`, profile `otp`, ports 8080 and 8081 on 127.0.0.1), one-shot build services (profile
  `otp-build`), and the `prepare_otp_inputs` management command. It downloads the city's static GTFS
  feeds and the Geofabrik regional OSM extract, and clips the extract with `osmium-tool` to the GTFS
  stops plus 3 km. Downloads are conditional and atomic; a per-city lock and `prepare-report.json`
  are included.
- Shared OTP config in `otp/config/`, with optional per-city overrides in `otp/<city>/`.
- Makefile targets `otp-build`, `otp-up` and `otp-down`, each with `CITY=krakow|warszawa`.
- City config: internal `otp` section (`osm_url`, optional `bbox`), validated at startup and not
  exposed by the API (#46).
- `cities.registry.get_otp_url(city)` and the settings `OTP_DATA_DIR`, `OTP_CONFIG_DIR`,
  `OTP_OSMIUM_BIN`, `OTP_BBOX_BUFFER_KM`, `OTP_OSM_MAX_BYTES`, `OTP_OSM_DOWNLOAD_MAX_SECONDS`, and the
  per-city heap and port settings (#46, #47).
- `osmium-tool` in the backend image (#47).

### Changed

- `OTP_URL` is replaced by `OTP_URL_KRAKOW` and `OTP_URL_WARSZAWA`, one per city.
- Celery worker and beat mount `./otp` read-only; the backend mounts it read-write (#47).
