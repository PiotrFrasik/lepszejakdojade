# GTFS fixture feeds

Small hand-written feeds for tests and local checks of the static GTFS importer.
Not test code: `import_gtfs --file` accepts a directory as well as a zip, e.g.

    python manage.py import_gtfs krakow --feed ztp_tram --file transit_data/fixtures/gtfs/minimal

## `minimal/`

| Table | Rows | Notes |
|---|---|---|
| agency | 1 | |
| stops | 6 | station `ST1` with platforms `ST1_A`, `ST1_B` (parent_station); `S3` has an empty wheelchair_boarding and a non-ASCII name |
| routes | 2 | `R1` extended route_type 900 (tram), colour `1F6FEB`; `R2` route_type 3 (bus), no colour |
| calendar | 2 | `WD` Mon-Fri, `WE` Sat-Sun, 2026-01-01..2028-12-31 |
| calendar_dates | 2 | 2026-11-11 (holiday): `WD` removed, `WE` added |
| shapes | 1 | `SH1`, 4 points listed out of order (sequence 2,1,3,4) |
| trips | 4 | `T1_WD_2350` runs past midnight; `T1_WE_0900` has no shape |
| stop_times | 13 | `24:04:00` and `24:10:00` (86640 and 87000 s); `T1_WD_0800` stop 3 has no times (stored as null); `9:12:00` has a one-digit hour; `08:05:00`/`08:06:00` differ |
| frequencies | 1 | `T2_WD_0715` every 600 s, 07:15-09:15 |
| feed_info | 1 | version `fixture-1` |

Expected service range: 2026-01-01..2028-12-31. The fixture dates expire at the end of 2028.
