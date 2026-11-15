# Decision records

Short ADR-style records. Each entry has context, decision, alternatives and consequences.
New entries go at the bottom. Do not rewrite an accepted entry; add a new one that supersedes it.

## 1. City configuration as YAML files with strict validation

**Status:** accepted (2026-11-11)

**Context.** The app serves several cities. City values (feed URLs, map centre, ticket zones,
attributions, line colours) must not be in code. The frontend also must not hard-code cities.

**Decision.** Each city is one file, `backend/cities/config/<id>.yaml`. The registry loads all files
and validates them strictly at startup. A broken file stops `runserver`, `migrate` and every
management command, and the error names the file and the field. The registry is cached per process
and the cache is cleared when the setting changes. `CITY_CONFIG_DIR` can point to another directory.
YAML comments are allowed, for example to mark a feed URL as not yet verified. PyYAML is a backend
dependency.

**Alternatives.** A database table edited in the admin. A Django settings dict. The reasons these
were not chosen are not recorded here.

**Consequences.**
- Adding a city is a file change that goes through review.
- A typo in a city file fails fast, before any request is served.
- The registry is cached per process. Restart the backend to pick up a changed file.
- Feed URLs and licences in the files are not verified yet. See `docs/data-sources.md` (planned).

## 2. Compiled Django `.mo` files are committed next to `.po` files

**Status:** accepted (2026-11-11, decided by the maintainer)

**Context.** The backend translations are in `.po` files. Compiled `.mo` files are needed at runtime.
The Compose setup mounts the source as `./backend:/app`. A `.mo` file compiled during the image build
is hidden by this bind mount, so the app would run without translations.

