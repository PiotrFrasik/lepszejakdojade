# API contract (v1)

Single source of truth for agents `backend`, `data`, `ai`, `frontend` and `tester`.
Only the coordinator changes this file, **before** anyone implements the change.
The generated OpenAPI schema (drf-spectacular, `/api/schema/`, Swagger UI at `/api/docs/`) must match it.

## Conventions
- Base path: `/api/v1/`. City-scoped resources: `/api/v1/cities/{city}/…` where `{city}` is `krakow` or `warszawa`.
- JSON, `snake_case` fields. Times in ISO 8601 with offset (`Europe/Warsaw`), durations in seconds, distances in metres.
- Pagination: `?page=`, response `{ "count", "next", "previous", "results" }`.
- Errors: `{ "error": { "code": "not_found", "message": "…" } }` with the matching HTTP status.
  Validation errors (`400`, code `validation_error`) may add an optional `details` object mapping field names
  to lists of messages, e.g. `{ "details": { "email": ["Enter a valid e-mail address."] } }`. Clients must not rely on it being present.
  Keys are field names; nested fields use dotted paths (`"items.1.n"` = field `n` of the second item of `items`);
  errors not tied to one field use the key `non_field_errors`.
- Auth: endpoints marked 🔒 require a logged-in user.
- Language: clients send `Accept-Language: pl` or `en` (default `pl`). Translatable fields (ticket names, descriptions, error messages) come back in that language. Proper names (stops, streets) are never translated.
  See **Language negotiation** below for the exact rules.
- Realtime fields are nullable; `null` means no live data, never a guess.

## Language negotiation (i18n, #28)
Applies to every endpoint under `/api/v1/`.
- Supported languages: `pl` (default) and `en`.
- The server reads `Accept-Language` and honours quality values (`q=`). It picks the first supported language
  by preference; a regional tag matches its base language (`en-GB` → `en`, `pl-PL` → `pl`).
- No header, an empty header, or only unsupported languages (e.g. `de`) → `pl`. Never an error.
- No other language source for the API (no cookie, no `?lang=` parameter, no URL prefix). Once accounts exist (#15),
  the user's saved `language` is a UI preference only; clients still send it as `Accept-Language`.
- Every response (including errors) carries a `Content-Language: pl|en` header with the language actually used.
- Errors: `error.message` and the messages in `error.details` are translated; `error.code` is a stable,
  untranslated identifier that clients must use for logic. This covers DRF and Django defaults too
  (`404`, `405`, `415`, `429`, validation messages), not only our own messages.
- Translatable database content (e.g. ticket names and descriptions, #14) is stored per language and returned as a
  single string in the negotiated language; if the requested translation is empty the `pl` value is returned.
  Responses never contain both languages side by side, except admin-only endpoints.

Example:
```
GET /api/v1/cities/unknown/
Accept-Language: de, en;q=0.8

HTTP/1.1 404 Not Found
Content-Language: en
{ "error": { "code": "not_found", "message": "Not found." } }
```

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
| Account | `POST /auth/register/`, `POST /auth/login/`, `POST /auth/logout/`, `GET /auth/me/`, `PATCH /auth/me/` (incl. `language`) |
| Favourites 🔒 | `GET/POST/DELETE /my/favourites/` |
| History 🔒 | `GET/DELETE /my/history/` |
| Chat | `POST /assistant/chat/` (body includes `language`: `pl` or `en`) |
| Data sources | `GET /data-sources/` |
| Health | `GET /health/` |

## Endpoint details

### `GET /api/v1/health/` (foundation, #2)
Liveness and dependency check used by docker compose and CI. No auth, not paginated, not translated.

Response `200 OK` when every check passes, `503 Service Unavailable` when any check fails (same body shape):
```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "redis": "ok"
  },
  "version": "0.1.0"
}
```
- `status`: `"ok"` or `"error"` (`"error"` if any check is not `"ok"`).
- `checks.<name>`: `"ok"` or `"error"`. No exception details or connection strings in the body (they go to the server log).
- `version`: application version string from settings.

### `GET /api/v1/cities/` (foundation, #5)
List of supported cities. No auth, **not paginated** (plain JSON array), ordered by `id`.
`name` is returned in the request language (`Accept-Language`, default `pl`).

Response `200 OK`:
```json
[
  {
    "id": "krakow",
    "name": "Kraków",
    "map": { "center": { "lat": 50.0614, "lon": 19.9383 }, "zoom": 12 }
  },
  {
    "id": "warszawa",
    "name": "Warszawa",
    "map": { "center": { "lat": 52.2297, "lon": 21.0122 }, "zoom": 11 }
  }
]
```
With `Accept-Language: en` the names are `"Cracow"` / `"Warsaw"` (values come from city config, not code).

### `GET /api/v1/cities/{city}/` (foundation, #5)
One city with everything the UI needs to render it. No auth. Same `id`, `name`, `map` as in the list, plus:

Response `200 OK`:
```json
{
  "id": "krakow",
  "name": "Kraków",
  "timezone": "Europe/Warsaw",
  "map": { "center": { "lat": 50.0614, "lon": 19.9383 }, "zoom": 12 },
  "vehicle_types": ["tram", "bus", "rail"],
  "line_groups": [
    { "id": "day", "name": "Day lines", "colour": "#1f6feb" },
    { "id": "night", "name": "Night lines", "colour": "#3d2b7a" }
  ],
  "realtime": { "departures": true, "vehicles": true }
}
```
- `vehicle_types`: subset of `tram`, `bus`, `metro`, `rail`, in display order (Kraków has no `metro`).
- `line_groups`: in display order; `name` translated (pl/en from config); `colour` is a `#rrggbb` hex string.
- `realtime`: which live data the city's sources provide. `false` means the UI must not offer that view.
- Feed URLs, ticket zones and data source attributions stay in the internal city config and are **not** exposed here
  (ticket zones come with tickets #14, attributions with `GET /data-sources/` #25).

Errors: unknown `{city}` → `404` with `{ "error": { "code": "not_found", "message": "…" } }` (message translated).
