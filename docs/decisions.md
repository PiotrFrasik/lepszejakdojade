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
