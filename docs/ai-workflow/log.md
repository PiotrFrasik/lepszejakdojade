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
