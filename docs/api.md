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
| Stops search (implemented, #59) | `GET /cities/{city}/stops/?q=` |
| Stops near a point (planned) | `GET /cities/{city}/stops/?lat=&lon=&radius=` |
| Stop overview (#9) | `GET /cities/{city}/stops/{stop_id}/` (lines at the stop with directions) |
| Departures (#73) | `GET /cities/{city}/stops/{stop_id}/departures/?limit=` (scheduled + live) |
| Lines (implemented, #10) | `GET /cities/{city}/lines/?vehicle_type=tram\|bus\|metro\|rail` |
| Line diagram (implemented, #10) | `GET /cities/{city}/lines/{line_id}/route/?direction=0\|1` |
| Stop timetable (implemented, #10) | `GET /cities/{city}/lines/{line_id}/stops/{stop_id}/timetable/?direction=&date=` |
| Trip (implemented, #10) | `GET /cities/{city}/trips/{trip_id}/?date=` |
| Journeys (implemented, #12) | `POST /cities/{city}/journeys/search/` |
| Vehicles (live) | `GET /cities/{city}/vehicles/?bbox=` |
| Alerts | `GET /cities/{city}/alerts/?line=` |
| Delay stats | `GET /cities/{city}/lines/{line_id}/delay-stats/?stop_id=` |
| Tickets (#14) | `GET /cities/{city}/tickets/?reduced=`, `POST /cities/{city}/tickets/suggest/` |
| Demo purchase 🔒 | `POST /orders/`, `GET /orders/{id}/`, `GET /my/tickets/` |
| Account | `POST /auth/register/`, `POST /auth/login/`, `POST /auth/logout/`, `GET /auth/me/`, `PATCH /auth/me/` (incl. `language`) |
| Favourites 🔒 | `GET/POST/DELETE /my/favourites/` |
| History 🔒 | `GET/DELETE /my/history/` |
| Chat (implemented, #18) | `POST /assistant/chat/` (answer language = negotiated `Accept-Language`) |
| Data sources (#25) | `GET /data-sources/` |
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

## Journeys (#12) and stop search (#59)

### `GET /api/v1/cities/{city}/stops/?q=` (#59, part of #9)
Stop name search for the journey form autocomplete. No auth. Active static GTFS feeds of the city only.
- `q`: required, at least 2 characters after trimming; case- and Polish-diacritics-insensitive
  (`plac` matches `Plac`, `zabl` matches `Żabłocie`). Prefix matches of any word rank before other substring matches,
  then by name. Shorter `q` → `400 validation_error`.
- **Grouped by name:** platforms with the same name within 300 m are one result. Not paginated, at most 20 results.
```json
[
  { "stop_id": "ztp_tram:stop_376_47501", "name": "Bagatela", "lat": 50.0606, "lon": 19.9330,
    "vehicle_types": ["tram", "bus"], "stop_ids": ["ztp_tram:stop_376_47501", "ztp_bus:stop_376_47502"] }
]
```
- `stop_id`: a representative platform (the one closest to the group centroid); `lat` / `lon`: the group centroid.
- `stop_ids`: all platforms of the group. `vehicle_types`: subset of `tram`, `bus`, `metro`, `rail` serving the group.

### `POST /api/v1/cities/{city}/journeys/search/` (#12)
Journey planning A→B through the city's OpenTripPlanner 2 instance (`OTP_URL_KRAKOW` or `OTP_URL_WARSZAWA`). No auth.
No rate limit yet (planned before public deployment).
Request:
```json
{
  "from": { "stop_id": "ztp_tram:stop_376_47501" },
  "to": { "lat": 50.0215, "lon": 19.8900 },
  "time": "2026-11-16T08:00:00+01:00",
  "time_mode": "depart",
  "preferences": { "fewer_transfers": false, "less_walking": false, "wheelchair": false }
}
```
- `from` / `to`: exactly one of `{ "stop_id" }` (any id from stop search, incl. `stop_ids`) or `{ "lat", "lon" }`.
  Optional `name` (string) is echoed back as the place label. Points outside the city's bounding box → `400`.
- `time`: optional, defaults to now; `time_mode`: `depart` (default) or `arrive`.
- `preferences`: all optional, default `false`. `fewer_transfers` and `less_walking` raise OTP's transfer and walk
  reluctance; `wheelchair` makes OTP prefer wheelchair-accessible trips and stops (inaccessible ones are penalised,
  not excluded).
- Same `from` and `to`, unknown `stop_id`, bad types → `400 validation_error` with `details`.

Response `200 OK`:
```json
{
  "from": { "name": "Bagatela", "lat": 50.0606, "lon": 19.9330 },
  "to": { "name": null, "lat": 50.0215, "lon": 19.8900 },
  "itineraries": [
    {
      "id": "i1",
      "start": "2026-11-16T08:03:00+01:00",
      "end": "2026-11-16T08:31:00+01:00",
      "duration": 1680,
      "transfers": 1,
      "walk_distance": 640,
      "walk_duration": 520,
      "legs": [
        {
          "mode": "walk",
          "start": "2026-11-16T08:03:00+01:00", "end": "2026-11-16T08:07:00+01:00",
          "duration": 240, "distance": 300,
          "from": { "name": "Bagatela", "stop_id": null, "lat": 50.0606, "lon": 19.9330 },
          "to": { "name": "Teatr Bagatela", "stop_id": "ztp_tram:stop_1", "lat": 50.0610, "lon": 19.9325 },
          "line": null, "headsign": null, "trip_id": null, "intermediate_stops": [],
          "geometry": { "type": "LineString", "coordinates": [[19.9330, 50.0606], [19.9325, 50.0610]] }
        },
        {
          "mode": "tram",
          "start": "2026-11-16T08:07:00+01:00", "end": "2026-11-16T08:20:00+01:00",
          "duration": 780, "distance": 4100,
          "from": { "name": "Teatr Bagatela", "stop_id": "ztp_tram:stop_1", "lat": 50.0610, "lon": 19.9325 },
          "to": { "name": "Czerwone Maki P+R", "stop_id": "ztp_tram:stop_9", "lat": 50.0170, "lon": 19.8890 },
          "line": { "id": "ztp_tram:52", "short_name": "52", "vehicle_type": "tram", "group": "day",
                    "colour": "#1f6feb", "text_colour": "#ffffff" },
          "headsign": "Czerwone Maki P+R",
          "trip_id": "ztp_tram:trip_3",
          "intermediate_stops": [ { "name": "Batorego", "stop_id": "ztp_tram:stop_2" } ],
          "geometry": { "type": "LineString", "coordinates": [[19.9325, 50.0610], [19.8890, 50.0170]] }
        }
      ]
    }
  ],
  "comparison": { "walk": { "duration": 3900, "distance": 5200 }, "bike": { "duration": 1260, "distance": 5600 } }
}
```
- `itineraries`: at most 5, sorted by arrival time (`depart`) or by departure time descending (`arrive`). Empty list
  (still `200`) when OTP finds no route.
- `mode`: `walk`, `tram`, `bus`, `metro`, `rail`. `line` is the timetable "line summary" (ids `{feed_id}:{gtfs_id}`
  as in the timetable API, so the client can link to the timetable) and `null` for walking legs.
- `transfers`: transit legs − 1 (min 0). `walk_distance` / `walk_duration`: sums over walking legs.
- `geometry`: GeoJSON LineString, coordinates `[lon, lat]` (decoded from OTP's polyline).
- `comparison`: direct walk and bike (OTP street routing, no transit) between the same points; each is `null` when
  OTP finds no such route or it would take more than 3 hours.
- Errors: unknown city → `404`; city without OTP configured or OTP unreachable / timing out (10 s) / returning an error
  → `503` with code `journey_planner_unavailable` (message translated). OTP internals are never passed to the client.

## Departures (#73)

### `GET /api/v1/cities/{city}/stops/{stop_id}/departures/?limit=` (#73, part of #9 and #20)
Next departures at a stop group, from the static timetable, with live times where the city has realtime data.
No auth. Timetable shared rules (ids, line summary, errors) apply.
- `stop_id`: any platform id. The response covers its whole stop group, using the same grouping as stop search
  (platforms with the same name within 300 m).
- `limit`: integer 1–30, default 15. Out of range or not an integer → `400 validation_error` with `details`.
- **Window.** Departures whose effective time (`expected` when known, otherwise `scheduled`) is at or after
  now − 1 minute, up to 3 hours after now, sorted by effective time, then `scheduled`. Trips scheduled up to
  60 minutes before now are considered, so a late vehicle still appears. Service days yesterday, today and tomorrow
  (city timezone) are considered, so trips past midnight are included. The last stop of a trip is not a departure.
- **Live data.** A departure is matched to collected GTFS-Realtime stop events by trip, platform and service day.
  An event counts only if it was seen in the last 5 minutes. The realtime-to-static feed mapping lives in city config.
```json
{
  "stop": { "id": "ztp_tram:stop_376_47501", "name": "Bagatela",
            "stop_ids": ["ztp_tram:stop_376_47501", "ztp_bus:stop_376_47502"] },
  "generated_at": "2026-11-15T21:04:10+01:00",
  "realtime_available": true,
  "departures": [
    { "line": { "id": "ztp_tram:52", "short_name": "52", "vehicle_type": "tram", "group": "day",
                "colour": "#1f6feb", "text_colour": "#ffffff" },
      "trip_id": "ztp_tram:block_1_trip_5", "headsign": "Czerwone Maki P+R",
      "platform_id": "ztp_tram:stop_376_47501", "platform_code": "01",
      "scheduled": "2026-11-15T21:06:00+01:00", "expected": "2026-11-15T21:09:00+01:00",
      "delay_seconds": 180, "status": "live" }
  ]
}
```
- `stop`: the requested platform's group; `id` echoes the requested `stop_id`, `name` is the group name.
- `generated_at`: server time of the response (city timezone offset).
- `realtime_available`: `true` only when the city config declares realtime departures and at least one of its
  trip-update feeds was fetched successfully in the last 5 minutes. When `false`, every departure has
  `status: "scheduled"` and `expected` / `delay_seconds` are `null`.
- `status`: `live` — a fresh event matched (`expected` and `delay_seconds` set; `delay_seconds` may be negative
  or 0); `canceled` — the trip or this stop is cancelled / skipped (`expected` and `delay_seconds` are `null`);
  `scheduled` — no fresh event (`expected` and `delay_seconds` are `null`).
- `headsign`: stop headsign, then trip headsign, then the last stop name. `platform_code`: GTFS `platform_code`
  or stop `code`, `null` when neither is set.
- An empty `departures` list is a valid answer (`200`), e.g. at night.
- Response header `Cache-Control: max-age=15`.
- Errors: unknown city or stop → `404 not_found`.

## Stop overview (#9)

### `GET /api/v1/cities/{city}/stops/{stop_id}/` (#9)
Lines serving a stop group, with their directions, so the client can link each one to the stop timetable (#10).
No auth. Active static GTFS feeds of the city only. Timetable shared rules (ids, line summary, errors) apply.
Next departures are not part of this response; clients call `…/stops/{stop_id}/departures/` (#73).
- `stop_id`: any platform id. The response covers its whole stop group, using the same grouping as stop search
  (platforms with the same name within 300 m).
```json
{
  "stop": { "id": "ztp_tram:stop_376_47501", "name": "Bagatela", "lat": 50.0606, "lon": 19.9330,
            "vehicle_types": ["tram", "bus"],
            "stop_ids": ["ztp_tram:stop_376_47501", "ztp_bus:stop_376_47502"] },
  "lines": [
    { "line": { "id": "ztp_tram:52", "short_name": "52", "vehicle_type": "tram", "group": "day",
                "colour": "#1f6feb", "text_colour": "#ffffff" },
      "directions": [
        { "direction": 0, "headsign": "Czerwone Maki P+R", "platform_id": "ztp_tram:stop_376_47501" },
        { "direction": 1, "headsign": "Os. Piastów", "platform_id": "ztp_tram:stop_376_47503" }
      ] }
  ]
}
```
- `stop`: `id` echoes the requested `stop_id`; `name` is the group name; `lat` / `lon` the group centroid;
  `vehicle_types` and `stop_ids` as in stop search.
- `lines`: every line with at least one trip (in any active service) calling at a platform of the group.
  Sorted by vehicle type (`tram`, `bus`, `metro`, `rail`), then by the order of the city's `line_groups`, then by
  `short_name` in natural order (`2` before `10`, then letters).
- `directions`: one entry per `direction_id` (missing = `0`) in which the line **departs** from the group, sorted by
  `direction`. A trip departs from the group when it calls at one of its platforms with a later stop after it and
  boarding allowed there (`pickup_type` is not `1`), as in the departures and stop timetable endpoints. A direction
  with no such trip (e.g. the group is only the last stop) is omitted; a line left with no directions is omitted.
  - `platform_id`: the platform of the group where most trips of that line and direction call (ties: lowest id).
    Together with `line.id` and `direction` it is valid input for
    `GET /cities/{city}/lines/{line_id}/stops/{platform_id}/timetable/?direction=`.
  - `headsign`: the most frequent headsign of those trips at that platform (stop headsign, then trip headsign,
    then the last stop name; ties: alphabetical). It is an empty string only if all three are blank.
- An empty `lines` list is valid (`200`).
- Response header `Cache-Control: max-age=300`.
- Errors: unknown city or stop → `404 not_found`.

## Tickets (#14)
Ticket catalogue per city, stored in the database and edited in the Django admin. No auth. Read only.
Shared rules for both endpoints:
- **Translated fields:** `name` and `description` are one string in the negotiated language (django-modeltranslation,
  empty `en` → `pl` value). Zone `name` comes from the city config `ticket_zones[].names` in the same language.
- **Money:** `price` is a decimal string with two places (`"6.00"`), `currency` is an ISO 4217 code (`"PLN"`).
  Clients format it for the selected language; they never do arithmetic on it as a float.
- **Ticket object:**
```json
{
  "id": "krakow-time-60-z1",
  "name": "60-minute ticket",
  "description": "Unlimited rides for 60 minutes in Zone I.",
  "kind": "time",
  "validity_minutes": 60,
  "zones": ["1"],
  "reduced": false,
  "price": "6.00",
  "currency": "PLN",
  "prices_as_of": "2026-11-01",
  "source_url": "https://ztp.krakow.pl/bilety"
}
```
  - `id`: stable slug, unique across cities.
  - `kind`: `single` (one ride, no transfers), `time` (unlimited rides for `validity_minutes`), `daily`
    (24 h / 48 h / 72 h …, `validity_minutes` = 1440 × days), `period` (7 days or longer, informational).
  - `validity_minutes`: `null` for `single`.
  - `zones`: ids from the city config `ticket_zones`, never empty; a ticket covers a journey only if it covers all
    the journey's zones.
  - `reduced`: reduced-fare variant (separate ticket object, separate price).
  - `prices_as_of`: date the price was checked (`YYYY-MM-DD`); `source_url`: official price list.
- Only active tickets (admin flag) are returned.
- Errors: unknown city → `404 not_found`.

### `GET /api/v1/cities/{city}/tickets/?reduced=true|false` (#14)
Whole catalogue of the city. **Not paginated.** Optional `reduced` filter (omitted or empty = both). Any other
value than `true` / `false` → `400 validation_error`.
```json
{
  "zones": [ { "id": "1", "name": "Zone I" }, { "id": "2", "name": "Zone II" } ],
  "tickets": [ { "...": "ticket object" } ]
}
```
- `zones`: the city's `ticket_zones` in config order.
- `tickets`: sorted by `kind` (`single`, `time`, `daily`, `period`), then `validity_minutes` ascending, then the number
  of zones ascending, then `reduced` (`false` first), then `id`.
- Response header `Cache-Control: max-age=300`.

### `POST /api/v1/cities/{city}/tickets/suggest/` (#14)
Cheapest ticket that covers one journey. Clients call it for a journey result (#12) using its `duration` and
`transfers`.
Request:
```json
{ "duration_seconds": 1680, "transfers": 1, "zones": ["1"], "reduced": false }
```
- `duration_seconds`: required integer, 1 … 86400.
- `transfers`: optional integer ≥ 0, default `0`. `single` tickets are considered only when it is `0`.
- `zones`: optional list of zone ids from the city config, default the city's first zone. Unknown zone id or empty
  list → `400 validation_error`. A city with no `ticket_zones` in its config and `zones` omitted → also
  `400 validation_error`.
- `reduced`: optional, default `false`; only tickets with the same `reduced` value are considered.

Selection: among active tickets of the city with kind `single` or `time` (never `daily` / `period`), keep those that
cover all requested `zones` and whose `validity_minutes × 60 ≥ duration_seconds` (`single`: any duration, only with
0 transfers). Pick the lowest `price`; ties: shorter `validity_minutes`, then fewer zones, then `id`.

Response `200 OK`:
```json
{
  "ticket": { "...": "ticket object" },
  "reason": "A 60-minute ticket covers this 28-minute journey in Zone I."
}
```
- `ticket`: `null` when nothing matches (e.g. the journey is longer than any time ticket). `reason` then says so.
- `reason`: one short sentence in the negotiated language (Django translations), built by the server; clients show it
  as is.
- Errors: unknown city → `404 not_found`; bad body → `400 validation_error` with `details`.

## Assistant (#18)

### `POST /api/v1/assistant/chat/` (#18)
AI chat assistant. No auth. Stateless: the client keeps the conversation and sends it with every request.
Request:
```json
{
  "city": "krakow",
  "messages": [
    { "role": "user", "text": "Kiedy następna 52 z Bagateli?" }
  ]
}
```
- `city`: a city id from `GET /cities/`; unknown → `400 validation_error`.
- `messages`: 1–20 items, oldest first, roles `user` or `assistant`; the last one must be `user`. Each `text` is
  1–1000 characters after trimming. Older messages beyond 20 are dropped by the client, not the server.
- **Language.** The answer is written in the negotiated language (`Accept-Language`, see Language negotiation),
  whatever language the question is in. No `language` field in the body.

Response `200 OK`:
```json
{
  "message": { "role": "assistant", "text": "Najbliższa 52 z Bagateli odjeżdża o 08:14 w kierunku Czerwone Maki P+R." },
  "cards": [
    {
      "type": "departures",
      "stop": { "stop_id": "ztp_tram:stop_376_47501", "name": "Bagatela" },
      "departures": [
        { "line": { "…": "line summary" }, "stop_id": "ztp_tram:stop_376_47501", "direction": 0, "headsign": "Czerwone Maki P+R",
          "time": "08:14", "next_day": false, "date": "2026-11-16", "trip_id": "ztp_tram:trip_3" }
      ]
    }
  ]
}
```
- `message.text`: plain text (no Markdown, no HTML); clients render it as text.
- `cards`: 0–3 items, built by the server **only from tool results** of this turn (never from model text). Types:
  - `journey`: `{ "type": "journey", "from": {…}, "to": {…}, "itinerary": {…}, "comparison": {…} }` — `from`, `to`,
    one `itinerary` object and `comparison` exactly as in `POST /cities/{city}/journeys/search/`.
  - `departures`: as above; up to 10 upcoming departures at one stop group (one or more lines), ascending.
    `stop.stop_id` is the group's representative platform (for display). Each departure's own `stop_id` is the
    platform it leaves from; with `line.id` / `direction` it links to the stop timetable
    (`/lines/{line_id}/stops/{stop_id}/timetable/?direction=&date=`).
  - `stops`: `{ "type": "stops", "stops": [ … ] }` — up to 5 items exactly as in `GET /cities/{city}/stops/?q=`
    (used when a place name is ambiguous).
  Clients ignore card types they do not know.
- **Answers only from app data.** The model may answer only from tool results (stop search, journey planning, lines,
  line route, stop timetable / next departures). If the tools give no answer it says so; it never guesses times,
  prices or delays. Tickets and live data are not available yet (planned) and the assistant says so.
- Proper names (stops, headsigns) are never translated.

Errors:
- `400 validation_error` with `details` (bad `city`, `messages`, roles, lengths).
- `429 rate_limited`: per client IP, 10 requests per minute and 100 per day (values from settings / env, not code).
  Response has a `Retry-After` header (seconds) and `error.details` is not used.
- `503 assistant_unavailable`: no `GEMINI_API_KEY`, provider error or timeout (30 s), or a tool loop longer than
  5 steps. Provider internals are never passed to the client. A tool failing (e.g. OTP down) is **not** a 503: the
  assistant answers that the data is unavailable right now.
- All `error.message` values are translated.

## Data sources (#25)

### `GET /api/v1/data-sources/` (#25)
Licence attributions and the age of the static data, for the "Data sources" page (#29). No auth, not paginated.
Translated fields come back in the request language (`Accept-Language`); proper names, licence names and URLs are not translated.

Response `200 OK`:
```json
{
  "cities": [
    {
      "id": "krakow",
      "name": "Kraków",
      "sources": [
        {
          "name": "Zarząd Transportu Publicznego w Krakowie",
          "url": "https://gtfs.ztp.krakow.pl/",
          "licence": "CC BY 4.0",
          "licence_url": "https://creativecommons.org/licenses/by/4.0/",
          "description": "Rozkłady jazdy tramwajów i autobusów w Krakowie (także linii aglomeracyjnych Mobilis) oraz dane o pojazdach w czasie rzeczywistym."
        }
      ],
      "feeds": [
        {
          "feed_id": "ztp_tram",
          "publisher_name": "ZTP Kraków",
          "last_modified": "2026-11-13T22:10:00+01:00",
          "downloaded_at": "2026-11-14T03:00:12+01:00",
          "imported_at": "2026-11-14T03:02:40+01:00",
          "service_start_date": "2026-11-14",
          "service_end_date": "2026-12-31"
        }
      ]
    }
  ]
}
```
- `cities`: every configured city, ordered by `id` as in `GET /cities/`; `name` in the request language.
- `sources`: the city's `attributions` from city config, in config order. `licence` (config allows null),
  `licence_url` and `description` are nullable. `description` comes from an optional `descriptions: { pl, en }`
  entry per attribution in city config (request language, falls back to `pl`, else `null`).
- `feeds`: one entry per **active** static GTFS feed version of the city, ordered by `feed_id`. Empty list when nothing
  has been imported yet (still `200`). It states when the data was created (`last_modified`, the publisher's HTTP
  `Last-Modified` converted to ISO 8601; `null` when absent or unparsable) and retrieved (`downloaded_at`), as several
  licences require. `publisher_name` is from `feed_info.txt` (`null` when empty); `imported_at`,
  `service_start_date`, `service_end_date` are nullable.
- Timestamps ISO 8601 with offset in the city timezone; dates `YYYY-MM-DD`.
- Not exposed: feed source URLs, hashes, etags, sizes, or any other internal config (feeds, OTP).
- The statement that the data was processed (required by PKP PLK, Koleje Mazowieckie and Warsaw open data terms)
  is static UI text on the page (frontend i18n), not part of the response.
- Errors: none specific to this endpoint.
