# Starter backlog

The coordinator turns these into GitHub issues (`gh issue create`), labelled `agent:<name>` and `feature:<slug>`.
Order matters only where "Depends on" says so; everything else can run in parallel.

| # | Title | Agent | Feature | Depends on |
|---|---|---|---|---|
| 1 | Set up docker compose: postgres+postgis, redis, backend, celery, otp, frontend | devops | foundation | — |
| 2 | Scaffold Django project, settings split, DRF, drf-spectacular, health endpoint | backend | foundation | 1 |
| 3 | Scaffold Vue 3 + TS + Vite app with router, Pinia, vue-i18n, MapLibre, layout and city switcher | frontend | foundation | 1 |
| 4 | Add CI workflow: lint, tests, build for backend and frontend | devops | foundation | 2, 3 |
| 5 | Add city configuration (Kraków, Warsaw) and cities endpoints | backend | foundation | 2 |
| 6 | Start realtime collector for Kraków (stop events only) | data | live-data | 2, 5 |
| 7 | Import GTFS feeds for Kraków, Warsaw, WKD and national rail | data | gtfs | 5 |
| 8 | Configure and build OpenTripPlanner 2 graphs for both cities | data | journeys | 7 |
| 9 | Add stops search and stop overview endpoints | backend | timetable | 7 |
| 10 | Add lines, line route diagram and stop timetable endpoints | backend | timetable | 7 |
| 11 | Build timetable browser: tabs, line tiles, diagram, stop timetable, print | frontend | timetable | 10 (contract) |
| 12 | Add journey search endpoint backed by OTP, with walk/bike comparison and preferences | backend | journeys | 8 |
| 13 | Build journey search form and results with map | frontend | journeys | 12 (contract) |
| 14 | Add ticket catalogue, admin and ticket suggestion | backend | tickets | 5 |
| 15 | Add accounts, favourites and limited search history | backend | accounts | 2 |
| 16 | Add demo checkout with test payments and QR demo tickets | backend | tickets | 14, 15 |
| 17 | Build tickets, checkout, account, favourites and history UI | frontend | tickets | 14–16 (contract) |
| 18 | Add Gemini chat provider, tools and rate limits | ai | assistant | 9, 10, 12, 14 |
| 19 | Build chat window with cards | frontend | assistant | 18 (contract) |
| 20 | Add realtime departures, vehicles and alerts endpoints (Kraków, then Warsaw) | data | live-data | 6, 7 |
| 21 | Show realtime departures and live vehicle map | frontend | live-data | 20 (contract) |
| 22 | Add nightly delay statistics and heatmap endpoint | data | live-data | 6 |
| 23 | Train delay model, predictions and transfer risk | data | live-data | 22 |
| 24 | Show predictions, transfer risk badges and delay heatmap | frontend | live-data | 22, 23 (contract) |
| 25 | Add data sources page and attributions | backend + frontend | foundation | 7 |
| 26 | Write README, architecture, decisions, AI workflow docs | docs | docs | after each feature |
| 27 | Set GitHub repository description and topics | devops | foundation | 1 |
| 28 | Add Polish/English support: i18n setup, language switcher, Accept-Language, user language preference | frontend + backend | i18n | 2, 3 |

Issue 28 belongs to the foundation: set up i18n before screens are built, so no feature hard-codes text.
Issue 6 should start as early as possible: delay statistics need 2–4 weeks of collected data.
Tests (`tester`) and review (`reviewer`) run for every issue that changes code.
