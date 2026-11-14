# Architecture

This page shows the services and the data flow. Items marked **(planned)** are not built yet;
the issue number is in brackets. Everything else exists in the code.

## Services

```mermaid
flowchart LR
    user(["Browser"])

    subgraph stack["docker compose stack"]
        fe["Frontend<br/>Vue 3 + Vite"]
        be["Backend<br/>Django + DRF"]
        cw["celery-worker"]
        cb["celery-beat"]
        redis[("Redis 7<br/>Celery broker")]
        db[("PostgreSQL 16<br/>+ PostGIS")]
        otp["OpenTripPlanner 2<br/>profile 'otp', no graph yet"]
    end

    gemini["Google Gemini API<br/>(planned, #18)"]
    ztp["ZTP Kraków<br/>GTFS-RT TripUpdates<br/>tram, bus, Mobilis bus (#38)"]
    gtfs["GTFS static feeds<br/>ZTP Kraków, mkuran.pl (Warsaw, WKD)"]

    user --> fe
    fe -- "/api/v1 (Vite proxy)" --> be
    be --> db
    cb -- "every REALTIME_POLL_INTERVAL_SECONDS" --> redis
    redis --> cw
    cw --> db
    cw -- "HTTP GET, protobuf" --> ztp
    be -.-> otp
    be -.-> gemini
    cw -- "HTTP GET, zip (conditional)" --> gtfs
```

