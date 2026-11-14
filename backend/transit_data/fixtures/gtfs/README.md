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

## `rail_area/`

A miniature national rail feed for the area filter (`static_gtfs/area_filter.py`). Use it with
the filter `bbox: [19.80, 49.95, 20.10, 50.15]` (around Kraków) and
`exclude_agencies: [SKM]`.

| Table | Rows | Notes |
|---|---|---|
| agency | 3 | `KML`, `IC`, `SKM` |
| stops | 9 | station `KGL` with platforms `KGL_1` and `KGL_2` (no coordinates, inside via its parent); `KPL`, `WIE`, `UNUSED` inside; `KRZ` (west of the bbox), `TAR`, `WAW` outside |
| routes | 4 | `KML_S1`, `IC_IC`, `SKM_S9` (agency `SKM`), `KML_BUS` (only used by an outside trip) |
| trips | 5 | see below |
| stop_times | 14 | with `shape_dist_traveled`, except `T_SKM_1` |
| shapes | 11 | `SH_S1` (3 points), `SH_IC` (6 points, 0..370), `SH_BUS` (2 points) |
| calendar | 3 | `WD`, `WE`, `DAILY` |
| calendar_dates | 2 | `WD` removed and `HOL` (only used by `T_BUS_1`) added on 2026-11-11 |
| transfers | 3 | one between kept trips at `KGL`, one to `KRZ`, one at `WAW` |
| feed_info, attributions | 1 each | copied unchanged |

| Trip | Calls | With the filter above |
|---|---|---|
| `T_S1_1` | KGL_1, KPL, WIE | kept whole |
| `T_IC_1` | WAW, KGL_2, KPL, TAR | kept, clipped to KGL_2, KPL; `SH_IC` clipped to points 1-4 (150..320) |
| `T_IC_2` | WAW, KGL_1, KRZ | dropped: only one call inside |
| `T_SKM_1` | KGL_1, KPL | dropped: agency `SKM` excluded (kept without `exclude_agencies`) |
| `T_BUS_1` | TAR, WAW | dropped: no call inside |

Expected result with the filter above: agency 2, stops 5 (`KGL`, `KGL_1`, `KGL_2`, `KPL`,
`WIE`), routes 2, trips 2, stop_times 5, calendar 2 (`WD`, `DAILY`), calendar_dates 1,
shapes 7 points, transfers 1. `UNUSED` is inside the bbox but served by no kept trip, so it
is dropped.
