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
