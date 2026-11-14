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
