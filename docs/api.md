# API contract (v1)

Single source of truth for agents `backend`, `data`, `ai`, `frontend` and `tester`.
Only the coordinator changes this file, **before** anyone implements the change.
The generated OpenAPI schema (drf-spectacular, `/api/schema/`, Swagger UI at `/api/docs/`) must match it.

## Conventions
- Base path: `/api/v1/`. City-scoped resources: `/api/v1/cities/{city}/…` where `{city}` is `krakow` or `warszawa`.
- JSON, `snake_case` fields. Times in ISO 8601 with offset (`Europe/Warsaw`), durations in seconds, distances in metres.
- Pagination: `?page=`, response `{ "count", "next", "previous", "results" }`.
- Errors: `{ "error": { "code": "not_found", "message": "…" } }` with the matching HTTP status.
- Auth: endpoints marked 🔒 require a logged-in user.
- Realtime fields are nullable; `null` means no live data, never a guess.

## Planned endpoints (details are added per feature)
| Area | Method & path |
|---|---|
| Cities | `GET /cities/`, `GET /cities/{city}/` |
| Stops | `GET /cities/{city}/stops/?q=&lat=&lon=&radius=` |
| Stop overview | `GET /cities/{city}/stops/{stop_id}/` (lines at the stop, next departures) |
| Departures | `GET /cities/{city}/stops/{stop_id}/departures/?limit=` |
| Lines | `GET /cities/{city}/lines/?vehicle_type=tram|bus|metro|rail` |
| Line diagram | `GET /cities/{city}/lines/{line_id}/route/?direction=0|1` |
| Stop timetable | `GET /cities/{city}/lines/{line_id}/stops/{stop_id}/timetable/?direction=&date=` |
| Trip | `GET /cities/{city}/trips/{trip_id}/?date=` |
| Journeys | `POST /cities/{city}/journeys/search/` |
| Vehicles (live) | `GET /cities/{city}/vehicles/?bbox=` |
| Alerts | `GET /cities/{city}/alerts/?line=` |
| Delay stats | `GET /cities/{city}/lines/{line_id}/delay-stats/?stop_id=` |
| Tickets | `GET /cities/{city}/tickets/`, `POST /cities/{city}/tickets/suggest/` |
| Demo purchase 🔒 | `POST /orders/`, `GET /orders/{id}/`, `GET /my/tickets/` |
| Account | `POST /auth/register/`, `POST /auth/login/`, `POST /auth/logout/`, `GET /auth/me/` |
| Favourites 🔒 | `GET/POST/DELETE /my/favourites/` |
| History 🔒 | `GET/DELETE /my/history/` |
| Chat | `POST /assistant/chat/` |
| Data sources | `GET /data-sources/` |
