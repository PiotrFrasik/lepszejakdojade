# lepszejakdojade

Public transport web app for Kraków and Warsaw. It is in early development: the foundation
(containers, API skeleton, frontend shell with a city picker, map and language switch) is in place.
A realtime collector for Kraków trip updates has started and stores data in the database.
Static GTFS timetables for Kraków and Warsaw are imported every night, and the timetable browser
shows them. Journey planning A→B is built on the home page. An AI chat assistant answers questions about
stops, journeys, departures and timetables. The stop view, tickets and live departures are planned.

Full product description: [docs/concept.md](docs/concept.md).
The app is bilingual (Polish / English) with a language switcher.

## Features

- **Timetable browser** (built, #10, #11): lines grouped by type, line diagram with a route map, stop
  timetables for weekdays, Saturdays and Sundays/holidays, and a trip view. Routes are in
  [Timetable browser](#timetable-browser).
- **Journey planning** (built, #12, #13): A→B on the home page with stop autocomplete, map picking,
  my location, depart or arrive time, preferences (fewer transfers, less walking, wheelchair), results with
  a route on the map, and walk and bike comparison. Routes are in [Journey planning](#journey-planning).
- **AI chat assistant** (built, #18, #19): a chat panel on every page and the `/assistant` page. Ask in
  Polish or English for stops, journeys, departures, lines and timetables. Answers come only from app data
  through six read-only tools. Journeys, departures and stops are shown as cards. Details are in
  [AI chat assistant](#ai-chat-assistant).
- **Planned:** live departures and vehicles (#20, #21), delay statistics and predictions (#22, #23),
  tickets (demo).

Screenshots and GIFs will be added when the first user-facing features are merged.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- [Node.js 22](https://nodejs.org/) on the host, only if you want to run frontend tools outside Docker
- Git

## Quick start

```bash
cp .env.example .env        # optional: compose has defaults for everything
docker compose up -d --build
```

| What | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API health | http://localhost:8000/api/v1/health/ |
| Swagger UI (OpenAPI) | http://localhost:8000/api/docs/ |

Stop the stack with `docker compose down`.

### OpenTripPlanner graphs

OpenTripPlanner (OTP) is the journey engine. It runs one instance per city, and each instance serves
one graph built from that city's timetables and map. OTP is not started by `docker compose up`.
Journey search (#12) calls the city's OTP instance. With no OTP service running, the journey search
returns an error (503).

Build a city's graph, then start its service:

```bash
make otp-build CITY=krakow    # prepare inputs, build the graph, restart the service if it is running
make otp-up CITY=krakow       # start the city's OTP service
make otp-down CITY=krakow     # stop it
```

`CITY` is `krakow` or `warszawa`. Build one city at a time. The Makefile needs a POSIX shell:
Linux, macOS, or Git Bash on Windows.

Debug UI, once a service is running: Kraków http://localhost:8080, Warsaw http://localhost:8081.
The ports are set with `OTP_KRAKOW_PORT` and `OTP_WARSZAWA_PORT`.

Without `make`, run the same three steps by hand. Replace `krakow` with `warszawa` for Warsaw.
Create the directory first (`mkdir -p` works in Git Bash and Linux):

```bash
mkdir -p otp/data/krakow
docker compose run --rm --user "$(id -u):$(id -g)" backend python manage.py prepare_otp_inputs --city krakow
docker compose --profile otp-build run --rm otp-build-krakow
docker compose --profile otp up -d otp-krakow
```

- `--user "$(id -u):$(id -g)"` is needed on Linux, so the files are not written as root. In
  PowerShell there is no `id`; leave `--user` out there.
- If the service is already running, restart it after a build:
  `docker compose --profile otp restart otp-krakow`.

Notes:

- The first prepare downloads the city's GTFS feeds and the regional OSM extract (Geofabrik). It
  needs network access. Later runs download only what changed.
- The OSM extract is clipped with `osmium-tool`. It is installed in the backend image; nothing to
  install on the host.
- Memory: measured on Docker with 12 GB and 8 CPUs. The Warsaw build peaked at 7.4 GB RSS, the
  Kraków build at 3.5 GB.
- The graph does not update itself. Rebuild after a feed changes (manual for now, see
  [docs/decisions.md](docs/decisions.md), entry 17).
- Details, settings and the layout of `otp/data/` are in [docs/architecture.md](docs/architecture.md)
  and [otp/README.md](otp/README.md).

### Gemini API key

The AI assistant needs a Google Gemini API key. Without it, the chat returns `503` and the rest of the app works.

1. Open [Google AI Studio](https://aistudio.google.com/app/apikey) and create an API key.
2. Put it in `.env` as `GEMINI_API_KEY=...`.
3. Optional: set `GEMINI_MODEL` (default `gemini-flash-latest`).

The free Gemini tier may let Google use prompts to improve its products. Do not type personal data into the chat.
The assistant variables are not yet listed in `docker-compose.yml` or `.env.example` (follow-up).

Never commit `.env`. It is listed in `.gitignore`.

## Cities

City configuration lives in `backend/cities/config/<id>.yaml`, one file per city.

- Adding a city means adding a file. No code change is needed.
- Files are validated strictly at startup. A broken file stops `runserver`, `migrate` and every
  management command. The error names the file and the field.
- Optional: set `CITY_CONFIG_DIR` in `.env` to load city files from another directory.
- Public fields are exposed via `GET /api/v1/cities/`. Internal fields (feeds, ticket zones,
  attributions) are not exposed.
- A `gtfs_static` feed can have an optional `filter` (`bbox`, `exclude_agencies`). The import cuts
  the feed to the city's area. See [docs/architecture.md](docs/architecture.md).
- `line_group_rules` (internal, not returned by the API) sets the line groups of the timetable browser.
  Each rule has `vehicle_types`, `feeds` and a `short_name` regex that maps to a group. The first
  matching rule wins; a line with no match goes to the first group.

## Realtime data collector

A Celery beat task, `transit_data.collect_trip_updates`, polls the GTFS-Realtime trip update
feeds of each city every `REALTIME_POLL_INTERVAL_SECONDS` (default 30). It runs in the
`celery-worker` and `celery-beat` services, so `docker compose up -d` starts it.

- Feeds come from each city's `gtfs_rt` list in its config file, where `entity: trip_updates`.
  For Kraków these are `ztp_tram_trip_updates`, `ztp_bus_trip_updates` and the Mobilis agglomeration
  bus feed (added in #38).
- Every poll writes one `FeedFetch` row per feed (status, error, skipped count). Stop visits go to
  `StopEvent`, one row per trip and stop.
- Check the data in the Django admin at http://localhost:8000/admin/. Create a login first:
  `docker compose exec backend python manage.py createsuperuser`. Both models are read-only there.
- Run one poll by hand, or several, with the management command:

  ```bash
  docker compose exec backend python manage.py collect_trip_updates --city krakow
  docker compose exec backend python manage.py collect_trip_updates --city krakow --feed ztp_bus_trip_updates
  docker compose exec backend python manage.py collect_trip_updates --loop 30 --count 10
  docker compose exec backend python manage.py collect_trip_updates --dump-dir /tmp/feeds
  ```

  `--dump-dir` saves each downloaded feed as a `.pb` file, for tests.
- Optional Django settings with their defaults: `TRANSIT_REALTIME_HTTP_TIMEOUT` (10 s),
  `TRANSIT_REALTIME_STALE_AFTER` (300 s), `TRANSIT_REALTIME_MAX_BYTES` (20 MB). They are not in
  `.env.example`; set them in the settings file if needed.

What the data looks like and what is missing is in [docs/architecture.md](docs/architecture.md).
Short version: tram messages have no delays. The static GTFS import (#7) is built, but the
collector does not use it yet. Raw events are meant to be kept for 60 days; the deletion job comes
with #22 and is not built yet.

## Static timetables (GTFS)

A nightly Celery beat task, `transit_data.import_all_gtfs`, imports the `gtfs_static` feeds of each
city at `GTFS_IMPORT_HOUR`:`GTFS_IMPORT_MINUTE` (default 03:30, Europe/Warsaw; both in `.env.example`).

- Kraków: ZTP tram and bus feeds, and national rail (`rail`). Warsaw: mkuran.pl feeds for ZTM Warszawa
  and WKD, and national rail (`rail`).
- The national rail feed is one file for both cities (mkuran.pl "Polish Trains"). Each city's import
  cuts it to the city's area. Warsaw leaves out SKM, which the ZTM feed already has (#43).
- Each import creates a new version. The active version stays in use until the new one has loaded
  completely.
- Run an import by hand:

  ```bash
  docker compose exec backend python manage.py import_gtfs krakow
  docker compose exec backend python manage.py import_gtfs krakow --feed ztp_tram --force
  docker compose exec backend python manage.py import_gtfs krakow --feed ztp_tram --file transit_data/fixtures/gtfs/minimal
  docker compose exec backend python manage.py import_gtfs warszawa --feed rail
  ```

  `--feed` limits the run to one feed. `--force` bypasses the size check (a new version with less
  than 50% of the active trips or stop times is otherwise rejected). `--file` reads a local GTFS
  zip or directory instead of downloading; it requires `--feed`. The command exits with status 1 when a feed failed.
- Optional Django settings with their defaults: `TRANSIT_GTFS_HTTP_TIMEOUT` (120 s),
  `TRANSIT_GTFS_MAX_BYTES` (1 GB), `TRANSIT_GTFS_MAX_UNCOMPRESSED_BYTES` (5 GB),
  `TRANSIT_GTFS_DOWNLOAD_MAX_SECONDS` (900 s), `TRANSIT_GTFS_MAX_SKIPPED_RATIO` (0.05),
  `TRANSIT_GTFS_MIN_SHARE_OF_ACTIVE` (0.5), `TRANSIT_GTFS_EXPIRY_WARNING_DAYS` (14),
  `TRANSIT_GTFS_KEEP_SUPERSEDED` (1), `TRANSIT_GTFS_KEEP_FAILED` (5). They are not in
  `.env.example`; set them in the settings file if needed.

Retention, sizes and the import rules are in [docs/architecture.md](docs/architecture.md). Licences
and attribution of each source are in [docs/decisions.md](docs/decisions.md), entries 13 and 19.

## Timetable browser

Built on the active static GTFS versions (see [Static timetables](#static-timetables-gtfs)). No login.

- Pages: `/timetable` (lines), `/timetable/lines/:lineId` (line diagram and route map),
  `/timetable/lines/:lineId/stops/:stopId` (stop timetable). The city is not in the URL; it comes from
  the city picker.
- API (read-only): `GET /api/v1/cities/{city}/lines/`, `.../lines/{line_id}/route/`,
  `.../lines/{line_id}/stops/{stop_id}/timetable/`, `GET /api/v1/cities/{city}/trips/{trip_id}/`.
  Contract: [docs/api.md](docs/api.md#timetable-10).
- Backend app: `backend/timetable/`. Frontend: `frontend/src/views/timetable/`.

## Journey planning

Built on the OTP graphs (see [OpenTripPlanner graphs](#opentripplanner-graphs)). No login.

- Page: `/` (home, full-screen map with the journey panel). `/journey` redirects to `/`.
- API: `GET /api/v1/cities/{city}/stops/?q=` (stop search, #59) and
  `POST /api/v1/cities/{city}/journeys/search/` (#12). Contract: [docs/api.md](docs/api.md#journeys-12-and-stop-search-59).
- Backend apps: `backend/journeys/` (OTP client, itineraries) and `backend/timetable/stops.py` (stop search).
  Frontend: `frontend/src/components/journey/`, `frontend/src/stores/journey.ts`.
- Flow and rules: [docs/architecture.md](docs/architecture.md#journey-search-implemented-12-13).

## AI chat assistant

The assistant is the `assistant` Django app (`POST /api/v1/assistant/chat/`) and the chat UI in the frontend.

- **Provider.** Gemini is behind a provider interface. The Gemini provider calls the REST API with `urllib`
  (no SDK). Key from `GEMINI_API_KEY`, model from `GEMINI_MODEL`. See [Gemini API key](#gemini-api-key).
- **Tools.** The model can call six read-only tools: `search_stops`, `plan_journey`, `next_departures`,
  `list_lines`, `get_line_route` and `get_stop_timetable`. They use the same services as the public endpoints.
  The model answers only from tool results. Tickets and live data are not available yet, and the assistant says so.
- **No stored chats.** The API keeps no state. The browser keeps the conversation in `sessionStorage` and sends
  the last 20 messages with each request.
- **Language.** The answer uses the `Accept-Language` language, whatever language the question is in.
- **Cards.** Journey, departure and stop cards are built by the server from tool results only.
- **Limits.** 10 requests per minute and 100 per day per client IP (settings and env). Counters are kept in
  local memory.
- **Safety.** Tools are read-only, the city is fixed by the request, tool arguments are capped, and a canary
  checks that the system prompt does not leak.
- **Development.** Without a key, set `VITE_ASSISTANT_MOCK=true` for the frontend. The mock works in development
  builds only.

Contract: [docs/api.md](docs/api.md#assistant-18). Design: [docs/architecture.md](docs/architecture.md#ai-chat-assistant-implemented-18-19).

## Tests

```bash
docker compose exec backend pytest -q     # backend (pytest)
cd frontend && npm run test               # frontend (Vitest), needs Node 22 on the host
```

## Continuous integration

GitHub Actions runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml) on every push to `main`
and on every pull request. Both jobs run on `ubuntu-24.04`.

- **Backend** (Python 3.12, PostGIS 16 and Redis 7 as service containers):
  `ruff check .`, `ruff format --check .`, `python manage.py makemigrations --check --dry-run`,
  `pytest`. The JUnit report is uploaded as the `backend-test-report` artifact.
- **Frontend** (Node 22): `npm ci`, `npm run lint`, `npm run type-check`, `npm test` (Vitest,
  including the pl/en locale key parity test), `npm run build`.

To run the same checks locally, use the same commands from `backend/` and `frontend/`. The
`env:` block in `ci.yml` lists the variables the backend job sets. The CI values are dummy values,
not secrets.

## Windows notes

- `make` is usually not installed on Windows. The Makefile targets are thin wrappers over
  `docker compose`; you can run the commands from the Makefile directly.
- If you change `POSTGRES_PASSWORD` after the first run, the database keeps the old password.
  Recreate the dev database with `docker compose down -v` (this deletes its data).
- After changes to `frontend/package.json`, rebuild the frontend image without its volume:
  `docker compose up -d --build -V`.
- An old `backend/.pytest_cache` directory owned by root (created by earlier container runs)
  can be deleted from the host.
- If Windows blocks port 5432 on the host, set
  `DB_PORT=55432` in `.env` and run `docker compose up -d` again. Only the host port changes; the
  containers still use 5432 inside the Docker network.

## Known limitations

- Map tiles are loaded directly from `tile.openstreetmap.org`. This follows the OSM tile usage
  policy and is fine for development, but not for production traffic. A tile provider must be
  chosen before deployment.
- The realtime collector runs only while the local stack is up. Continuous collection needs a
  server; hosting is not decided yet.
- Warsaw's timetable comes from the mkuran.pl community feed, maintained by one person. The importer
  keeps the last good version; the official ZTM feed is the fallback (see `docs/decisions.md`, entry 12).
  The national rail feed comes from the same source and has the same risk.
- National rail has static timetables only. There is no realtime data for it yet.
- Timetable browser: frequency-based trips show the template trip's times in the trip view. The stop
  entry (a stop page without a line) and the departures board are planned (#9, #56).
- Journey planning: there is no address search. Points are stops, map picks or my location (#13).
- Journey planning: no rate limit yet. It is needed before public deployment.
- Journey planning: the results show times without a date when the trip is on another day. The wheelchair
  preference does not exclude inaccessible trips.
- Journey planning: journeys use the timetable graph only. Realtime delays are not in the journey results.
- OTP graphs are rebuilt by hand. A graph built before the rail feed was added has no national rail
  until it is rebuilt. Graphs have no bicycle transfers (`docs/decisions.md`, entry 16) and no
  realtime updates.
- Attributions required by the data licences are not shown in the app yet (#25).
- AI assistant: the rate limit uses the connection IP and no proxy setting (`NUM_PROXIES`), and counters are
  in local memory per process. A shared Redis cache is a follow-up.
- AI assistant: a blocked prompt returns `503`. A normal answer is a follow-up.
- AI assistant: the provider timeout (30 s) is not a hard limit for the whole tool loop.
- AI assistant: the chat history is kept only in the browser. It is not saved on the server.

## Repository layout

```
backend/     Django API, Celery worker and beat (config/, core/, cities/, transit_data/, timetable/, journeys/, assistant/)
frontend/    Vue 3 + TypeScript + Vite app
otp/         OpenTripPlanner config and graph data
docs/        concept, API contract, architecture, decisions, AI workflow log
docker-compose.yml, Makefile, .env.example
```

## Documentation

- [docs/concept.md](docs/concept.md): product concept
- [docs/api.md](docs/api.md): API contract (the live Swagger UI is linked above)
- [docs/architecture.md](docs/architecture.md): services, data flow and retention
- [docs/data-sources.md](docs/data-sources.md) (planned, #25): feeds, licences and attribution
- [docs/backlog.md](docs/backlog.md): planned work
- [docs/decisions.md](docs/decisions.md): short decision records
- [docs/ai-workflow/log.md](docs/ai-workflow/log.md): log of features built with AI agents
- `docs/ai-workflow/README.md` (planned): how the app is built with AI agents

## License

See [LICENSE](LICENSE).