| Service | Where | Notes |
|---|---|---|
| Frontend | `frontend/` | Vue 3, TypeScript, Vite, Pinia, vue-i18n, MapLibre |
| Backend | `backend/` | Django 5, DRF, drf-spectacular. Apps: `core`, `cities`, `transit_data` |
| celery-worker, celery-beat | `backend/` image | Same image as the backend; runs background tasks |
| Redis | `redis:7-alpine` | Celery broker |
| PostgreSQL | `postgis/postgis:16-3.4` | Main database |
| OpenTripPlanner | `opentripplanner:2.6.0` | Started only with `--profile otp`; journey search is planned (#8, #12) |
| Gemini | external | Planned (#18). Behind a provider interface |
| ZTP Kraków feeds | external | Read by the realtime collector |
| GTFS static feeds | external | Imported nightly by `celery-worker` (#7). Kraków: ZTP. Warsaw: mkuran.pl (ZTM data). WKD: mkuran.pl |

## Data flow

### Realtime collector (implemented, #6)

Celery beat queues `transit_data.collect_trip_updates` every `REALTIME_POLL_INTERVAL_SECONDS`
(default 30). A worker runs it once per poll.

```mermaid
sequenceDiagram
    participant B as celery-beat
    participant W as celery-worker
    participant P as PostgreSQL
    participant Z as ZTP feed

    B->>W: queue task (expires after one interval)
    loop each city, each gtfs_rt feed with entity trip_updates
        W->>P: take advisory lock for this feed
        alt lock taken by another poll
            W-->>W: skip feed
        else lock free
            W->>Z: HTTP GET (urllib, timeout 10 s, max 20 MB)
            alt HTTP or network error, parse error, stale header
                W->>P: insert FeedFetch (status, error)
            else header timestamp same as last poll
                W->>P: insert FeedFetch (status unchanged), no StopEvent writes
            else new data
                W->>W: parse protobuf, validate entities and stop updates
                W->>P: upsert StopEvent in batches of 1000
                W->>P: insert FeedFetch (status ok, skipped_count)
            end
        end
    end
```

Rules the collector follows:

- **One row per stop visit.** `StopEvent` is unique on
  `(city_id, feed_id, service_date, trip_id, stop_id, stop_sequence)`. Tram messages have no
  `stop_sequence`, so the unique key uses `NULLS NOT DISTINCT`.
- **Upsert, not append.** Each poll updates the row with the newest prediction and moves
  `last_seen`. `first_seen` is kept. An arrival or departure value is kept if a later message
  does not contain it.
- **Honest nulls.** The scheduled time is `time - delay` only when the feed gives both. Otherwise
  it is null.
- **Observed value.** The last stored value (event time not after `last_seen`) is the best
  "observed" value for statistics (#22).
- **Service date.** ZTP feeds give no `start_date`. The service date is the local date of the
  event time minus 3 hours (`service_date_inferred=True`). A trip seen in the last 4 hours keeps
  its stored date, so trips crossing 03:00 do not split. Limitation: a trip first seen after 03:00
  that started before 03:00 gets the later date.
- **Bad values skip only the affected part.** An entity or stop update with overlong ids, NUL
  bytes or out-of-range numbers or times is skipped. The count goes to `FeedFetch.skipped_count`
  and a summary to `FeedFetch.error`. One warning is logged per poll.
- **The collector does not raise.** Each feed poll ends with a `FeedFetch` row, whatever happened.
- **No overlapping polls.** A Postgres advisory lock per feed stops two polls of the same feed
  from running at once. Beat jobs expire after one interval, so queued polls do not pile up.

What the ZTP feeds contain (as observed):

| Feed | Available | Missing |
|---|---|---|
| Tram trip updates | trip id, stop id, absolute times, vehicle id | start date, route id, stop sequence, delay. The static import (#7) is in place, but the collector does not read it yet |
| Bus trip updates | route id (always), delay and stop sequence (about 14–20% of updates) | Some last-stop departures come with time 0 and delay 0; they are treated as missing |

Volume: about 5,000 stop events per poll in the evening and 10,000 to 17,500 during the day.
Estimated size is about 790 bytes per row including indexes, roughly 200 MB per day.

Table bloat: daytime upserts cause table and index bloat. This is addressed in #22 (delete by
`service_date`, review the `last_seen` index, tune autovacuum).

### Static GTFS import (implemented, #7)

Celery beat runs `transit_data.import_all_gtfs` every day at `GTFS_IMPORT_HOUR`:`GTFS_IMPORT_MINUTE`
(default 03:30, Europe/Warsaw). It imports every `gtfs_static` feed that has a URL in each city config.
The same import runs by hand with `manage.py import_gtfs <city>`.

```mermaid
sequenceDiagram
    participant B as celery-beat
    participant W as celery-worker
    participant Z as GTFS feed
    participant P as PostgreSQL

    B->>W: transit_data.import_all_gtfs (daily)
    loop each city, each gtfs_static feed with a URL
        W->>P: take advisory lock for this city and feed
        alt lock taken by another import
            W-->>W: report busy
        else lock free
            W->>Z: conditional GET (ETag, Last-Modified), size and time limits
            alt not modified, or same sha256 as the last failed data error
                W->>P: report unchanged or skipped
            else new archive
                W->>W: stream CSV files, skip or correct bad rows
                W->>P: COPY rows into a new FeedVersion
                W->>P: check size against active version, switch active (one transaction), ANALYZE
                W->>P: delete versions beyond retention
            end
        end
    end
```

Rules the importer follows:

- **Versioned.** Every import writes a new `FeedVersion`. The active version is switched only after
  the whole load succeeds. Readers never see a half-loaded feed.
- **Retention.** Per feed: the active version, one superseded version, and the last 5 failed
  versions (failed rows hold no data). Settings: `TRANSIT_GTFS_KEEP_SUPERSEDED`, `TRANSIT_GTFS_KEEP_FAILED`.
- **Retry.** A failure caused by a data error (`GtfsFormatError`, `FeedRejected`) is remembered by
  sha256, and the same archive is not imported again until it changes. Any other failure (interrupted run,
  database error, time limit) is retried on the next run.
- **Size check.** A new version with less than 50% of the active trips or stop times is rejected
  (`TRANSIT_GTFS_MIN_SHARE_OF_ACTIVE`). `--force` bypasses the check. Only a log warning is written
  for a rejected version.
- **Bad rows.** Rows with bad references or values are skipped and counted, with reasons, in the
  import report. Stop hierarchy errors (bad parent links) are corrected; stop times on stations are
  skipped. A feed is rejected when more than 5% of rows are skipped (`TRANSIT_GTFS_MAX_SKIPPED_RATIO`).
- **Expiry warning.** The report warns when service ends within 14 days (`TRANSIT_GTFS_EXPIRY_WARNING_DAYS`).
- **Report.** Each run stores counts, skipped rows, corrections, ignored files and a comparison with
  the active version as JSON on `FeedVersion.report`.
- **Times.** Stored as seconds since midnight of the service day. Values above 24:00 are allowed.
- **Calendar.** `calendar.txt` is optional when `calendar_dates.txt` exists.

Measured on the real feeds during #7 testing (local stack):

| Feed | Stops | Trips | Stop times | Import time |
|---|---|---|---|---|
| Kraków tram (`ztp_tram`) | 355 | 15,321 | 439,544 | 4.2 s |
| Kraków bus (`ztp_bus`) | 2,983 | 85,907 | 1,833,889 | about 21–25 s |
| Warsaw ZTM (`ztm`) | 7,270 | 259,591 | 7,446,307 | 73–87 s |
| WKD (`wkd`) | 60 | 3,702 | 55,386 | 1.4 s |

About 90,000 stop times per second, 210 MB peak memory. The database was about 3.5 GB with the
active and one previous version of all feeds. A departures query for one stop on one date took
6.9 ms; a trigram name search took 0.4 ms (measured on the same data).

Limits (not built yet): no check for times on the first or last stop, no check that times rise
monotonically, and the raw zip files are not kept (OTP, #8, will need them).

### Journey search (planned, #8, #12)

Frontend sends `A → B` with time and preferences to the backend. The backend calls OTP
(`OTP_URL`) and returns journeys. The app has no routing code of its own; the engine is OpenTripPlanner 2
([concept](concept.md), section 1).

### Timetable (planned, #9, #10)

The static import (#7, see above) already fills the PostgreSQL tables. The backend will serve stops,
lines and stop timetables from these tables. The frontend will render the browser and the print view.

### Live departures and vehicles (planned, #20, #21)

The realtime `StopEvent` data (#6) and vehicle positions feed the departures and live map
endpoints. Delay statistics (#22) and predictions (#23) are built on the same rows.

### Chat (planned, #18, #19)

The frontend sends a message to the backend. The backend calls Gemini through the provider
interface. Gemini answers by calling tools (journeys, timetables, tickets, live data) and the
backend returns text or cards. Rate limits apply per user.

## Retention

| Data | Rule | State |
|---|---|---|
| `StopEvent` (raw realtime) | Kept 60 days (`RAW_EVENT_RETENTION_DAYS`) | Deletion job not built yet; comes with #22 |
| `FeedFetch` (one row per poll) | About 2,880 rows per feed per day at a 30 s interval | No retention rule yet |
| Static GTFS versions (`FeedVersion` and its rows) | Active, one superseded, last 5 failed versions per feed (see above) | Built (#7) |
| Downloaded GTFS zip files | Not kept | OTP (#8) needs them; not decided yet |
| Nightly statistics | Planned (#22) | Not built |

## Operating the collector

- It runs only while the local stack is up. Continuous collection needs a server (not decided).
- Status per feed: `ok`, `unchanged`, `stale`, `http_error`, `network_error`, `parse_error`,
  `error`. Check them in the Django admin (read-only views of `FeedFetch` and `StopEvent`).
- Command options are in the [README](../README.md#realtime-data-collector).

## Operating the static import

- Run it by hand: `manage.py import_gtfs <city> [--feed <id>] [--force] [--file <zip or dir>]`. `--file` requires `--feed`.
  Exit status is 1 when a feed failed. Unchanged, busy and skipped feeds are not errors.
- The admin shows the static tables read-only. Rows are written and deleted only by the importer.
- Warsaw (`ztm`, `wkd`) feeds expire. The WKD feed data ends around 2026-12-12; the expiry
  warning appears 14 days before the end of service.
- Warsaw uses the mkuran.pl feed. A single maintainer runs it; the official ZTM feed is the fallback
  (see `docs/decisions.md`, entry 12).
