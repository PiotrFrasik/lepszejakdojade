# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Entries are written from Conventional Commit messages.

## [Unreleased]

### Added

- AI chat assistant (#18, #19): `POST /api/v1/assistant/chat/` in the new `assistant` app and a chat panel on every
  page with a `/assistant` page. Gemini sits behind a provider interface (REST over `urllib`, no SDK); the model is
  set by `GEMINI_MODEL` (default `gemini-flash-latest`) and the key by `GEMINI_API_KEY`. Six read-only tools use the
  timetable and journey services. The API is stateless; the client sends the last 20 messages. Answers use the
  `Accept-Language` language. Journey, departure and stop cards are built from tool results only. Per-IP throttling
  (10 per minute, 100 per day) is set in settings and env.
- Journey search API (#12): `POST /api/v1/cities/{city}/journeys/search/` in the new `journeys` app. It calls
  the city's OpenTripPlanner 2 instance through its GraphQL API (`/otp/gtfs/v1`, 10 s timeout). Returns up
  to 5 itineraries with legs, geometry, and walk and bike comparison. Preferences: fewer transfers, less
  walking, wheelchair (preferred, not excluded). Any OTP failure returns `503 journey_planner_unavailable`.
  Settings `OTP_TIMEOUT_SECONDS`, `JOURNEY_FEWER_TRANSFERS_COST`, `JOURNEY_LESS_WALKING_RELUCTANCE` and
  `JOURNEY_COMPARISON_MAX_DURATION`.
- Stop search API (#59): `GET /api/v1/cities/{city}/stops/?q=` in the `timetable` app. Matching ignores
  diacritics, platforms with the same name within 300 m are grouped, at most 20 results, cached for 24 h and
  keyed by the active feed versions.
- Journey search UI (#13): the home page `/` is a map with a journey panel (floating on desktop, top panel and
  bottom tab bar on phones). `/journey` redirects to `/`. Stop autocomplete, map picking, my location, swap,
  depart or arrive time in the city's timezone, preferences, results with a route on the map, and walk and
  bike comparison.
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
- National rail GTFS (#43): the mkuran.pl "Polish Trains" feed (`rail`) for both cities, cut to each
  city's area at import. Warsaw leaves out SKM, which the `ztm` feed already has.
- Optional `filter` on `gtfs_static` feeds in the city config: `bbox` and `exclude_agencies`. The
  import keeps trips with at least two calls in the box, cuts them to those calls, and drops unused
  routes, agencies, services and shapes.
- Stops without usable coordinates inherit the position of their nearest positioned parent. The
  import report counts them as corrections. Orphans are still skipped (#43).
- Attributions for PKP PLK, Mikołaj Kuranowski (Polish Trains GTFS) and Koleje Mazowieckie in both
  city configs (#43).
- Timetable browser and read-only API (#10, #11): `timetable` app with the lines, line route, stop
  timetable and trip endpoints, and frontend views under `/timetable` (pl and en).

### Changed

- `OTP_URL` is replaced by `OTP_URL_KRAKOW` and `OTP_URL_WARSZAWA`, one per city.
- Celery worker and beat mount `./otp` read-only; the backend mounts it read-write (#47).
- OTP input prep uses the cut feed for a `gtfs_static` feed with a `filter`, and caches the source
  and cut zips. The unpacked-size limit applies to the OTP path as well as the import (#43).
- The backend CI job installs `osmium-tool`, so the real OSM clip test runs instead of skipping (#53).
