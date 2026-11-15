# AI workflow log

One entry per feature, newest first. Written by the `docs` agent from the agents' reports,
the reviewer's verdicts and the maintainer's manual-test feedback.

<!-- Template — copy for each new entry
## <Feature name> — <YYYY-MM-DD>
**Issues / PRs:** #N, #M
**Branches:** feat/N-slug, feat/M-slug

| Agent | What it did | Result |
|---|---|---|
| backend | … | … |
| frontend | … | … |
| tester | … tests added, … passing | … |
| reviewer | rounds: N | APPROVED / CHANGES REQUESTED → fixed |

**Review findings that mattered:** …
**Manual test (maintainer):** what was checked, what was changed or rejected and why.
**Problems and lessons:** what went wrong with the agents and how the process or prompts were adjusted.
-->

## Data sources — 2026-11-15
**Issues / PRs:** #25, #29 (PRs: pending)
**Branches:** feat/25-data-sources-endpoint, feat/29-data-sources-page; integration worktree `integration/data-sources` for the manual test

| Agent | What it did | Result |
|---|---|---|
| coordinator | Picked data sources in the agreed MVP order (after the AI chat). Wrote the contract in `docs/api.md` first (uncommitted) and passed it to the agents as a file in the scratchpad, because worktrees do not see uncommitted files. Added data freshness (`last_modified` = created, `downloaded_at` = retrieved), because PKP PLK, Koleje Mazowieckie and Warsaw open data terms require stating when data was created and retrieved, and that it was processed. The "processed" statement is static i18n text. | Done. |
| backend (#25) | `GET /api/v1/data-sources/` in the `cities` app. Optional `descriptions: {pl, en}` per attribution in city config (validated, both languages required). Descriptions added to all 13 attributions. HTTP `Last-Modified` parsed to ISO 8601 (`null` if unparsable). Timestamps in the city timezone. One query. Only active feed versions of feeds still in config. No internal fields. No new translations or migrations. | Done. |
| frontend (#29) | `DataSourcesView` replaces the placeholder. Processed-data notice. Per-city sections, current city first, with sources and data freshness. Locale-formatted dates. Loading, error with retry, and empty states. Re-fetch on language change. Accessible headings and external links. Phone layout. pl and en keys. | Done. |
| tester (#25) | Backend `test_data_sources.py`, 52 cases. Full backend suite 1257 passed. | Passing. |
| tester (#29) | Frontend `dataSourcesView.test.ts`, 18 tests. Full Vitest 347 passed. Type-check and lint clean. | Passing. |
| reviewer (#25) | Rounds: 1. | APPROVED, no blocking findings. |
| reviewer (#29) | Rounds: 1. | APPROVED, no blocking findings. |

**Review findings that mattered:**
- Frontend, should-fix, deferred: feed dates are formatted in the selected city's timezone, not the feed's city. Both cities share one zone today.
- Nits, deferred: ZTP description wording ("real-time vehicle data" could name positions, delays and alerts); move `parse_http_date` to core utils; tighten the query count test to 1; merge the duplicate licence link markup; use `section` or `role="note"` instead of `aside` for the notice.

**Manual test (maintainer):** OK, approved on the `integration/data-sources` worktree.

**Problems and lessons:**
- No new problems. Passing the uncommitted contract as a scratchpad file worked.
- Each agent finished in one round. No fix rounds were needed.

**Follow-ups:**
- The deferred should-fix and nits above.
- PKP PLK must be told about the processing. This is done by the maintainer, outside the app.

## Journey search — 2026-11-15
**Issues / PRs:** #12, #13, #59 (PRs: pending)
**Branches:** feat/12-journey-search-endpoint, feat/13-journey-search-ui, feat/59-stop-search; integration worktree `integration/journeys` for the manual test

| Agent | What it did | Result |
|---|---|---|
| coordinator | Wrote the contract for #12 and #59 in `docs/api.md` first (uncommitted) and passed the paths to the agents. Built the integration worktree by applying the three uncommitted diffs; `.po` conflicts were resolved by hand and `.mo` recompiled. | Done. |
| backend (#12) | New `journeys` app: OTP GraphQL client on `urllib`, polyline decoding, parallel transit, walk and bike queries, stop ids resolved to coordinates, modes limited to the city's vehicle types, bbox check, line summary reused from the timetable. | Done. 67 journeys tests; full suite passing. |
| backend (#59) | `GET /cities/{city}/stops/?q=` in `timetable/stops.py`: in-memory matching without diacritics, word-prefix ranking, grouping within 300 m, max 20, 24 h cache keyed by active feed versions. No `unaccent` migration. | Done. Checked on real Warsaw data: no platform codes in stop names, so grouping works. |
| frontend (#13) | Home map with a floating panel (desktop) or top panel and bottom tab bar (phone); `/journey` redirects to `/`. Stop autocomplete, map picking, my location, swap, depart or arrive time, preferences, results with route on the map, walk and bike comparison, error states (503, 429, network, 400). The Pinia store keeps the search across navigation. | Done. Vitest 329/329 passing. |
| reviewer (#12) | APPROVED. | Should-fix done: `http.client.HTTPException` now returns 503. |
| reviewer (#13) | APPROVED. | Fixed: stale selection after Enter, results cleared on place change, generic 400 message, focus handling in map picking. |
| reviewer (#59) | APPROVED. | Should-fix listed: `q` max length, Redis as Django cache (devops), make `_routes_at_stops` public. Status not recorded. |

**Review findings that mattered:**
- #13: a stale selection could be used after Enter, and results stayed after the place changed. Both fixed.
- #12: an `http.client` error was not mapped to 503. Fixed.
- #59: the reviewer asked for a `q` length limit and for Redis as the Django cache, which is a devops task.

**Manual test (maintainer):** OK, approved, on the `integration/journeys` worktree (2026-11-15).

**Problems and lessons:**
- The path hook blocked the backend and frontend agents from writing tests and `docs/api.md`. The tester and the coordinator wrote them, and the agents spent time on temporary specs. The guard works as intended, but it costs a round trip.
- Copying `.env` into the integration worktree was denied for the coordinator, so Piotr ran the stack.
- Applying the three uncommitted diffs to one worktree gave `.po` conflicts, resolved by hand, and the `.mo` files were recompiled.

**Follow-ups:**
- Address geocoding (planned; needs its own decision record).
- Rate limit on the journey endpoint (`AnonRateThrottle`) before public deployment.
- Show the date on result times for other days.
- Strict wheelchair option.
- Tests for the four frontend fix-round behaviours.
- #59 should-fixes: `q` max length, Redis as Django cache (devops), public `_routes_at_stops`.
- #13 should-fix left: skeleton colour tokens.
- #51: nightly OTP graph rebuilds.

## Timetable browser — 2026-11-15
**Issues / PRs:** #10, #11 (PRs: pending); #56 split off from #11 (new, not started)
**Branches:** feat/10-timetable-endpoints, feat/11-timetable-browser; integration worktree `integration/timetable-11` for the manual test

| Agent | What it did | Result |
|---|---|---|
| coordinator | Scoped the session to #10 and #11. The stop entry moved to #56 (depends on #9) because of the 2026-11-15 deadline. Wrote the contract in `docs/api.md` first. Agents read it from the main checkout, because worktrees do not see uncommitted files. Updated the contract during the work: white and black colour rule, `direction_id` null counts as 0, `code`, `lat` and `lon` nullable, last stop excluded, frequency expansion, default direction = lowest existing, date lower bound. Found the MapLibre worker problem in a browser smoke test. | Done. |
| backend (#10) | New `timetable` app. Line groups in the city YAML with validation. Calendar and day types, including the holiday rule. Variants (main, short_turn, depot, other) via SQL `array_agg`. Transfers within 300 m. Frequency expansion. Checked on real Kraków and Warsaw data in a separate DB (`ljd_timetable`): 20–110 ms per request, no N+1. Fixes: colour rule, blank-headsign fallback, review fixes. | Done. |
| frontend (#11) | Tabs. Line grid with groups and search. Line page with direction toggle, diagram, route map. Stop timetable with three columns, markers and legend, date picker, trip dialog, print CSS. Polish and English. Fixes after review and after the MapLibre fix below. | Done. |
| tester (#10) | Backend 199 + 13 new tests (fictional city `ttville`). Full backend suite 1095 passed. | Passing. |
| tester (#11) | Frontend 100 + 12 new tests. Full frontend suite 235 passed. | Passing. |
| reviewer (#10) | Rounds: 1. | APPROVED with 5 should-fix. Fixed: date lower bound and default direction. Added an OpenAPI schema test. The Warsaw holiday rule is left to the manual check. |
| reviewer (#11) | Rounds: 1. | APPROVED with 8 should-fix. 6 fixed (listed below). |

**Review findings that mattered:**
- Backend, tester: a blank headsign had no fallback. Fixed (headsign falls back to the last stop name).
- Backend, colour rule: `FFFFFF` and `000000` route colours treated as unset. Fixed.
- Backend, reviewer: date lower bound changed from 500 to 400. Default direction fixed.
- Frontend, reviewer, fixed: the opposite-direction notice was lost; controls unmounted on reload; the next departure after midnight was wrong; duplicate keys; the direction switch was not abortable; the opposite-direction button stayed visible after a 404.
- Frontend, coordinator (browser smoke test): MapLibre's worker failed to load under Vite, so GeoJSON layers did not render. Fixed with `setWorkerUrl`. Unit tests mock MapLibre and did not catch it.

**Manual test (maintainer):** OK, on the integration worktree.

**Problems and lessons:**
- Vite pre-bundling breaks MapLibre's worker URL. It is only visible in a real browser. Run a browser smoke test before the manual gate.
- The path hook blocks code agents from editing tests. Test updates after a fix go back to `tester`.
- The backend image lacked `django-modeltranslation`. It needed a rebuild with `--build`.
- Windows refused host port 5432. `DB_PORT` and `REDIS_PORT` overrides (55432, 56379) were used.

**Follow-ups:**
- #56 and #9 next, for the timetable (stop entry and departures board).
- City in timetable URLs.
- `opposite_stop` and `long_name` in the contract, to drop an extra request.
- Trip identity for frequency-based runs.
- Precomputed stop-to-routes table (data agent).
- Verify the holiday rule on Warsaw data when a weekday holiday falls in the feed window.
- Drop the `ljd_timetable` database after merge.

## National rail GTFS — 2026-11-14
**Issues / PRs:** #43, #53 (PRs: pending)
**Branches:** feat/43-national-rail-gtfs, ci/53-osmium-in-ci

| Agent | What it did | Result |
|---|---|---|
| coordinator | Picked #43 and #53. #43 was picked because backlog item 7 ("GTFS incl. national rail") was not finished. No API contract change. | Done. |
| data (#43) | Chose the source (mkuran.pl "Polish Trains", one feed `rail` for both cities). Added the area filter, the import pipeline changes, the OTP input prep and the loader fix (stops without coordinates inherit their parent's position). Two fix rounds. | Done. |
| backend (#43) | `FeedFilter` in the city registry, shared `_parse_bbox`, `rail` entries and attributions in both city YAML files. | Done. |
| devops (#53) | Backend CI job installs `osmium-tool`. | Done. |
| tester (#43) | 144 tests. Then +20 tests for coordinate inheritance. Then fixed 8 tests and added 24 new. Full backend run: 884 passed, ruff clean. | Passing. |
| reviewer (#53) | Rounds: 1. | APPROVED. |
| reviewer (#43) | Rounds: 2. | Round 1 APPROVED with should-fixes, applied. Round 2 APPROVED. |

**Review findings that mattered:**
- Tester: the loader skipped platforms without coordinates that the filter had kept. The import failed. Fixed by inheriting the nearest parent's position.
- Reviewer, should-fix, all fixed: removing a `filter` left the cut OTP file trusted through shared metadata (now separate source metadata and cleanup). Clipped trips could start or end untimed (now only timed calls are kept). `agency.txt` was empty for single-agency feeds (now kept whole). The size limit was missing on the OTP path.
- Reviewer, nits, not fixed: a non-integer `stop_sequence` is skipped silently; the OTP path opens the archive twice for the size check; licence strings in the YAML are English sentences and need i18n or short codes for #25.

**Manual test (maintainer):** Approved.

**Problems and lessons:**
- The path guard blocked the data agent from editing `backend/cities/` (registry and city YAML). The cross-area change needed an extra backend run. Plan such splits up front.
- The data agent could not remove a tester's xfail marker, because tests belong to `tester`. Route test edits to `tester`.
- Worktrees have no `.env` (it is git-ignored). The manual test needed a copy of it, plus `DB_PORT=15443` and `REDIS_PORT=16443`, because host port 5432 is blocked.

**Follow-ups:**
- #51: nightly OTP rebuilds. Graphs are not yet rebuilt with rail; re-measure build time and memory.
- #25: data sources page with the rail attributions.
- Rail realtime (Polish Trains updates) is not in scope.
- Confirm #53 is green in CI on the PR.

## OpenTripPlanner graphs — 2026-11-14
**Issues / PRs:** #8, #46, #47 (PRs: pending)
**Branches:** feat/8-otp-graphs, feat/46-otp-city-config, chore/47-otp-compose

| Agent | What it did | Result |
|---|---|---|
| coordinator | Picked #8 (dependencies closed; unblocks journeys #12 and #13). Deferred #43 (national rail) because the source was not chosen. Created #46 (backend: OTP section in city config, because the path guard keeps data out of `backend/cities/`) and #47 (devops). No API contract change: OTP is internal; the journeys endpoint is #12. Fixed the interface (YAML `otp` section, `City.otp`, `get_otp_url`, `OTP_DATA_DIR`) in both prompts so data and backend could work in parallel. Ran an integration worktree combining the three uncommitted branches before the manual test. | Done. |
| data (#8) | Shared OTP config, `prepare_otp_inputs` command, osmium clipping, sample GraphQL queries. Built and served both graphs with plain `docker run`; 5 itineraries per city. Round 2: separate OSM download limits, bbox sanity warnings, absolute osmium paths, `--osm-file` equal to the output rejected, per-city lock. | Done. |
| backend (#46) | `otp` section with strict validation, `get_otp_url`, `OTP_DATA_DIR`. Follow-up: settings aligned with data's code (`OTP_CONFIG_DIR`, `OTP_OSMIUM_BIN`, `OTP_BBOX_BUFFER_KM`); new `env_float` (blank gives the default; nan, inf and negative values raise `ImproperlyConfigured`). | Done. |
| devops (#47) | Per-city serve and build services, osmium-tool in the backend image, Make targets with `CITY` validation, `.env.example`, `.gitignore` for `otp/data/**`, `.gitattributes` (LF for the Makefile), CI env, celery mounts read-only, `mkdir` and `--user` for Linux permissions. | Done. |
| tester (#46) | 65 to 85 tests; cities 146 passing. | Passing. |
| tester (#8) | 102 tests. Integration run: backend 697 passed, 0 skipped (real osmium clip ran), ruff clean. Kraków end to end: prepare 40 s, build 5 min 25 s, 5 itineraries; backend container reaches `otp-krakow`. | Passing. |
| reviewer (#46) | Rounds: 2. | APPROVED in both rounds. |
| reviewer (#8) | Rounds: 1. | APPROVED with should-fixes, applied. |
| reviewer (#47) | Rounds: 1. | APPROVED with should-fixes, applied. |

**Review findings that mattered:**
- A blank `OTP_BBOX_BUFFER_KM=` crashed the settings import (found by tester). It would have broken startup once listed in `.env.example`. Fixed with `env_float`.
- A nan, inf or negative buffer would silently produce a broken clip box. Now rejected at startup.
- Merge order: #47 removes `OTP_URL` from compose, so #46 must be merged first or together.
- Linux: Docker creates bind-mount directories as root, so prepare could not write to them. Fixed with a host `mkdir` and `--user`.
- Risk of CRLF line endings in the Makefile. `.gitattributes` forces LF.
- One bad stop could inflate the clip bbox and the build heap. Now a warning.

**Manual test (maintainer):** Passed, on the integration worktree.

**Problems and lessons:**
- The path guard blocked `backend` from updating a tester-owned test after a settings default change. It was routed to `tester`. The guard works as intended, but it costs a round trip.
- The interface agreed up front still drifted: data needed `OTP_CONFIG_DIR`, `OTP_OSMIUM_BIN` and `OTP_BBOX_BUFFER_KM`, which were not in the original contract. Next time, ask the data agent to list the required settings early.
- There is no `make` on the Windows host, so the Make targets were only dry-run in a container until integration.
- The integration worktree caught nothing new, but gave the maintainer one place to test.

**Follow-ups:**
- Scheduled graph rebuild.
- GTFS-RT updaters in OTP (needs a `static_feed` link on `gtfs_rt` entries in the city config).
- National rail (#43).
- Add `osmium-tool` to the CI apt list so the real clip test runs in CI.

## GTFS import and feed sources — 2026-11-14
**Issues / PRs:** #38 (PR #44), #7 (PR #45), #43 (new issue: national rail, split out of #7)
**Branches:** chore/38-verify-feed-sources, feat/7-gtfs-import

| Agent | What it did | Result |
|---|---|---|
| coordinator | Split national rail out of #7 into #43 and retitled #7 to "Import GTFS feeds for Kraków (ZTP) and Warsaw (ZTM, WKD)". Ran feed research (#38) and the import (#7) in parallel. Forwarded verification findings to the implementing agent during its task. Read the ZTM Warszawa terms in a browser. No API contract change. | Done. |
| data (#38) | Checked every feed URL live on 2026-11-14 (status, content type, GTFS or protobuf content). Found the Mobilis agglomeration bus feeds missing from config. Read the licences. | Done. |
| backend (#38) | Config: Mobilis feeds, optional `licence_url` on attributions, OpenStreetMap attribution for both cities. The collector polls the Mobilis TripUpdates too. | Done. |
| devops (#38) | `UM_WARSZAWA_API_KEY` in `.env.example` and compose (empty; used in #20). | Done. |
| tester (#38) | Collector tests derive the Kraków feeds from config. 306 tests passing. | Passing. |
| reviewer (#38) | Rounds: 1. | APPROVED. Two should-fix comment edits made. |
| data (#7) | Models for static GTFS, `static_gtfs/` pipeline: conditional download, streaming CSV reader, `COPY` loader, versions, advisory lock, retention, `ANALYZE`, import report. Measured the four real feeds. | Done. |
| backend (#7) | `import_all_gtfs` in the Celery beat schedule, read-only admin, optional settings. | Done. |
| devops (#7) | `GTFS_IMPORT_HOUR` and `GTFS_IMPORT_MINUTE` in `.env.example`. | Done. |
| tester (#7) | 190 tests, then 31 more after review. Backend total 508 passing. No production bugs found. | Passing. |
| reviewer (#7) | Rounds: 2. | Round 1 CHANGES REQUESTED, fixed. Round 2 APPROVED. |

**Review findings that mattered:**
- Round 1, blocking, fixed: the rule "same sha256 as the last failed import is skipped" also skipped
  transient failures (interrupted run, database error, time limit). One bad night could leave a city
  stale for good. Fixed with `FeedVersion.data_error`: only data errors are remembered (see `docs/decisions.md`, entry 11).
- Round 1, should-fix, all fixed: temp tables not qualified with `pg_temp` (an unqualified `DROP` could
  drop a real table); stop hierarchy not enforced; no check against the active version (new versions
  below 50% of trips or stop times are rejected, `--force` bypasses); unlock and failure recording could
  hide the original error.
- Round 2: the reviewer required a real-feed re-run. No skipped rows and no corrections in any of the four feeds.

**Manual test (maintainer):**
- #38: Passed. One poll showed tram 242, bus 544 and Mobilis 158 entities.
- #7: Passed. Kraków re-imported with `--force` (versions 15 and 16 imported, old versions deleted). Admin checked.
- Warsaw source: the maintainer kept mkuran.pl instead of the official ZTM feed (see `docs/decisions.md`, entry 12).

**Problems and lessons:**
- The path guard means `data` cannot edit city config under `backend/`. Research went to `data`, edits to `backend`.
- `ztm.waw.pl` blocks `curl` (CloudFront 403). The coordinator read the page in the browser instead.
- Feed size required `COPY`. The ORM `bulk_create` was too slow.
- Parallel compose projects need unique host ports per agent. Used: gtfs7 55432, cfg38 55433, test38 55434, sched7 55435, test7 55436, fix7 55437.
- Docs for #38 were deferred to this one entry (agreed with the maintainer), so the log keeps one entry per feature.

**Follow-ups:**
- Rebase `feat/7-gtfs-import` onto #44 to get the Mobilis feed.
- A legitimate timetable cut of more than 50% is rejected every night until `--force`. Only a log warning; monitoring needed.
- No check for times on the first or last stop, or for monotonic times.
- Raw zip files are not kept; OTP (#8) needs them.
- Stop search is not accent-insensitive (#9).
- `StopTime` admin filter by feed version is not indexed.
- UM Warszawa resource id not confirmed (#20). Attribution page (#25).
- WKD feed data ends around 2026-12-12.
- National rail (#43). The official ZTM feed includes Koleje Mazowieckie, WKD and SKM; candidate for #43.

## Bilingual support (i18n) — 2026-11-14
**Issues / PRs:** #28 (backend), #30 (frontend) (PRs: pending)
**Branches:** feat/28-backend-i18n, feat/30-frontend-i18n

| Agent | What it did | Result |
|---|---|---|
| coordinator | Added the "Language negotiation" contract to `docs/api.md` before implementation. Moved the user `language` field to #15 and account sync to #17 (issue comments). Pasted the contract into the agent prompts, because worktrees do not see uncommitted main changes. | Done. |
| backend (#28) | `AcceptLanguageMiddleware`. Translated errors, including DRF and Django defaults (404, 405, 415, 429, parse errors, validation details). `handler400` and `handler403`. django-modeltranslation and `TranslatedModelSerializer`. Polish catalogue with 25 messages, including Polish plurals. | Done. 217 tests passing at hand-off. |
| frontend (#30) | Browser language detection. `<html lang>` set on startup. Date, time and number formats, `format` helpers and `useFormat` composable (city timezone). Unit strings in both locales. No hard-coded text found in existing components. | Done. 65 tests at hand-off. |
| tester | Backend +70 tests (287 total). Frontend +50 tests (115 total). No production bugs. Corrected its own loose assertion ("1.0 km" was a guess; the actual output is "1 km"). | Passing. |
| reviewer | Rounds: 1 per branch. | Frontend APPROVED, backend APPROVED. All should-fix items fixed. |

**Review findings that mattered:**
- Frontend, fixed: a misleading comment, an undocumented `DEFAULT_TIME_ZONE` fallback, and a loose km assertion (now exact).
- Backend, fixed: Polish "2 elementów" wording, `ParseError` override limited to real parser failures, 429 seconds rounded up (ceil), serializer docstring, and the `details` key format (dotted paths, `non_field_errors`) added to the contract.

**Manual test (maintainer):** Passed on both branches.
**Problems and lessons:**
- The path guard blocks code agents from writing tests. Their own checks ran as temporary files, and the tester re-wrote them as real tests.
- Port 5432 is taken by the main stack (realtime collector). Test stacks ran on `DB_PORT=55432`, `REDIS_PORT=56379`, `BACKEND_PORT=58000`, `FRONTEND_PORT=55173`.
- In PowerShell, `curl` is an alias for `Invoke-WebRequest`. Manual-test instructions must use `curl.exe` and `$env:VAR=...` syntax.
- With `DEBUG=True`, unknown `/api/` URLs return Django's HTML debug 404. This existed before #28.

**Follow-ups:**
- User `language` on the account: #15 (model) and #17 (sync).
- Optional en-GB date style, if the maintainer wants it.

## Kraków realtime collector — 2026-11-14
**Issues / PRs:** #6 (PR: pending)
**Branches:** feat/6-krakow-realtime-collector

| Agent | What it did | Result |
|---|---|---|
| coordinator | Chose #6 over i18n (#28, #30) to start collecting data early, because statistics need weeks of data. No API contract change. Removed a stale agent folder from an earlier session (one empty directory, locked by a process). | Done. |
| data (#6) | New `transit_data` app: Celery beat task, GTFS-RT download and parse, `StopEvent` and `FeedFetch` models, `collect_trip_updates` command. Recorded real `.pb` fixtures and checked the collector live in a scratch compose project. Found and fixed a bug where an empty HTTP body was logged as `ok`. | Done. |
| backend (#6) | Wiring: requirements, `INSTALLED_APPS`, `CELERY_BEAT_SCHEDULE`. Existing tests: 80 passing. | Done. |
| devops (#6) | `.env.example` and compose: `REALTIME_POLL_INTERVAL_SECONDS`. | Done. |
| tester (#6) | Round 1: 77 new tests. Round 2: 42 more. Backend total 217 passing, ruff clean. | Passing. No production bugs found. |
| reviewer (#6) | Rounds: 2. | Round 1 APPROVED with 3 should-fix, 2 fixed and 1 deferred. Round 2 APPROVED. |

**Review findings that mattered:**
- Round 1, fixed: the inferred service date flipped in the middle of a trip across 03:00. Fixed with the 4-hour memory of the stored date (see `docs/decisions.md`, entry 4).
- Round 1, fixed: one bad value rolled back the whole poll. Now only the affected entity or stop update is skipped (see `docs/decisions.md`, entry 5).
- Round 1, deferred by the maintainer to #22: table bloat from daytime upserts.

**Manual test (maintainer):** Approved. Stack run from the worktree. Data was visible in the admin, new fetches arrived about every 30 s, and the first poll stored about 10.8k events. Follow-up after the test: the command output showed UTC while the logs showed local time. Fixed after the test.

**Problems and lessons:**
- PowerShell 5 does not support `&&`. Give Piotr PowerShell instructions one command per block.
- Port 5432 was blocked by Windows again. The worktree stack needed `DB_PORT=55432`. Consider making a non-default `DB_PORT` the documented default.
- Collection runs only while the local stack is up. Long-running collection needs a server (not decided yet).
- Agents created 0-byte bind-mount files in `backend/config/settings/` during verification. Check `git status` before each commit.
- The session paused overnight in the middle of an agent run. It was resumed by messaging the same agent.

**Follow-ups:**
- Table bloat and the deletion job for raw events: #22.
- A feed without a header timestamp is never marked `unchanged` or `stale`. A body-hash fallback is needed.
- A floor for `REALTIME_POLL_INTERVAL_SECONDS` is not set yet.
- Hosting for continuous collection: to discuss.

## CI workflow — 2026-11-11
**Issues / PRs:** #4 (PR: pending)
**Branches:** ci/4-github-actions

| Agent | What it did | Result |
|---|---|---|
| coordinator | Picked #4 as the first backlog item with closed dependencies. No API contract change. This time agents used one worktree, as planned. | Done. |
| devops (#4) | Wrote `.github/workflows/ci.yml` (backend and frontend jobs). Validated locally in containers: frontend 65 tests pass, backend pytest 80 pass. Found 2 ruff SIM117 errors and 1 ruff format issue in `backend/cities/tests/` (tester's area, left untouched). | Done. |
| tester | Fixed the ruff errors (formatting only, no assertions changed). Re-ran every workflow command in containers. | All pass: backend 80, frontend 65, build OK with a size warning for the HomeView chunk (1.07 MB). |
| reviewer | Rounds: 1. | APPROVED, no blocking findings. |

**Review findings that mattered:**
- Should-fix, applied by devops: `pg_isready` uses `-h localhost` (the PostGIS init server listens on the socket only).
- Should-fix, applied by devops: `ubuntu-24.04` pinned.
- Should-fix, applied by devops: `cancel-in-progress` only for PRs.
- Should-fix, applied by devops: JUnit file renamed to `junit.xml` (already gitignored).
- Should-fix, applied by devops: unused `GEMINI_API_KEY` env removed.
- Deliberately skipped: a `.mo` vs `.po` drift check (`compilemessages` output is not byte-stable) and SHA-pinning of actions.

**Manual test (maintainer):** Approved. The maintainer did not find the new files at first. They were in the agent worktree under `.claude/worktrees/`, not in the main checkout.

**Problems and lessons:**
- Tell the maintainer the worktree path, and that changes reach the main folder only after the PR is merged and `git pull` is run.
- devops's follow-up report repeated the ruff failures after the tester had already fixed them (stale context). The coordinator verified the state with `git status`.
- Host port 5432 is blocked on this machine, so local DB checks use a Docker network instead of host ports.

**Follow-ups:**
- The workflow has not yet run on GitHub. The acceptance check "green on PR" is pending.
- HomeView bundle size.
- Consider SHA pinning later.

## City configuration — 2026-11-11
**Issues / PRs:** #5, #35 (PRs: pending)
**Branches:** feat/5-city-config, feat/35-frontend-cities-endpoint

| Agent | What it did | Result |
|---|---|---|
| coordinator | Picked #5 first because the Kraków realtime collector (#6) depends on it. Added the cities contract to `docs/api.md` before implementation. Created #35 because the frontend had hard-coded cities (`TODO(#5)`). | Done. The contract was pasted into the agent prompts, because worktrees branch from `main` and did not contain the uncommitted `docs/api.md`. |
| backend (#5) | `cities` app. YAML registry with strict validation and a process cache (cleared on setting change). Serializers expose only public fields. Both endpoints have OpenAPI annotations. Translated 404. pl/en `.po` and `.mo` files. PyYAML added. | Done. Verified in a temporary container: check, ruff, `spectacular --validate`, 21 existing tests. |
| frontend (#35) | Removed hard-coded cities. Store loads the list and details via the API client, aborts superseded requests, re-fetches on language change and validates the remembered city. Picker has loading, error, retry and empty states. Changed `app.tagline`, which named the cities. | Done. |
| tester | Backend: 59 new tests (41 registry, 18 API), all passing. Frontend: 64 → 65 tests, all passing after a fix round. Fictional cities in frontend fixtures. | Passing. |
| reviewer | Rounds: 1 per branch. | Backend APPROVED in round 1. Frontend APPROVED in round 1 with a should-fix, fixed in one round. |

**Review findings that mattered:**
- Backend, should-fix: `CITY_CONFIG_DIR` was missing from `.env.example`.
- Backend, should-fix: the `.mo` policy was undecided (decided by the maintainer, see `docs/decisions.md`).
- Backend, should-fix: feed URLs and licences are not verified.
- Frontend, should-fix: the "retrying" state in the city picker could never be shown. Fixed. The fix also added `role="status"` to the empty list and moved `init()` to `App.vue` only. Tester added a test.

**Manual test (maintainer):** Approved. The maintainer chose to commit the `.mo` files.

**Problems and lessons:**
- Worktrees do not see uncommitted contract changes in the main checkout. Commit the contract first, or paste it into the prompts. This time agents did use separate worktrees, which fixes the deviation in the previous entry.
- In Git Bash, set `MSYS_NO_PATHCONV=1` for `docker run -w /app`.
- A backend test that needs the DB fails in an ad-hoc container without the compose env. Run the full suite on the compose stack.
- The reviewer cannot run ruff or pytest on the host (no Python), so it relies on tester results.

**Follow-ups:**
- Verify feed URLs and attribution licences (data agent, before #7).
- Show details load errors in the UI once a screen uses city details.

## Foundation part 1 — 2026-11-11
**Issues / PRs:** #1, #2, #3 (PRs: pending)
**Branches:** chore/1-docker-compose, feat/2-django-scaffold, feat/3-vue-scaffold (planned; see process note)

| Agent | What it did | Result |
|---|---|---|
| coordinator | Created 16 labels and 30 issues from `docs/backlog.md` (two-agent items split: #25/#29 data sources, #28/#30 i18n). Added `GET /api/v1/health/` to `docs/api.md` before implementation. Added optional `details` to the error format after the backend agent flagged a contract gap. Fixed the path-guard hook in `.claude/settings.json`. | Done. The hook called `python3`, which is the Windows Store stub, so it failed silently and guarded nothing. It now uses `py -3` when available. |
| devops (#1) | Compose stack (db PostGIS 16, redis, backend, celery worker and beat, frontend, otp under profile `otp`), Dockerfiles, `.gitignore` (`.env` was not ignored before), `.env.example`, Makefile. Follow-up: Vite polling for Windows bind mounts, `npm ci`, backend healthcheck and start order. | Done. The first follow-up attempt used a Python script that does not exist on the host, so only part applied. The agent noticed and redid it with the Edit tool. |
| backend (#2) | Django 5.2 scaffold, settings split, DRF, drf-spectacular, contract error handler, health endpoint (200/503, no error details leaked), Celery app. | Done. 21 backend tests passing. |
| frontend (#3) | Vue 3 + TypeScript + Vite, Pinia, Vue Router, vue-i18n (43 keys, pl/en), city picker modal (focus trap, inert background), city switcher, PL/EN toggle, MapLibre map with OSM tiles, API client with `Accept-Language`, backend status in footer. | Done. Frontend tests 41 → 44. |
| tester | Backend 21 tests, frontend 41 → 44 tests. Found that `AppHeader.vue` could not be imported under Vitest on Windows (`/favicon.svg` asset URL transform). | Fixed by frontend (`transformAssetUrls` with `includeAbsolute: false`). Tester removed its mock and added header tests. All passing. |
| reviewer | Rounds: 2 | Round 1 CHANGES REQUESTED, fixed. Round 2 APPROVED. |

**Review findings that mattered:**
- Round 1, blocking: celery beat wrote `backend/celerybeat-schedule` into the bind-mounted repo, so it would have been committed.
- Round 1, also fixed: db, redis and otp ports were published on all interfaces (reachable from the LAN with the default password or no auth); now bound to 127.0.0.1. Backend container now runs as non-root. `POSTGRES_PASSWORD` default made consistent. Celery settings default made consistent with wsgi.

**Manual test (maintainer):** Passed. Feedback: the home screen should be a journey search panel on top of a full-screen map, with a bottom tab bar on phones and its own visual design. Recorded as a decision on issue #13. The scaffold was left unchanged.

**Process note:** Agents worked in one checkout instead of separate worktrees. Nothing was committed before the manual test and the three areas do not overlap. Branches are to be split at commit time. This differs from the worktree rule in `CLAUDE.md`.

**Problems and lessons:**
- Check that hook interpreters exist on the target OS (`python3` was missing on Windows).
- Bind-mounted dev containers can write runtime files into the repo. Run review before the first commit.
- Tell agents the shell environment up front: there is no `python3` on the host PATH, and the Bash safety check rejects some `rm -rf` and `--rm` commands.
