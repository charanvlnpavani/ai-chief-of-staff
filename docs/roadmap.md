# Roadmap

Milestones follow the blueprint in [vision.md](vision.md) (section 10). Each milestone is approved
before it starts and built one at a time.

Status labels: **Done** (implemented and tested), **Partial**, **Blocked** (needs something from
the owner), **Planned**.

## The eight experiences

| # | Experience | Status | Where it lives today |
|---|---|---|---|
| 1 | Personal Dashboard | Partial | `/today`: due tasks and today's habits. No calendar, email or briefing yet. |
| 2 | Second Brain / Life Library | Planned | — |
| 3 | Daily Review Agent | Planned | — (the Chief of Staff can summarize the day in chat; no saved reviews) |
| 4 | Personal Goal Tracker | Partial | `/goals`: numeric or milestone progress computed from recorded activity, On Track / At Risk / Paused / Completed, check-ins, append-only history that survives target edits, `get_goals` AI tool. Not yet: links to tasks/habits, weekly actions, weekly AI reflection. |
| 5 | Habit & Routine Coach | Partial | `/habits`: versioned schedules, streak engine, breaks. Routines, reflections and weekly report not yet. |
| 6 | Meeting Memory Assistant | Planned | — |
| 7 | Email Command Center | Planned | — |
| 8 | Personal Knowledge Search | Planned | — |
| — | AI Chief of Staff (read-only) | Done; live calls need a key | `/chief`: 11 read tools, consent, monthly budget, usage ledger, encrypted history. Any provider, bring your own key: Claude (native), OpenAI, Gemini, OpenRouter (incl. free models), Groq, local Ollama (free, offline) or any OpenAI-compatible endpoint, with a model picked from the provider's live list. Keys verified, encrypted at rest, only the last 4 characters shown; free models cost $0 in the budget; private endpoint URLs blocked in production. `AI_KEY_MODE=user` enforced in production. |

## Milestones

| ID | Milestone | Status | Evidence / notes |
|---|---|---|---|
| M0 | Read-only repository audit | Done | Audit delivered before implementation |
| M1 | Application foundation | Done (CI not yet run) | Google OIDC + dev sign-in, sessions, settings incl. time zone, consents, append-only audit log, RFC 9457 errors, log redaction, security headers, CSRF protection, Alembic, pytest on real Postgres, web shell with themes, privacy mode and PWA manifest, pre-commit + gitleaks, `.github/workflows/ci.yml` (runs once pushed) |
| M2 | Tasks, calendar view, Personal Dashboard | Partial | Done: recurring tasks with priorities and due dates, `/today` dashboard. Not yet: calendar view, reminders, daily briefing, quick actions. |
| M3 | Goals and Habits | Done | Habits with schedules, check-ins, time-zone-aware streaks, breaks. Goals with milestones, numeric targets, check-ins, progress and health, history kept across target edits (migration 0004). Follow-ups: link goals to tasks/habits, weekly actions, goals on `/today`. |
| M4 | Second Brain capture and organization | Planned | |
| M5 | Knowledge Search and Ask Your Library | Planned | Postgres full-text search first; one index shared with M4 |
| M6 | Daily Review Agent | Planned | First milestone that needs the background worker (Celery + Redis) for scheduled reviews |
| M7 | Meeting Memory Assistant | Planned | |
| M8 | Email Command Center | Planned | Gmail read-only; no sending |
| M9 | Mobile, automation, deployment hardening | Blocked (deploy) | Hosting choice needed; backend Dockerfile prepared, not built. Also: CSP nonces, Postgres row-level security, export/deletion, backups and restore test, Expo app. |

## Beyond the eight experiences (vision section 13)

| Domain | Status | Notes |
|---|---|---|
| Professional Work / Career Growth | Partial | `/work`: learning time vs a daily goal, DSA log with spaced review, skill matrix. Built ahead of plan. |
| Zero-to-Pro Developer Skill Roadmap | Partial | `/roadmaps`: type a subject, get a basic → intermediate → advanced → pro plan split into days; tick today's tasks; progress, per-level progress, streak and a finish date that slides when a day is skipped. Built-in DSA roadmap (51 days, original content; nothing copied from roadmap.sh); any other subject drafted by the user's own AI connection (consent and budget apply; every call costed in the ledger) in two stages: an outline with one concept per day split 30/30/25/15 % across the levels, then each day expanded into Understand / Practise / Check yourself tasks. Day counts are enforced in code (short levels topped up, skipped days retried, then filled), so even small local models give the full plan. Drafts run as a background job with live progress (`/roadmaps/draft-jobs`), kept in memory in the API process until the background worker exists (M6). Read-only `get_roadmaps` AI tool. Each roadmap links to the matching roadmap on roadmap.sh; with `ROADMAP_SH_CONTENT_DIR` pointing at a local clone, each day shows "Learn more" notes and resources for its concept (personal use only, read at request time, never stored or committed). Not yet: linking roadmap days to learning time, skills or goals; editing a saved roadmap. |
| Finance | Planned | Manual entry first; field encryption |
| Health | Planned | Manual entry first |
| Jobs | Planned | Application pipeline |
| Social Media | Planned | Publishing only with per-post approval |
| AI News | Planned | |
