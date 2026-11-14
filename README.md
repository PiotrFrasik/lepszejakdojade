# lepszejakdojade

Public transport web app for Kraków and Warsaw. It is in early development: the foundation
(containers, API skeleton, frontend shell with a city picker, map and language switch) is in place.
A realtime collector for Kraków trip updates has started and stores data in the database.
Journey planning, timetables, tickets, live departures and the AI assistant are planned.

Full product description: [docs/concept.md](docs/concept.md).
The app is bilingual (Polish / English) with a language switcher.

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

### Optional: OpenTripPlanner

OTP is not started by default. It runs only with the `otp` profile:

```bash
docker compose --profile otp up
```

The OTP graph is built in a later step (issue #8), so OTP will not answer journey queries yet.

### Gemini API key

The AI assistant needs a Google Gemini API key. It is not used yet.

1. Open [Google AI Studio](https://aistudio.google.com/app/apikey) and create an API key.
2. Put it in `.env` as `GEMINI_API_KEY=...`.

Never commit `.env`. It is listed in `.gitignore`.

## Cities

City configuration lives in `backend/cities/config/<id>.yaml`, one file per city.

- Adding a city means adding a file. No code change is needed.
- Files are validated strictly at startup. A broken file stops `runserver`, `migrate` and every
  management command. The error names the file and the field.
- Optional: set `CITY_CONFIG_DIR` in `.env` to load city files from another directory.
- Public fields are exposed via `GET /api/v1/cities/`. Internal fields (feeds, ticket zones,
  attributions) are not exposed.

## Realtime data collector

A Celery beat task, `transit_data.collect_trip_updates`, polls the GTFS-Realtime trip update
feeds of each city every `REALTIME_POLL_INTERVAL_SECONDS` (default 30). It runs in the
`celery-worker` and `celery-beat` services, so `docker compose up -d` starts it.

- Feeds come from each city's `gtfs_rt` list in its config file, where `entity: trip_updates`.
  For Kraków these are `ztp_tram_trip_updates` and `ztp_bus_trip_updates`.
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
Short version: tram messages have no delays until the static GTFS import (#7) is built. Raw
events are meant to be kept for 60 days; the deletion job comes with #22 and is not built yet.

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

## Repository layout

```
backend/     Django API, Celery worker and beat (config/, core/, cities/, transit_data/)
frontend/    Vue 3 + TypeScript + Vite app
otp/         OpenTripPlanner config and graph data
docs/        concept, API contract, architecture, decisions, AI workflow log
docker-compose.yml, Makefile, .env.example
```

## Documentation

- [docs/concept.md](docs/concept.md): product concept
- [docs/api.md](docs/api.md): API contract (the live Swagger UI is linked above)
- [docs/architecture.md](docs/architecture.md): services, data flow and retention
- [docs/backlog.md](docs/backlog.md): planned work
- [docs/decisions.md](docs/decisions.md): short decision records
- [docs/ai-workflow/log.md](docs/ai-workflow/log.md): log of features built with AI agents
- `docs/ai-workflow/README.md` (planned): how the app is built with AI agents

## License

See [LICENSE](LICENSE).
