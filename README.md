# lepszejakdojade

Public transport web app for Kraków and Warsaw. It is in early development: the foundation
(containers, API skeleton, frontend shell with a city picker, map and language switch) is in place.
Journey planning, timetables, tickets, live data and the AI assistant are planned.

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

## Tests

```bash
docker compose exec backend pytest -q     # backend (pytest)
cd frontend && npm run test               # frontend (Vitest), needs Node 22 on the host
```

## Windows notes

- `make` is usually not installed on Windows. The Makefile targets are thin wrappers over
  `docker compose`; you can run the commands from the Makefile directly.
- If you change `POSTGRES_PASSWORD` after the first run, the database keeps the old password.
  Recreate the dev database with `docker compose down -v` (this deletes its data).
- After changes to `frontend/package.json`, rebuild the frontend image without its volume:
  `docker compose up -d --build -V`.
- An old `backend/.pytest_cache` directory owned by root (created by earlier container runs)
  can be deleted from the host.

## Known limitations

- Map tiles are loaded directly from `tile.openstreetmap.org`. This follows the OSM tile usage
  policy and is fine for development, but not for production traffic. A tile provider must be
  chosen before deployment.

## Repository layout

```
backend/     Django API, Celery worker and beat (config/, core/)
frontend/    Vue 3 + TypeScript + Vite app
otp/         OpenTripPlanner config and graph data
docs/        concept, API contract, architecture, decisions, AI workflow log
docker-compose.yml, Makefile, .env.example
```

## Documentation

- [docs/concept.md](docs/concept.md): product concept
- [docs/api.md](docs/api.md): API contract (the live Swagger UI is linked above)
- [docs/backlog.md](docs/backlog.md): planned work
- [docs/ai-workflow/log.md](docs/ai-workflow/log.md): log of features built with AI agents
- `docs/ai-workflow/README.md` (planned): how the app is built with AI agents

## License

See [LICENSE](LICENSE).
