# lepszejakdojade

Public transport web app for Kraków and Warsaw. Plan a journey from A to B, browse timetables, see the
departures at a stop, look up tickets and ask an AI assistant. The app is bilingual (Polish / English) with a
language switcher. Journey search runs on OpenTripPlanner 2; the app has no routing code of its own.

It is a recruitment project, built with a team of Claude Code agents coordinated by one session. It is a demo,
not a commercial product. Product description: [docs/concept.md](docs/concept.md).

Screenshots and GIFs are not in the repository yet.

## What works

| Feature | Where in the app | Status |
|---|---|---|
| Journey search A→B with map, route, walk and bike comparison, preferences (#12, #13) | Home page `/` | built (Kraków graph; Warsaw after its graph is built) |
| Timetable browser: lines, line diagram, route map, stop timetables, trip view (#10, #11) | `/timetable` | built |
| Stop view: lines at the stop and departures board (#9, #56, #73, #74) | `/timetable/stops/:stopId`, from stop search on `/timetable` | built (live times for Kraków only) |
| AI chat assistant: Gemini with function calling, six read-only tools (#18, #19) | Chat panel on every page, `/assistant` | built (needs `GEMINI_API_KEY`) |
| Data sources page with licences and data age (#25, #29) | `/data-sources`; API `GET /api/v1/data-sources/` | built |
| Ticket catalogue per city (#14, #82) | `/tickets` | built (Warsaw prices unverified) |
| Ticket hint under journey results (#14, #82) | Journey results on `/` | partial: single and time tickets, first zone only (#83) |
| Polish / English switcher | Every page | built |
| Accounts, favourites and search history (#15) | — | not built |
| Demo checkout and QR demo tickets (#16, #17) | — | not built |
| Live vehicle map and service alerts (#20, #21) | — | not built |
| Warsaw realtime data (#20) | — | not built |
| Delay statistics and predictions (#22–#24) | — | not built |
| Nightly OTP graph rebuilds (#51) | — | not built |
| Nearby stop search and colloquial stop names (#77) | — | not built |

## Quick start

Needs [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose) and Git.
[Node.js 22](https://nodejs.org/) on the host is optional, for running frontend tools outside Docker.

```bash
cp .env.example .env                                              # optional; needed for the chat (see Gemini API key)
docker compose up -d --build
docker compose exec backend python manage.py import_gtfs krakow  # load the Kraków timetables
make otp-build CITY=krakow                                        # build the Kraków journey graph
make otp-up CITY=krakow                                           # start its OTP service
```

Without `make` (for example in PowerShell), run the manual steps in [OpenTripPlanner graphs](#opentripplanner-graphs).
Journey search returns an error until the Kraków OTP service is running.

| What | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API health | http://localhost:8000/api/v1/health/ |
| Swagger UI (OpenAPI) | http://localhost:8000/api/docs/ |
| Django admin | http://localhost:8000/admin/ (create a login first: `docker compose exec backend python manage.py createsuperuser`) |

Stop the stack with `docker compose down`. If a local PostgreSQL already uses port 5432, set `DB_PORT`
in `.env` (for example `DB_PORT=55432`) and run `docker compose up -d` again. See [Windows notes](#windows-notes).

Warsaw works the same way: `import_gtfs warszawa`, then `make otp-build CITY=warszawa` (peak memory about 7.4 GB).

## Demo walkthrough

About 5 minutes, after the quick start above.

1. Open http://localhost:5173 and pick **Kraków** in the city picker.
2. On the home page, search from **Rondo Mogilskie** to **Bagatela**. Check the route on the map and the walk and bike comparison.
3. Open **Timetable** (`/timetable`), pick a line, then a stop. Compare the weekday, Saturday and Sunday columns.
4. Search for **Rondo Mogilskie** on `/timetable` and open the stop. Live times show when the Kraków realtime collector has data; otherwise the board shows the timetable.
5. Open **Tickets** (`/tickets`). Then go back to a journey result to see the ticket hint.
6. Open the chat (or `/assistant`) and ask "When is the next tram from Teatr Bagatela?" (or in Polish "Kiedy najbliższy tramwaj z Teatru Bagatela?"). The answer comes from timetable data and shows a departures card. Needs the Gemini key; the free tier allows about 15 model requests per minute, and one question can use several, so wait a minute if the assistant says it is unavailable.
7. Switch the language with the PL / EN switcher and check that the interface changes.

## Known limitations

- **Warsaw ticket prices are unverified.** They come from memory; the official sites block automated checks.
- **The ticket hint assumes the first zone** (#83) and considers single and time tickets only.
- **Warsaw has no journey graph or realtime data** unless you build the graph. Its timetable comes from one community feed (mkuran.pl).
- **Delay predictions are not built.** They need weeks of collected data (#22–#24).
- **Realtime collection runs only while the local stack is up.** Hosting is not decided.
- **Demo, not a commercial product.** No accounts, no purchase, no production hosting. Map tiles come from the OpenStreetMap public server, which is for development only.

Full list: [Detailed limitations](#detailed-limitations).

## How it was built

The app was built with Claude Code agents, coordinated by one session. The coordinator plans, delegates and
reports. It writes no application code.

| Agent | Owns |
|---|---|
| coordinator | Plans each feature, writes the API contract, creates issues and branches |
| backend | Django API in `backend/` (except the two areas below) |
| data | GTFS import, realtime collector, OTP graphs (`backend/transit_data/`, `otp/`) |
| ai | Gemini chat, tools and rate limits (`backend/assistant/`) |
| frontend | Vue 3 app (`frontend/`) |
| tester | Backend and frontend tests, end-to-end tests |
| reviewer | Reviews each branch before Piotr's manual test |
| docs | README, `docs/`, changelog |
| devops | Docker, CI, Makefile, `.env.example`, commits and pull requests |

- **Contract first.** An endpoint is written in [docs/api.md](docs/api.md) before backend and frontend start.
- **One issue, one branch, one PR.** Code agents work in parallel, each in its own git worktree. Piotr approves every commit and merges the PRs.
- **Gates.** Tests, then review (at most two fix rounds), then Piotr's manual test before any commit.
- **Path guard.** A hook blocks each agent from editing outside its area.
- **Usage limits.** The agents share one plan allowance, so at most two code agents run at once.

In numbers: 28 starter backlog items ([docs/backlog.md](docs/backlog.md)), 15 feature entries in the log, PRs up to #85.

Read more: the [AI workflow log](docs/ai-workflow/log.md) (per feature: agent reports, review findings and
manual-test feedback) and the [decision records](docs/decisions.md) (40 entries).

## Setup details

Details for the steps in the quick start.

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
`GEMINI_MODEL` is not yet listed in `.env.example` (follow-up).

Never commit `.env`. It is listed in `.gitignore`.

## Cities

City configuration lives in `backend/cities/config/<id>.yaml`, one file per city.

- Adding a city means adding a file. No code change is needed.
- Files are validated strictly at startup. A broken file stops `runserver`, `migrate` and every
  management command. The error names the file and the field.
- Optional: set `CITY_CONFIG_DIR` in `.env` to load city files from another directory.
- Public fields are exposed via `GET /api/v1/cities/`. Internal fields (feeds, ticket zones) are not
  exposed. Attributions are served by `GET /api/v1/data-sources/`.
- A `gtfs_static` feed can have an optional `filter` (`bbox`, `exclude_agencies`). The import cuts
  the feed to the city's area. See [docs/architecture.md](docs/architecture.md).
- `line_group_rules` (internal, not returned by the API) sets the line groups of the timetable browser.
  Each rule has `vehicle_types`, `feeds` and a `short_name` regex that maps to a group. The first
  matching rule wins; a line with no match goes to the first group.
- `static_feed` (on a `gtfs_rt` feed with entity `trip_updates`) names the `gtfs_static` feed that the realtime
  feed's trip ids belong to. It is required on every such feed when `realtime.departures` is true; the app
  does not start without it. See [Live departures](#live-departures).

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
Short version: tram messages have no delays. The collector stores what the feeds say; the departures
board joins it with the static GTFS import (#7) at request time. Raw events are meant to be kept for 60 days; the deletion job comes
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

## Live departures

The departures board shows the next departures of a stop group in Kraków and, without live data, in Warsaw.
No login.

- Page: `/timetable/stops/:stopId`, the stop view. Open it from stop search on `/timetable` or from a stop timetable.
- API (read-only): `GET /api/v1/cities/{city}/stops/{stop_id}/departures/?limit=`. Contract:
  [docs/api.md](docs/api.md#departures-73).
- Backend: `backend/timetable/departures.py`. Frontend: `StopDeparturesView`, `DepartureRow`, `useStopDepartures`
  and `utils/departures.ts`.
- The board refreshes 30 s after the previous response and pauses when the tab is hidden. After 5 min without a
  successful refresh it shows the timetable only.
- Development only: `VITE_DEPARTURES_MOCK=true` replaces the API with a mock on the dev server. It is never in
  production builds.
- Rules and the data flow are in [docs/architecture.md](docs/architecture.md#live-departures-implemented-73-74).

## Stop view

The stop view is the departures board at `/timetable/stops/:stopId` with a "Lines at this stop" list below it.
Each line links to its timetable at this stop in each direction. No login.

- API (read-only): `GET /api/v1/cities/{city}/stops/{stop_id}/`. Contract: [docs/api.md](docs/api.md#stop-overview-9).
- Backend: `backend/timetable/overview.py`. Frontend: `StopLines.vue` and `useStopOverview.ts`.
- The two requests load in parallel and fail on their own. If both return 404, the page shows "stop not found".
- Rules and the data flow are in [docs/architecture.md](docs/architecture.md#stop-overview-implemented-9-56).

## Journey planning

Built on the OTP graphs (see [OpenTripPlanner graphs](#opentripplanner-graphs)). No login.

- Page: `/` (home, full-screen map with the journey panel). `/journey` redirects to `/`.
- API: `GET /api/v1/cities/{city}/stops/?q=` (stop search, #59) and
  `POST /api/v1/cities/{city}/journeys/search/` (#12). Contract: [docs/api.md](docs/api.md#journeys-12-and-stop-search-59).
- Backend apps: `backend/journeys/` (OTP client, itineraries) and `backend/timetable/stops.py` (stop search).
  Frontend: `frontend/src/components/journey/`, `frontend/src/stores/journey.ts`.
- Flow and rules: [docs/architecture.md](docs/architecture.md#journey-search-implemented-12-13).

## Tickets

The ticket catalogue of each city, and a ticket suggestion under the journey results. No login. Buying tickets
is not built yet (#16, #17).

- Page: `/tickets` (the catalogue). The journey results show a ticket hint.
- API: `GET /api/v1/cities/{city}/tickets/?reduced=true|false` (catalogue) and
  `POST /api/v1/cities/{city}/tickets/suggest/` (suggestion). Contract: [docs/api.md](docs/api.md#tickets-14).
- Backend app: `backend/tickets/`. The `Ticket` model has a name and a description in Polish and English
  (django-modeltranslation). The Django admin has language tabs for them. Migration `0002` seeds the Kraków and
  Warsaw tickets.
- The suggestion considers single and time tickets only. Zones are not modelled per stop yet: it uses the city's
  first zone (#83). See [decision 40](docs/decisions.md#40-ticket-suggestion-uses-single-and-time-tickets-only).
- Frontend: `TicketsView` and `TicketHint`. Prices are formatted from decimal strings, not floats.
- Development: `VITE_TICKETS_MOCK=true|empty|fail|offline` replaces the API with a mock. The `empty`, `fail` and
  `offline` values are for testing the empty, error and offline states.
- Design: [docs/architecture.md](docs/architecture.md#tickets-implemented-14-82).

## AI chat assistant

The assistant is the `assistant` Django app (`POST /api/v1/assistant/chat/`) and the chat UI in the frontend.

- **Provider.** Gemini is behind a provider interface. The Gemini provider calls the REST API with `urllib`
  (no SDK). Key from `GEMINI_API_KEY`, model from `GEMINI_MODEL`. See [Gemini API key](#gemini-api-key).
- **Tools.** The model can call six read-only tools: `search_stops`, `plan_journey`, `next_departures`,
  `list_lines`, `get_line_route` and `get_stop_timetable`. They use the same services as the public endpoints.
  The model answers only from tool results. Tickets and live times are not available yet. The assistant's departures use the static timetable only.
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

## Detailed limitations

- Map tiles are loaded directly from `tile.openstreetmap.org`. This follows the OSM tile usage
  policy and is fine for development, but not for production traffic. A tile provider must be
  chosen before deployment.
- The realtime collector runs only while the local stack is up. Continuous collection needs a
  server; hosting is not decided yet.
- Warsaw's timetable comes from the mkuran.pl community feed, maintained by one person. The importer
  keeps the last good version; the official ZTM feed is the fallback (see `docs/decisions.md`, entry 12).
  The national rail feed comes from the same source and has the same risk.
- National rail has static timetables only. There is no realtime data for it yet.
- Timetable browser: frequency-based trips show the template trip's times in the trip view.
- Stop view: a direction is listed when a trip departs the stop there (a later stop exists and the
  pickup type is not "no pickup"). Stop search does not yet find stops by nearby location (#77).
- Live departures: the collector drops whole-trip cancellations, so only skipped stops show as cancelled.
- Live departures: trips from `frequencies.txt` are not expanded.
- Live departures: Warsaw has no realtime data, so its board shows the timetable only.
- Live departures: the central stop takes 0.6 to 0.8 s to respond.
- Journey planning: there is no address search. Points are stops, map picks or my location (#13).
- Journey planning: no rate limit yet. It is needed before public deployment.
- Journey planning: the results show times without a date when the trip is on another day. The wheelchair
  preference does not exclude inaccessible trips.
- Journey planning: journeys use the timetable graph only. Realtime delays are not in the journey results.
- OTP graphs are rebuilt by hand. A graph built before the rail feed was added has no national rail
  until it is rebuilt. Graphs have no bicycle transfers (`docs/decisions.md`, entry 16) and no
  realtime updates.
- Tickets (#14, #82): Warsaw prices come from memory and are not yet checked against the ZTM source. The
  source URL is also to be verified.
- Tickets: zones per stop are not modelled. The suggestion uses the city's first zone (#83).
- Tickets: the suggestion considers single and time tickets only. Daily and periodic tickets are not suggested.
- Tickets: no purchase, accounts or QR tickets yet (#16, #17). The assistant has no ticket tool yet.
- Data sources page (#25, #29): it shows the licence name and link, not the full licence text.
  `docs/data-sources.md` is still planned.
- AI assistant: the rate limit uses the connection IP and no proxy setting (`NUM_PROXIES`), and counters are
  in local memory per process. A shared Redis cache is a follow-up.
- AI assistant: a blocked prompt returns `503`. A normal answer is a follow-up.
- AI assistant: the provider timeout (30 s) is not a hard limit for the whole tool loop.
- AI assistant: the chat history is kept only in the browser. It is not saved on the server.

## Repository layout

```
backend/     Django API, Celery worker and beat (config/, core/, cities/, transit_data/, timetable/, journeys/, assistant/, tickets/)
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

## License

See [LICENSE](LICENSE).
