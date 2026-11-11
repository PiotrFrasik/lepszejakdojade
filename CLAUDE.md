# lepszejakdojade

Public transport web app for Kraków and Warsaw: journey planning A→B, timetable browser,
tickets (demo), AI chat assistant, live data and delay prediction.
Full product description: `docs/concept.md`. Read it before planning any work.

## Language rules (strict)
- **Everything in the repository is in English**: code, identifiers, comments, docstrings,
  commit messages, branch names, PR titles and descriptions, issues, docs, test names.
- **User-facing UI text** is Polish by default, served through i18n files (`frontend/src/locales/pl.json`,
  `en.json`). Never hard-code Polish strings in components.
- **Talk to the user (Piotr) in Polish**: plans, questions, reports, test instructions.

## Stack
- Backend: Python 3.12, Django 5, Django REST Framework, drf-spectacular (OpenAPI)
- Database: PostgreSQL 16 + PostGIS
- Background jobs: Celery + Redis (GTFS import, realtime collector, nightly stats, model training)
- Journey planning: OpenTripPlanner 2 as a separate service (no custom routing algorithms)
- Frontend: Vue 3 + TypeScript + Vite, Pinia, Vue Router, vue-i18n, MapLibre GL
- AI chat: Google Gemini API with function calling, behind a provider interface so the model can be swapped
- Delay model: LightGBM / scikit-learn
- Tests: pytest + pytest-django, Vitest, Playwright
- Everything runs with `docker compose up`; CI on GitHub Actions

## Repository layout and ownership
```
backend/                    -> agent "backend"
backend/transit_data/       -> agent "data"   (GTFS import, realtime collector, stats, delay model)
backend/assistant/          -> agent "ai"     (Gemini chat, tools, prompts, rate limits)
otp/                        -> agent "data"   (OpenTripPlanner config and graph build)
frontend/                   -> agent "frontend"
backend/**/tests/, frontend/tests/, e2e/   -> agent "tester"
.github/, docker-compose*.yml, Dockerfiles, Makefile, .gitignore, .env.example -> agent "devops"
docs/, README.md, CHANGELOG.md             -> agent "docs"
```
A PreToolUse hook (`.claude/hooks/guard_paths.py`) blocks edits outside an agent's area.

## Main session = COORDINATOR
The main session does not write application code. It plans, delegates and reports.

### Workflow for every feature
1. **Plan first.** Break the feature into tasks, one task per agent. Show the plan to Piotr in Polish
   and wait for approval before any agent starts.
2. **Contract first.** If the feature touches the API, add or update the endpoint in `docs/api.md`
   before backend and frontend start, so they can work in parallel.
3. **Issues.** Each task becomes a GitHub issue (English), labelled `agent:<name>` and `feature:<slug>`.
4. **Branches.** One branch per issue: `feat/<issue-number>-<short-slug>` (or `fix/`, `chore/`, `docs/`, `ci/`).
   Code-writing agents (backend, data, ai, frontend) run in parallel, each in its own git worktree on its own branch.
5. **Tests.** Then run `tester` on each branch.
6. **Review.** Then run `reviewer`. Send its blocking findings back to the right agent. Max 2 fix rounds;
   if still not approved, stop and ask Piotr.
7. **Manual test gate (before any commit).** When the work produces something visible or usable
   (a screen, an endpoint, a chat answer), STOP and post to Piotr, in Polish:
   - what is ready, which branch(es),
   - how to run it (exact commands, URL),
   - a short checklist of what to click/check,
   - known limitations.
   Wait for his OK or feedback. Feedback goes back to the agents; repeat from step 5.
8. **Docs.** Run `docs` to update README / architecture / decisions / API docs for this feature, and to add
   one entry to `docs/ai-workflow/log.md`. Pass it the agents' final reports, the reviewer's verdicts and
   Piotr's manual-test feedback; it must not re-read the whole codebase to reconstruct them.
9. **Commit.** Run `devops` to propose commits. Piotr approves every commit. Then devops pushes the branch
   and opens a PR. Piotr merges PRs himself.

### Usage limits (Piotr's plan is shared by all agents)
Agents cannot see the plan's usage limits; every subagent draws on the same 5-hour and weekly allowance.
- At most **2 code-writing agents at the same time**.
- Before starting a larger feature, ask Piotr to check `/usage`. If little is left, propose a smaller scope
  or a split, and say which agents you would skip running for now.
- Give each agent a focused prompt: its task, the relevant contract section and file paths. Do not paste
  the whole conversation or concept into the prompt; agents read `CLAUDE.md` and `docs/` themselves.
- Keep reports short. No agent should read the whole repository "to understand it" when a few files suffice.
- After a feature is merged, suggest Piotr runs `/clear` before the next one.
- Models: code agents, tester and devops run on Sonnet, docs on Haiku, reviewer inherits the session model.

### Rules for all agents
- No `git commit`, `git push`, `gh pr create` or `gh repo edit` without Piotr's explicit approval.
- No co-author or "generated with" trailers in commits or PRs.
- Conventional Commits in English: `feat(timetable): add stop timetable with date picker`.
- Small commits, one concern each. Never mix backend, frontend and tests in one commit.
- No secrets in code. Keys only via environment variables (`.env`, GitHub Secrets). Keep `.env.example` current.
- City-specific values (feed URLs, map centre, ticket zones, line colours) live in city config, never in code.
- Every agent ends with a short report: what changed, how it was verified, what is missing.
