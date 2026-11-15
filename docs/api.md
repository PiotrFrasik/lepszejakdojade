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
| Lines (implemented, #10) | `GET /cities/{city}/lines/?vehicle_type=tram\|bus\|metro\|rail` |
| Line diagram (implemented, #10) | `GET /cities/{city}/lines/{line_id}/route/?direction=0\|1` |
| Stop timetable (implemented, #10) | `GET /cities/{city}/lines/{line_id}/stops/{stop_id}/timetable/?direction=&date=` |
| Trip (implemented, #10) | `GET /cities/{city}/trips/{trip_id}/?date=` |
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

## Timetable (#10)
Shared rules for the timetable endpoints:
- Data comes only from the **active** static GTFS feed versions of the city. No auth. Proper names (stops,
  headsigns, long names) come from GTFS and are never translated; `error.message` is.
- **Ids.** `line_id` and `stop_id` are `{feed_id}:{gtfs_id}` (e.g. `ztp_tram:1`), stable across re-imports of the
  same feed and unique within a city. `trip_id` is `{feed_id}:{gtfs_trip_id}`. Clients treat ids as opaque strings
  and URL-encode them in paths.
- **Service day and times.** `date` parameters are `YYYY-MM-DD` in the city timezone and default to today there.
  GTFS times past 24:00 belong to the service day they start on. Clock times are returned as `HH:MM` local
  (`24:15` becomes `"00:15"` with `next_day: true`); full timestamps are ISO 8601 with offset.
- **Day types.** `weekday`, `saturday`, `sunday` (Sundays and public holidays). The day type of a date is its
  weekday, except that a weekday or Saturday whose set of active services equals the set of the nearest Sunday
  counts as `sunday` (this covers holidays without a hard-coded holiday list).
- **Line groups.** Each line belongs to exactly one `line_groups[].id` of the city (`GET /cities/{city}/`). The
  matching rules (by vehicle type, feed, short name pattern) live in the internal city config, never in code;
  a line that matches no rule goes to the first group.
- **Errors.** Unknown city, line, stop or trip, or a stop the line does not serve in that direction → `404 not_found`.
  Invalid `direction`, `date` (incl. dates within a year of the calendar limits) or `vehicle_type` → `400 validation_error` with `details`.

Shared `line` object (used below as "line summary"):
```json
{ "id": "ztp_tram:52", "short_name": "52", "vehicle_type": "tram", "group": "day",
  "colour": "#1f6feb", "text_colour": "#ffffff" }
```
- `colour` / `text_colour`: GTFS `route_color` / `route_text_color` when set, otherwise the group colour and a
  readable text colour (`#ffffff` or `#000000`). A `route_color` of pure white (`FFFFFF`) or pure black (`000000`)
  counts as not set (some feeds use them as placeholders).
- Trips without `direction_id` count as direction `0`. A direction with no trips of the line → `404`.
- A blank `short_name` falls back to `long_name`, then the GTFS id; a blank headsign falls back to the last stop name.
- Stop `code` is `null` when GTFS has none.

### `GET /api/v1/cities/{city}/lines/?vehicle_type=tram|bus|metro|rail` (#10)
All lines of the city, optionally filtered by vehicle type. **Not paginated** (plain array), sorted by group
display order, then naturally by `short_name` (`2 < 10 < 52 < N1`). Each item is a line summary plus:
```json
[
  { "id": "ztp_tram:1", "short_name": "1", "long_name": "Wzgórza Krzesławickie - Salwator",
    "vehicle_type": "tram", "group": "day", "colour": "#1f6feb", "text_colour": "#ffffff", "notice": null }
]
```
- `notice`: detour or timetable change warning. Always `null` until live alerts exist (#20); clients show the
  badge only when it is non-null. Future shape: `{ "kind": "detour" | "timetable_change", "text": "…" }`.

### `GET /api/v1/cities/{city}/lines/{line_id}/route/?direction=0|1&date=` (#10)
Line diagram for one direction. `direction` defaults to the lowest direction the line has (`0` if it exists). Built from the trips of that line and direction that
run on `date`, or, if none run that day, on the nearest following day with service (`date` in the response).
```json
{
  "line": { "…": "line summary" },
  "direction": 0,
  "date": "2026-11-16",
  "directions": [
    { "direction": 0, "headsign": "Czerwone Maki P+R" },
    { "direction": 1, "headsign": "Os. Piastów" }
  ],
  "stops": [
    { "stop_id": "ztp_tram:stop_376_47501", "name": "Bagatela", "code": "01",
      "lat": 50.0606, "lon": 19.9330, "wheelchair_boarding": true, "variant_only": false,
      "transfers": [ { "…": "line summary" } ] }
  ],
  "variants": [
    { "id": "v1", "kind": "main", "headsign": "Czerwone Maki P+R", "trip_count": 120, "stop_ids": ["…"] },
    { "id": "v2", "kind": "short_turn", "headsign": "Rondo Matecznego", "trip_count": 8, "stop_ids": ["…"] }
  ],
  "shape": { "type": "LineString", "coordinates": [[19.933, 50.0606], [19.94, 50.05]] }
}
```
- `directions`: the directions that exist (one item for loop lines); `headsign` = most common headsign.
- `stops`: the **main variant** (stop pattern with the most trips) in order, plus stops served only by other
  variants inserted at their position in sequence, marked `variant_only: true`.
- `wheelchair_boarding`: `true` / `false` / `null` (unknown). `lat` / `lon` are `null` for stops without coordinates.
- `transfers`: other lines (any vehicle type, excluding this line) stopping at this stop or at a stop with the
  same name within 300 m; sorted like the lines list.
- `variants`: every distinct stop pattern, main first. `kind`: `main`; `short_turn` (a contiguous part of the main
  pattern); `depot` (starts or ends at a stop outside the main pattern, otherwise follows it); `other`.
  Variant ids are only meaningful within one response.
- `shape`: GeoJSON LineString of the main variant (GTFS shape, or straight lines between stops if missing),
  coordinates `[lon, lat]`.

### `GET /api/v1/cities/{city}/lines/{line_id}/stops/{stop_id}/timetable/?direction=0|1&date=` (#10)
Timetable of one line at one stop. `direction` defaults to the lowest direction the line has (`0` if it exists).
```json
{
  "line": { "…": "line summary" },
  "stop": { "stop_id": "ztp_tram:stop_376_47501", "name": "Bagatela", "code": "01" },
  "direction": 0,
  "headsign": "Czerwone Maki P+R",
  "date": "2026-11-16",
  "day_type": "weekday",
  "previous_stop": { "stop_id": "ztp_tram:stop_1", "name": "Teatr Bagatela" },
  "next_stop": { "stop_id": "ztp_tram:stop_2", "name": "Batorego" },
  "columns": [
    { "day_type": "weekday", "date": "2026-11-16", "hours": [
      { "hour": 5, "departures": [
        { "minute": 12, "time": "05:12", "next_day": false, "trip_id": "ztp_tram:trip_3",
          "headsign": "Czerwone Maki P+R", "markers": ["low_floor"], "variant": "v1" }
      ] }
    ] },
    { "day_type": "saturday", "date": "2026-11-21", "hours": [] },
    { "day_type": "sunday", "date": "2026-11-22", "hours": [] }
  ],
  "variants": [ { "id": "v2", "kind": "short_turn", "headsign": "Rondo Matecznego" } ]
}
```
- `columns`: always three, in the order `weekday`, `saturday`, `sunday`. Each column shows the departures of the
  **first date ≥ `date`** that has that day type (`columns[].date`), looking at most 14 days ahead; so picking a
  holiday shows its real timetable in the `sunday` column. Top-level `day_type` is the day type of `date` itself
  and tells the client which column to highlight. Empty `hours` = no service of that day type in that window.
- `hours`: only hours with departures, ascending; departures after midnight of the service day (`next_day: true`)
  come after hour `23` as hour `0`, `1`…
- `markers`: subset of `low_floor` (trip `wheelchair_accessible = 1`), `short_turn` (trip variant kind is
  `short_turn`) and `variant` (any other non-main variant). `variant` is the variant id as in the route endpoint
  for the same line, direction and date. `variants` lists the non-main variants used in this timetable so the
  legend can name their headsigns; legend labels come from client i18n.
- `previous_stop` / `next_stop`: neighbours on the main variant, `null` at the ends.
- Times come from `departure_time`; stop times with `pickup_type = 1` (no pickup), without `departure_time`, or at
  the last stop of the trip are left out (at a terminus the response is `200` with empty columns).
- Frequency-based trips (GTFS `frequencies.txt`, e.g. Warsaw metro) are expanded into one departure per headway;
  their `trip_id` is the template trip, so the trip view shows the template run's times (known limitation).

### `GET /api/v1/cities/{city}/trips/{trip_id}/?date=` (#10)
One trip on one service date (trip view after clicking a minute). `404` if the trip does not run on `date`.
```json
{
  "trip_id": "ztp_tram:trip_3",
  "date": "2026-11-16",
  "line": { "…": "line summary" },
  "direction": 0,
  "headsign": "Czerwone Maki P+R",
  "wheelchair_accessible": true,
  "stops": [
    { "stop_id": "ztp_tram:stop_376_47501", "name": "Bagatela",
      "arrival": "2026-11-16T05:12:00+01:00", "departure": "2026-11-16T05:12:00+01:00" }
  ]
}
```
- `wheelchair_accessible`: `true` / `false` / `null`. `arrival` / `departure` are `null` when GTFS has no time for
  that stop.