**Decision.** The compiled `.mo` files are committed next to their `.po` files. CI (issue #4) should
check that each `.mo` file matches its `.po` file. Compile them again with `compilemessages` when a
`.po` file changes.

**Alternatives.** Compile at container start, or only in the image build. Both do not work with the
bind mount.

**Consequences.**
- Binary files are in git and can show as changed in diffs.
- Forgetting to recompile gives stale translations. The CI check (issue #4) is meant to catch this.

## 3. The frontend gets cities only from the API

**Status:** accepted (2026-11-11)

**Context.** The frontend had hard-coded cities. This blocked adding a city without a frontend change.

**Decision.** The frontend loads the city list and city details from `/api/v1/cities/` through the API
client. No city values (names, coordinates, ids used as data) are in frontend code. UI text for city
names still goes through i18n.

**Alternatives.** Keep a copy of the city list in the frontend, or generate it at build time from the
backend files. Not chosen; the reasons are not recorded here.

**Consequences.**
- The city picker depends on the API. It shows loading, error, retry and empty states.
- Adding a city needs no frontend release.

## 4. Service date for feeds without `start_date` is inferred

**Status:** accepted (2026-11-14)

**Context.** Statistics need a service day for each trip (for example, a 00:30 trip of Friday's
timetable belongs to Thursday's service day). The ZTP Kraków tram TripUpdates feed has no
`start_date`, so the service day cannot come from the feed.

**Decision.** The realtime collector infers the service date as the local date of the event time
minus 3 hours, and marks the row `service_date_inferred=True`. A trip seen in the last 4 hours
reuses its stored service date, so a trip that crosses 03:00 keeps one date.

**Alternatives.** Use the feed's `start_date` when it exists and skip trips without it. Neither ZTP
feed has `start_date`, so this would store nothing. Wait for the static GTFS import (#7). Collection
had to start now because delay statistics need weeks of data, and static GTFS alone cannot tell which
day's run of a daily-repeated `trip_id` an update belongs to. Once #7 exists it can refine the
inference.

**Consequences.**
- Rows from ZTP tram feeds carry a flag. Statistics can tell inferred dates from feed dates.
- A trip first seen after 03:00 that started before 03:00 gets the later date. This is a known
  limitation.
- The inference can be replaced once static GTFS (#7) is available.

## 5. A bad value skips only its entity, not the whole poll

**Status:** accepted (2026-11-14)

**Context.** One malformed entity in a feed (overlong id, NUL byte, out-of-range time) rolled back
the whole poll. A single bad message then removed all data from that poll.

**Decision.** Validation runs per entity and per stop update. A bad value skips only that entity or
stop update. The skipped count is stored in `FeedFetch.skipped_count`, a summary in `FeedFetch.error`,
and one warning is logged per poll. The collector never raises; every poll writes a `FeedFetch` row.

**Alternatives.** Reject the whole feed on any bad value (the old behaviour). Rejected because one bad
entity would discard about 10k valid stop events, and if the bad entity persists in the feed, every
poll would be lost for as long as it stays there.

**Consequences.**
- Partial data is possible. Check `skipped_count` in the admin to see it.
- A feed that is bad in every poll shows a steady skipped count. This is visible, not silent.

## 6. Language comes only from `Accept-Language`

**Status:** accepted (2026-11-14)

**Context.** The API must return messages in the user's language without a login. Django's
`LocaleMiddleware` also reads a language cookie and URL prefixes. That gives the API more than one
language source, and they can disagree.

**Decision.** `core.middleware.AcceptLanguageMiddleware` replaces `LocaleMiddleware`. It reads only the
`Accept-Language` header. Quality values are honoured, a regional tag matches its base language, and
the default is `pl`. Every response carries `Content-Language` and `Vary: Accept-Language`. The rules
are in `docs/api.md`, section "Language negotiation".

**Alternatives.** Keep `LocaleMiddleware`. Rejected: the API has no other language source, so a cookie
or URL prefix would only add a second source that can disagree with the header.

**Consequences.**
- A user's saved language (#15) is a UI preference. Clients still send it as `Accept-Language`.
- Known limitation: redirects from `SecurityMiddleware` have no `Content-Language` header.

## 7. Translated database content uses django-modeltranslation

**Status:** accepted (2026-11-14, decided by the maintainer)

**Context.** Database content such as ticket names and descriptions (#14) must exist in Polish and
English.

**Decision.** Translated fields use django-modeltranslation, with one column per language (`name_pl`,
`name_en`). If the requested translation is empty, the `pl` value is returned. The admin shows language
tabs. `core.serializers.TranslatedModelSerializer` returns one string in the request language. It is
meant for reads only; content is edited in the admin.

**Alternatives.** A JSON field per model. Not chosen by the maintainer; the reasons are not recorded
here.

**Consequences.**
- Each new translated field adds one column per language and a migration.
- API responses contain one language. Admin-only endpoints are the exception (see `docs/api.md`).
- The API does not offer writes for translated content.

## 8. API errors are translated, `error.code` is not

**Status:** accepted (2026-11-14)

**Context.** DRF's messages for parser failures, CSRF failures and 429 are untranslated or poor in
Polish. DRF and Django defaults (404, 405, 415, validation messages) would also show English to Polish
users.

**Decision.** Our own translated messages cover parser failures, CSRF failures, 429, and the default
404, 405, 415 and validation messages. `handler400` and `handler403` are set in the URL config.
`error.code` is a stable identifier and is never translated. The Polish catalogue
(`backend/locale/pl`) extends DRF's and includes Polish plural forms. `core/drf_messages.py` exists
only so `makemessages` picks up DRF's strings; it is not used at runtime.

**Alternatives.** Keep DRF's default messages. Rejected for the reasons in the context.

**Consequences.**
- Clients must use `error.code` for logic. `error.message` and `error.details` are for display.
- After editing a `.po` file, compile it again (see entry 2).

## 9. Frontend locale and date formatting

**Status:** accepted (2026-11-14)

**Context.** A first visit must follow the browser language. Transit times must match the city's
timetable, not the timezone of the device.

**Decision.** The locale is the stored choice, then `navigator.languages`, then `pl`. The detected
language is not saved, so it follows the browser until the user chooses. `<html lang>` is set on
startup. Dates, times and numbers are formatted through `useFormat()` (`frontend/src/i18n/format.ts`).
Times always use the city's timezone. English uses the vue-i18n `en` locale: US date style and 24-hour
times. `DEFAULT_TIME_ZONE` is only a fallback until the city details are loaded.

**Alternatives.** Format with the browser's timezone. Not chosen; the reasons are not recorded here.

**Consequences.**
- New date, time or number displays should use `useFormat()`, not direct `Intl` or `toLocale*` calls.
- Until the city details load, times use the fallback timezone.
- An en-GB date style is not offered yet (optional follow-up).

## 10. Static GTFS is stored as versioned rows, loaded with COPY

**Status:** accepted (2026-11-14)

**Context.** Timetables (#9, #10) and journey data need the static GTFS feeds in PostgreSQL. The
feeds are large: Warsaw ZTM has about 7.4 million stop times and Kraków bus about 1.8 million. A new
feed must not replace the active data until it is fully loaded and checked.

**Decision.** Each import creates a `FeedVersion` row. All static rows (stops, routes, calendars,
shapes, trips, stop times, frequencies) point to their version. The import runs in one transaction and
then switches the feed's active version. Rows are written with PostgreSQL `COPY` (psycopg), not with
ORM `bulk_create`. GTFS ids are stored as strings. Times are seconds since midnight of the service
day, so values above 24:00 are allowed. `route_type` is stored as the raw number, and a separate
`vehicle_type` maps it, including the extended types (Kraków trams use 900). `stop_times` has no
database foreign key to `trips` or `stops`; the importer checks references and records skipped rows.
An advisory lock per city and feed stops two imports of the same feed from running at once.

**Alternatives.** ORM `bulk_create`: too slow for this volume (the reason for `COPY`). The reasons
for the other choices are not recorded here.

**Consequences.**
- Measured on the real feeds: about 90,000 stop times per second, 210 MB peak memory, about 3.5 GB of
  database with the active and one previous version.
- Old versions are removed by a retention rule (see `docs/architecture.md`).
- Integrity of `stop_times` is the importer's job. A bad row is skipped and listed in the report.
- The `StopTime` admin filter by feed version is not indexed yet (follow-up).

## 11. Failed imports: retry transient errors, skip only repeated data errors

**Status:** accepted (2026-11-14)

**Context.** The first version skipped any new download whose sha256 matched the last failed
import. A transient failure (interrupted run, database error, time limit) then blocked the next
nights too. One bad night could leave a city's timetable stale for good. A separate risk: a feed
cut by more than half would silently replace good data.

**Decision.** `FeedVersion.data_error` is true only for `GtfsFormatError` and `FeedRejected`. The same
sha256 is not imported again only when the last failed import was a data error. Any other failure is retried on
the next run. A new version whose trips or stop times are below 50% of the active version is
rejected. `--force` bypasses that check. Only the last 5 failed versions are kept
per feed; they hold no data.

**Alternatives.** Skip every sha256 that failed before. Rejected by review: it can hide a transient
failure forever. Accept any size change. Rejected: a truncated feed would replace good data.

**Consequences.**
- A legitimate timetable cut of more than half is rejected every night until someone runs `--force`.
  Only a log warning shows this. Monitoring is a follow-up.
- Unlock and failure recording do not hide the original error.

## 12. Warsaw uses the community mkuran.pl feed, not the official ZTM GTFS

**Status:** accepted (2026-11-14)

**Context.** Warsaw has two GTFS sources. The community feed `mkuran.pl/gtfs/warsaw.zip` is built
from ZTM Warszawa data. The official ZTM feed (`gtfs.ztm.waw.pl/last`) is published by ZTM itself.

**Decision.** Warsaw stays on the mkuran.pl feed (`ztm`). The official feed is kept as the fallback.

Reasons from the research (#38):
- The official feed has no metro, covers 10 days only, prefixes route and trip ids with the day, and
  has no stations or accessibility data. It does not send an ETag.
- - The official feed does include Koleje Mazowieckie, WKD and SKM. This is noted as a candidate for
  the national rail issue (#43).

**Alternatives.** The official ZTM feed. Rejected for now for the reasons above.

**Consequences.**
- Risk: the mkuran feed is maintained by one person. The importer keeps the last good version
  and warns 14 days before the feed expires.
- Fallback if the feed stops: point the `ztm` URL in `backend/cities/config/warszawa.yaml` to the
  official feed. Its content differs (see above), so check the import report after the switch.

## 13. Feed licences and attribution

**Status:** accepted (2026-11-14). Verified by the data agent (#38) and read by the maintainer.

**Context.** The app shows and processes public transport data from several publishers. Each
publisher sets its own attribution rule.

**Decision.** Each city config lists its attributions. The new optional `licence_url` field is
allowed there. The facts per source:

| Source | Licence | Attribution |
|---|---|---|
| ZTP Kraków (GTFS, GTFS-RT) | CC BY 4.0 | Name the publisher and the licence |
| WKD feed (via mkuran.pl) | CC0 1.0 | None required. mkuran asks to show all names in `attributions.txt` |
| ZTM Warszawa (via mkuran.pl) | ZTM terms: free reuse, including processing and public display | No attribution text required. The reuser is responsible for data currency |
| Warsaw open data API (UM Warszawa) | Warsaw open data terms | State the source, when the data was created and retrieved, and that it was processed |
| OpenStreetMap | ODbL | Added to both cities |

The Warsaw open data API is used by #20; the attribution page is #25.

**Alternatives.** Hard-code the attribution text in the frontend. Rejected: city values belong in
city config (see decision 1).

**Consequences.**
- The attribution list must be shown in the app before a public release (#25). Attributions are
  internal fields in the city config and are not exposed by the API yet.
- `UM_WARSZAWA_API_KEY` is in `.env.example` and compose, empty. Its resource id is not confirmed
  (#20).
- Re-check the licence text when a publisher changes its terms.

## 14. One OpenTripPlanner instance per city

**Status:** accepted (2026-11-14)

**Context.** OpenTripPlanner 2 serves exactly one graph per instance. The app covers two cities
with separate feeds and separate OSM extracts.

**Decision.** Each city runs its own OTP 2.6 service: `otp-krakow` on 127.0.0.1:8080 and
`otp-warszawa` on 127.0.0.1:8081, both under the `otp` compose profile. Each has its own data
directory, `otp/data/<city>/`, and its own one-shot build service under the `otp-build` profile.
The backend finds each instance through `cities.registry.get_otp_url(city)`, which reads
`OTP_URL_KRAKOW` or `OTP_URL_WARSZAWA`.

**Alternatives.** One combined graph for both cities in one instance. Not possible with OTP 2,
which serves one graph per instance.

**Consequences.**
- Two containers, two ports and two graph builds. Each city is built separately.
- Heap is set per city and per phase: build 4G (Kraków) and 7G (Warsaw); serve 2G and 3G.
- The old single `OTP_URL` setting is removed.

## 15. Clip the OSM extract with the osmium-tool CLI in the backend image

**Status:** accepted (2026-11-14)

**Context.** The Geofabrik regional extracts are large: Małopolska is 204 MB and Mazowsze is 302 MB.
A graph for the whole region needs more heap and build time than the served area requires. The
clip must keep whole ways at the border, so that streets are not cut.

**Decision.** `prepare_otp_inputs` clips the regional extract with
`osmium extract --strategy complete_ways` to the bounding box of all GTFS stops plus 3 km
(`OTP_BBOX_BUFFER_KM`). A city config can set `otp.bbox`. The `osmium-tool` package is installed in
the backend image. `OTP_OSMIUM_BIN` names the binary.

**Alternatives.**
- pyosmium. It has no equivalent of `extract` with `complete_ways`.
- No clip (`--no-clip`). It works, but needs more heap and build time.

**Consequences.**
- The clip result is 72 MB for Kraków (from 204 MB) and 134 MB for Warsaw (from 302 MB).
- The real clip test does not run in CI yet, because the CI image has no `osmium-tool`. Adding it to
  the CI apt list is a follow-up.
- A bad stop can widen the bbox. `prepare_otp_inputs` warns when the bbox is wider than 2 degrees
  or reaches beyond the extract.

## 16. No bicycle transfers in the transfer pre-computation

**Status:** accepted (2026-11-14)

**Context.** OTP pre-computes transfers between stops when it builds the graph. With bicycle
transfers of up to 30 minutes, the Kraków build used 6.4 GB RSS, made about 10 times more transfers
and produced a 343 MB graph.

**Decision.** Transfers are walking, plus wheelchair, capped at 15 minutes. Bicycle transfers are
not in the build configuration (`otp/config/build-config.json`).

**Alternatives.** Bicycle transfers with a 30-minute cap. Not chosen; the measured cost is in the context above.

**Consequences.**
- Journeys that need a bicycle transfer between stops are not found by OTP.
- The build fits in the heap sizes above (Kraków peak 3.5 GB RSS, Warsaw peak 7.4 GB RSS).
- The decision can be revisited with more memory or a shorter cap.

## 17. Graph rebuild is manual for now

**Status:** accepted (2026-11-14)

**Context.** The graph is built from the static GTFS feeds and the OSM extract. The Warsaw feed is a
rolling window, so the graph goes out of date each day. A build takes 4 to 8 minutes and up to 7.4 GB
of memory.

**Decision.** The rebuild is a manual step: `make otp-build CITY=<city>`, or the three raw compose
commands in the README. The scheduled rebuild is a follow-up.

**Alternatives.** A scheduled rebuild in Celery beat. Not built yet.

**Consequences.**
- Until the next rebuild, OTP plans journeys on the old timetable.
- A rebuild restarts the service. It is not zero-downtime.

## 18. National rail: one mkuran.pl feed, cut to each city's area at import

**Status:** accepted (2026-11-14)

**Context.** National rail was missing from both cities' timetables and graphs. It was split out of
#7 as #43. The national feed covers the whole country, but each city needs only its own area.

**Decision.** Both cities use one feed, `rail` (`https://mkuran.pl/gtfs/polish_trains.zip`, "Polish
Trains" by mkuran.pl). It is about 26 MB, rebuilt daily, covers a 30-day window and has 13 agencies.
Each city cuts it with an optional `filter` in its city config: `bbox` and, for Warsaw,
`exclude_agencies: [SKM]`. Kraków bbox `[19.55, 49.88, 20.40, 50.27]`; Warsaw bbox
`[20.55, 51.90, 21.50, 52.52]`. SKM is already in the `ztm` feed. The cut rules are in
`docs/architecture.md` (static GTFS import). OTP inputs use the same cut feed.

**Alternatives.** The alternatives considered for #43 are not recorded here.

**Consequences.**
- Measured on the real feed: Kraków 248 stops, 1,721 trips; Warsaw 447 stops, 8,412 trips.
- Rail has static timetables only. Its realtime updates are not in scope.
- The same single-maintainer risk as entry 12 applies to this feed.
- A changed `filter` forces a re-import. A failed or empty cut fails the version; the active version stays.
- Graphs built before this change have no rail until they are rebuilt (see entry 17).
- Attribution for this feed is in entry 19.

## 19. Rail licences: PKP PLK processing notice not acted on for now

**Status:** accepted (2026-11-14, decided by the maintainer)

**Context.** The Polish Trains feed contains data from PKP PLK and Koleje Mazowieckie (KM). Their
public-sector reuse terms ask that the source, the creation or retrieval time and the fact that the
data was processed are stated. PKP PLK's terms also ask to be informed about processing. KM's terms
have a clause on use "in its originally obtained form".

**Decision.**
1. The PKP PLK notice about processing is not acted on. This is a private, non-commercial project.
   Revisit before any public use.
2. The KM clause "in its originally obtained form" is accepted as written.
3. Both cities' configs list the three attributions from the feed's `attributions.txt`: PKP PLK,
   Mikołaj Kuranowski (Polish Trains GTFS) and Koleje Mazowieckie. They will be shown on the data
   sources page (#25).

**Alternatives.** Inform PKP PLK before processing. Not done for now (point 1).

**Consequences.**
- Before any public release, revisit point 1 and check the attribution text.
- The licence strings in the city configs are English sentences. #25 needs translated text or short
  codes to show them in the app.

## 20. Timetable ids are `{feed_id}:{gtfs_id}`

**Status:** accepted (2026-11-15, #10)

**Context.** A city has several feeds, and GTFS ids are only unique within one feed. Clients also keep
ids in URLs.

**Decision.** `line_id`, `stop_id` and `trip_id` are `{feed_id}:{gtfs_id}`. Clients treat them as opaque
strings and URL-encode them.

**Alternatives.** Plain GTFS ids: may collide across feeds of the same city.

**Consequences.** Ids stay the same across re-imports of the same feed. Ids are unique within a city.

## 21. Holidays count as Sunday, found from the active services

**Status:** accepted (2026-11-15, #10)

**Context.** The timetable needs a day type for holidays. Holidays are not in the feed as a day type.

**Decision.** A weekday or Saturday whose set of active services equals the set of the nearest Sunday is
treated as `sunday`. No holiday list is hard-coded, so it works for any city.

**Consequences.** It depends on the feed's calendar. Warsaw's rule is not yet checked on a weekday holiday
inside the feed window (see the follow-ups in the log).

## 22. GTFS `route_color` FFFFFF and 000000 count as unset

**Status:** accepted (2026-11-15, #10)

**Context.** The Kraków bus feed uses white and black as placeholder colours.

**Decision.** A `route_color` of `FFFFFF` or `000000` is ignored. The group colour is used instead.

**Consequences.** A line that really is white or black in GTFS gets the group colour.

## 23. The last stop of a trip is not in stop timetables

**Status:** accepted (2026-11-15, #10)

**Context.** A departure from the last stop of a trip is not a passenger departure.

**Decision.** Stop times at the last stop of a trip are left out of stop timetables. At a terminus the
response is `200` with empty columns.

**Consequences.** The trip view still shows the last stop.

## 24. Frequency trips are expanded per headway; the trip view shows the template

**Status:** accepted (2026-11-15, #10)

**Context.** Some feeds (for example Warsaw metro) describe runs with `frequencies.txt` instead of one trip
per run.

**Decision.** Stop timetables expand each frequency into one departure per headway. The trip id is the
template trip, so the trip view shows the template's times.

**Consequences.** A trip view for a frequency-based run does not show that run's own times. Trip identity
for these runs is a follow-up.

## 25. Stop-to-routes transfer lookup is cached for 24 h, keyed by stop row id

**Status:** accepted (2026-11-15, #10)

**Context.** The transfers of a line diagram need a lookup from stop to routes. It is the same for all
users until the next import.

**Decision.** Cache it in the Django cache for 24 h, keyed by stop row id. Each import creates new rows and
so new ids, so an old entry is never read after an import.

**Consequences.** After an import, the first request for a stop rebuilds its entry. A precomputed table is a
follow-up (data agent).

## 26. MapLibre worker URL is set explicitly

**Status:** accepted (2026-11-15, #11)

**Context.** Under Vite, dependency pre-bundling dropped MapLibre's worker file. The GeoJSON layers did not
render in the browser. Unit tests mock MapLibre, so they did not catch it.

**Decision.** Import the worker file with `?url` and pass it to `setWorkerUrl`, in `frontend/src/config/mapWorker.ts`.

**Consequences.** The map needs a browser smoke test before a manual test. Unit tests cannot show this.

## 27. Default direction is the lowest direction the line has

**Status:** accepted (2026-11-15, #10)

**Context.** Some lines have only direction `1`, and the direction parameter is optional.

**Decision.** When `direction` is omitted, the line route and stop timetable use the lowest direction that
exists for the line. `0` is used when it exists.

**Consequences.** A line with only direction `1` opens on `1`. Trips without `direction_id` count as `0`.

---

## 28. OpenTripPlanner is queried with GraphQL through the standard library

**Status:** accepted (2026-11-15, #12)

**Context.** Journey search needs three GraphQL `planConnection` queries (transit, walk, bike) per request, to one
OTP endpoint, `/otp/gtfs/v1`.

**Decision.** `backend/journeys/otp.py` posts the queries with Python's `urllib`. The timeout is
`OTP_TIMEOUT_SECONDS` (10 s). Any failure (network, timeout, HTTP error, bad response) becomes `503
journey_planner_unavailable`, and OTP's messages are not returned to the client. The three queries run in parallel
in `services.py`.

**Alternatives.** A GraphQL client library. The reasons it was not chosen are not recorded here.

**Consequences.**
- No new dependency.
- Every failure gives the same `503` to the client, so the client cannot tell a timeout from an OTP error.

## 29. Stop search is in memory, with diacritics folding

**Status:** accepted (2026-11-15, #59)

**Context.** The journey form needs stop-name autocomplete. Users type names without Polish diacritics (`zabl`
for `Żabłocie`). A PostgreSQL `unaccent` extension would need a migration. That migration belongs to the data
agent's area, and was not part of this feature.

**Decision.** `GET /cities/{city}/stops/?q=` matches in Python, in `backend/timetable/stops.py`. Names are compared
without diacritics, `ł` is folded to `l`, and word-prefix matches rank first. Platforms with the same name within
300 m are one result, at most 20 results. The stop list is cached for 24 h, keyed by the active feed versions.

**Alternatives.** A PostgreSQL search with `unaccent` or a trigram index, as a migration. Not chosen for this
feature; the reasons are not recorded here.

**Consequences.**
- The stop list of a city is held in the cache for 24 h. Memory use under load is not measured.
- A new import starts a new cache entry, so search does not use the old version's stops.
- Revisit with a database search if the memory cost or the ranking needs grow.
- Redis is not yet the Django cache backend (follow-up, devops).

## 30. Wheelchair is a preference, not a filter

**Status:** accepted (2026-11-15, #12)

**Context.** Users who need step-free trips want them first. Excluding every inaccessible stop or trip could leave
no route. Some GTFS stops have unknown wheelchair boarding (`wheelchair_boarding` is `null`).

**Decision.** The `wheelchair` preference makes OTP prefer accessible trips and stops. The OTP router config sets
`onlyConsiderAccessible` to false, so inaccessible options are penalised, not removed.

**Alternatives.** A strict option that excludes inaccessible options. Not built; it is a follow-up.

**Consequences.**
- An itinerary can still use an inaccessible stop or vehicle. The response does not flag this yet.
- A strict wheelchair option is a separate, later change.

## 31. No address geocoding in the MVP

**Status:** accepted (2026-11-15, #13)

**Context.** Journey points can be a stop, a map point or the user's location. Typing a street address needs a
geocoder, which is an extra external service with its own terms and cost.

**Decision.** The MVP has no address search. `from` and `to` are stops from the stop search, points picked on the
map, or the browser's location. The API accepts `{ "stop_id" }` or `{ "lat", "lon" }`.

**Alternatives.** An external geocoding service. Not chosen for the MVP; the reasons are not recorded here.

**Consequences.**
- Users cannot type a street address. They pick a stop or a point on the map.
- Address geocoding is a follow-up, and it needs its own decision record when it is added.

## 32. Stateless chat with no database table

**Status:** accepted (2026-11-15, #18)

**Context.** The assistant answers questions in a browser session. Accounts (#15) are planned, not built, so
there is no user to attach a history to.

**Decision.** `POST /api/v1/assistant/chat/` keeps no state. The browser keeps the conversation in
`sessionStorage` and sends the last 20 messages with each request. The `assistant` app has no models and no
migrations.

**Alternatives.** Store conversations in PostgreSQL, keyed by a session or user. Not chosen for this feature;
the reasons are not recorded here.

**Consequences.**
- Chat history is lost when the browser tab closes, and it is not visible on another device.
- The server keeps no conversation data to review or delete.
- Stored history, if wanted later, needs its own decision record.

## 33. Chat language comes from `Accept-Language`

**Status:** accepted (2026-11-15, #18)

**Context.** Decision 6 makes `Accept-Language` the only language source for the API. An earlier draft of the chat
contract had a `language` field in the request body, which would be a second source.

**Decision.** The answer is written in the language negotiated from `Accept-Language`, whatever language the
question is in. The request body has no `language` field. The rules are in `docs/api.md`, section "Language
negotiation".

**Alternatives.** A `language` body field (`pl` or `en`). Not chosen, because it would be a second language source.

**Consequences.**
- The client must send the `Accept-Language` header, as it does for every other endpoint.
- A question in English sent with `Accept-Language: pl` gets a Polish answer.

## 34. Departures cards carry a `stop_id` per departure

**Status:** accepted (2026-11-15, #18, #19)

**Context.** A departures card shows one stop group, and the card's `stop.stop_id` is the group's representative
platform. Departures can leave from other platforms of the same group. The AI agent found that the contract had no
per-departure stop, so a link to the stop timetable could point to the wrong platform.

**Decision.** Each departure in a `departures` card has its own `stop_id`, the platform it leaves from. The link to
the stop timetable uses that `stop_id`, together with `line.id` and `direction`.

**Alternatives.** Use the card's representative `stop_id` for every departure. Rejected: the links can point to the
wrong platform. The first frontend version did this; the tester found it and it was fixed.

**Consequences.**
- The departure object is larger by one field.
- The contract gap was resolved in `docs/api.md` by the coordinator.

## 35. Unchanged feed polls count as fresh

**Status:** accepted (2026-11-15, #73)

**Context.** The collector stores status `unchanged` when a feed's header timestamp equals the one of the last
poll. The feed has not changed, so the stored times are still the latest. The departures board needs a rule for
when live data is fresh.

**Decision.** A `FeedFetch` with status `unchanged` counts as fresh, like `ok`. Any other status is not fresh.

**Alternatives.** Count only `ok` as fresh. The reasons are not recorded here.

**Consequences.**
- A feed that answers `unchanged` on every poll keeps the board live.
- Freshness depends on the last successful poll, not on when the data last changed.

## 36. ZTP delay 0 is shown as live on time

**Status:** accepted (2026-11-15, #73)

**Context.** ZTP sends a prediction for every upcoming stop, so a delay of 0 is a prediction that the vehicle is on
time. The scheduled time is not in the feed, so the board needs a rule for which time to show.

**Decision.** When the feed gives both a time and a delay, the board uses the feed's time and delay. A live
departure with delay 0 is shown as "on time" with the live marker, not as scheduled.

**Alternatives.** Show a delay of 0 as scheduled. Rejected: every predicted ZTP departure would then look scheduled.

**Consequences.**
- "On time" means the feed predicted it. It is not inferred from the timetable.
- Bus last-stop departures with time 0 and delay 0 are still treated as missing (see `docs/architecture.md`).

## 37. Live events match by stop sequence, with a stop fallback

**Status:** accepted (2026-11-15, #73)

**Context.** A trip can call at the same stop twice, for example on a loop. Matching on trip and stop only can
attach a live time to the wrong call. Bus updates carry `stop_sequence` for about 14–20% of updates. Tram updates
carry none.

**Decision.** A live event matches a scheduled call by trip and `stop_sequence`. If either side has no
`stop_sequence`, the match uses the stop. An event with a different, non-null `stop_sequence` never matches.

**Alternatives.** Match on trip and stop only. Rejected: review found that a loop trip could take the wrong time.

**Consequences.**
- Tram events, and bus events without a sequence, match by stop. On a loop trip they can still match the wrong call.
- A bus event that has a sequence matches only its own call.

## 38. Realtime feeds link to one static feed each

**Status:** accepted (2026-11-15, #73)

**Context.** Kraków tram and bus trip ids follow the same pattern. A trip id alone can match a trip in the other
feed.

**Decision.** Each `gtfs_rt` feed with entity `trip_updates` sets `static_feed` to the id of its `gtfs_static` feed.
Trip matching uses only that pair. `static_feed` is required when `realtime.departures` is true. The registry
rejects a missing value at startup.

**Alternatives.** Match trip ids across all static feeds of the city. Rejected: the shared id pattern gives false
matches.

**Consequences.**
- A new realtime feed needs a `static_feed` entry in its city config.
- A feed without `static_feed` is allowed only while `realtime.departures` is off.

## 39. Stop overview counts directions in one aggregate with a 24 h cache

**Status:** accepted (2026-11-15, #9)

**Context.** The stop view needs every line at a stop with its directions. Counting per line would mean one query
per line, about 24 at Rondo Mogilskie. Line names and colours change with the city config, not with the feed.

**Decision.** One SQL aggregate (`GROUPING SETS`) counts distinct departing trips per line, direction, platform and
headsign. A trip departs when a later stop exists and its pickup type is not 1, as in the departures board and the
stop timetable. The directions per route are cached for 24 h, keyed by city, active feed version ids and the group's
representative stop. Line summaries, groups and colours are read from the city config on every request.

**Alternatives.** Derive the lines from the departures board: rejected, it shows only the next departures, not all
lines. One request per line from the frontend: rejected, more round trips. Cache the whole response: rejected, a
config change would show late.

**Consequences.**
- A new import starts a new cache entry. Config changes show at once.
- Kraków measured: about 1.7 s cold and 52 ms warm. Warsaw not measured locally.
- Tests for config changes while cached and for unknown route suffixes are a follow-up.
