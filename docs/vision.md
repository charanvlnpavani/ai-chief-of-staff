# PERSONAL OS — Project Vision & Development Blueprint

> This is the product's guiding document. It describes what Personal OS should become; it is not
> a record of what exists. For what is built and tested today, see [roadmap.md](roadmap.md).

**Document type:** Product Requirements Document (PRD) + implementation guide for Claude Code  
**Status:** Proposed specification — not an implementation report  
**Version:** 1.0  
**Primary development environment:** Visual Studio Code + Claude Code  
**Existing repository:** https://github.com/charanvlnpavani/ai-chief-of-staff  
**Product:** Responsive web application, with a mobile application planned

> **Vision:** One private, intelligent workspace to plan the day, capture knowledge, review progress, achieve goals, build habits, remember meetings, manage email, and search personal information with trustworthy source references.

---

## 1. Product aim

Personal OS brings everyday work and life information together, reducing scattered tabs, missed follow-ups, forgotten learning material, and repeated manual planning. It should act as a **personal command center** supported by an AI Chief of Staff—not an autonomous agent with uncontrolled access to accounts.

### Eight primary experiences

1. **Personal Dashboard** — Calendar, tasks, reminders, emails, and priorities in one view.
2. **Second Brain / Life Library** — Save articles, newsletters, YouTube links, webpages, and notes, then ask questions grounded in those items.
3. **Daily Review Agent** — Summarize completed work, unfinished tasks, blockers, and the next day's priorities.
4. **Personal Goal Tracker** — Break long-term goals into milestones, weekly actions, and measurable progress.
5. **Habit & Routine Coach** — Track routines, check-ins, streaks, reflections, and realistic improvement suggestions.
6. **Meeting Memory Assistant** — Convert authorized meeting notes and transcripts into decisions, owners, and follow-ups.
7. **Email Command Center** — Categorize email, summarize threads, propose replies, and manage follow-up reminders.
8. **Personal Knowledge Search** — Search notes, documents, meeting records, and saved resources using natural language and source links.

**Relationship to the earlier Personal OS master plan:** These eight experiences are the **initial product-facing focus**. They complement, rather than silently replace, the previously planned Personal Growth, Professional Work, Finance, Health, Habits, Jobs, Social Media, and AI News managers. Existing implemented managers must be preserved. The latter manager domains can be developed or expanded after validating this foundation.

### Initial audience and success criteria

- **Audience:** Primarily one authenticated user; future multi-user boundaries should be possible.
- **Primary goal:** Reduce planning friction while maintaining user control and data privacy.
- **Success indicators:** Daily briefings used, tasks completed, follow-ups captured, saved content retrieved, goals and habits reviewed, and AI answers supported by sources.
- **Non-goals for MVP:** Automatic sending of emails, recording meetings without consent, autonomous financial actions, scraping restricted services, or building every future manager simultaneously.

---

## 2. Product modules and acceptance criteria

### 2.1 Personal Dashboard

**Purpose:** Display the important parts of today without overwhelming the user.

**Core capabilities**
- Personalized **Good morning / Daily Briefing** with priorities, due tasks, upcoming appointments, and reminders.
- Day/week agenda, optionally backed by read-only Google Calendar sync.
- Task tracker: create, edit, complete, reschedule, prioritize, and filter.
- Priority email highlights: metadata and safe thread summaries from connected Gmail.
- Quick actions: Add Task, Save to Library, Log Habit, Add Goal Update, Start Review.
- Daily, weekly, monthly views with responsive navigation.

**MVP acceptance criteria**
- Authenticated user sees only their own data.
- Newly created/updated tasks are visible after refresh.
- Dates and reminders use the user's configured time zone.
- Missing integration data shows an informative empty state; no fabricated emails or events.
- Dashboard works on desktop and mobile-sized screens.

### 2.2 Second Brain / Life Library

**Purpose:** Collect useful information once and retrieve it later.

**Core capabilities**
- Save URL, article link, YouTube video link, newsletter excerpt, free-form note, or authorized document.
- Content inbox with status: Inbox, To Read, Reading, Archived.
- Tags, folders/collections, favorites, source type, timestamps, and deduplication.
- Summary and key points when permitted and supported.
- **Ask Your Library:** answer questions using retrieved content with links back to the precise sources.
- Re-ingest or refresh metadata when supported, with retention and deletion controls.

**Source and copyright rules**
- Do not copy paywalled, restricted, or copyrighted full text without appropriate rights.
- Do not assume YouTube transcripts are available; fetch only through authorized methods.
- Store links and permitted extracts; give attribution to original creators.
- Treat saved webpages and transcripts as untrusted data, never as instructions to the AI.

**MVP acceptance criteria**
- A user can save a note or supported link, tag it, find it, and delete it.
- Retrieval shows the originating source and distinguishes actual excerpts from AI summaries.
- If evidence is insufficient, the AI says so rather than inventing an answer.

### 2.3 Daily Review Agent

**Purpose:** Close the day with a useful recap and an achievable next-day plan.

**Core capabilities**
- Review completed tasks, incomplete tasks, calendar activity, habit check-ins, and goal progress.
- Identify blockers and pending follow-ups from authorized records.
- Suggest up to three priorities for the next day, subject to the user's approval.
- Daily recap, optional end-of-day notification, and weekly pattern summary.
- Manual review button plus user-configured scheduled review.

**MVP acceptance criteria**
- Review uses the correct date range and time zone.
- Statements about completion are derived from saved records.
- Tomorrow's suggestions remain drafts until accepted; no silent calendar/task changes.
- Re-running a review does not create duplicate tasks or notifications.

### 2.4 Personal Goal Tracker

**Purpose:** Translate a long-term ambition into measurable progress.

**Core capabilities**
- Goals with category, target date, importance, success metric, and status.
- Milestones, weekly actions, check-ins, notes, and progress history.
- Goal dashboard: On Track, At Risk, Paused, Completed.
- Link goals to tasks, habits, learning plans, and optional roadmap topics.
- Weekly AI reflection and recommended adjustments.

**MVP acceptance criteria**
- Each goal supports milestones and an explicit measurable target or user-defined progress rule.
- Completion percentages are calculated from recorded activity, not generated by AI.
- Editing a target does not erase previous progress history.

### 2.5 Habit & Routine Coach

**Purpose:** Build sustainable routines through evidence-based tracking and constructive feedback.

**Core capabilities**
- Custom habit definitions and schedules (daily, specific weekdays, weekly).
- Check-in calendar, consistency charts, streaks, pause days, and optional reminders.
- Morning/evening routines with reflection prompts.
- Weekly report and small, realistic habit suggestions.
- Habit links to Personal Goals and Professional Growth.

**MVP acceptance criteria**
- Check-ins are idempotent for each user/habit/date when applicable.
- Streaks respect schedule exceptions and user time zone.
- Missing a day does not delete history or misreport achievements.

### 2.6 Meeting Memory Assistant

**Purpose:** Turn meeting information into actionable institutional memory.

**Core capabilities**
- Paste meeting notes or upload an authorized transcript/document.
- Meeting summary, discussion topics, decisions, unresolved questions.
- Action items with owner, due date, confidence, and source excerpt.
- Decision log and follow-up reminders.
- Link accepted actions to Personal OS tasks and calendar events.

**Privacy and consent**
- Do not record or transcribe meetings without appropriate participant consent and applicable legal compliance.
- Treat third-party meeting material as sensitive; require explicit authorization before sending it to an external AI model.
- Label AI-extracted owners/dates as proposed until user-confirmed.

**MVP acceptance criteria**
- User can paste notes and obtain a structured draft summary.
- User can approve/edit action items before saving them as tasks.
- Saved decisions link back to the meeting and supporting notes.

### 2.7 Email Command Center

**Purpose:** Turn inbox information into prioritized actions while preserving control over messages.

**Core capabilities**
- Connect Gmail using least-privilege OAuth, starting with read-only scopes.
- Classify message/thread metadata into priority, jobs, finance, newsletters, reminders, personal, and other categories.
- Thread summaries, suggested next actions, draft reply text, and follow-up tracking.
- Link selected emails to tasks, meeting notes, or library entries.
- Manual sync, sync health, last sync, reconnection, and disconnect actions.

**Permissions and safety**
- Read-only Gmail integration in MVP; generated replies are drafts **inside Personal OS**.
- Creating a Gmail draft or sending email is a separate future capability requiring the correct scope and explicit approval.
- Never send, forward, archive, label, or delete Gmail content autonomously.
- Do not store account passwords; encrypt OAuth tokens, allow revocation, and minimize stored message content.

**MVP acceptance criteria**
- With consent, user can connect/disconnect Gmail, view synchronized thread metadata, and read an authorized summary.
- AI reply suggestions are clearly marked as drafts and do not send messages.
- Repeated syncs do not duplicate threads or follow-ups.

### 2.8 Personal Knowledge Search

**Purpose:** Answer questions across *all* authorized personal sources.

**Core capabilities**
- Keyword search and optional semantic/vector search over notes, saved documents, meeting records, and Life Library items.
- Filters for source type, date range, tags, collections, and domain.
- Natural-language answers with source citations and deep links.
- Search history controls, source permissions, and privacy-aware indexing.
- Related topics and cross-links between documents.

**Relationship to Second Brain**
- **Second Brain** is the capture and organization experience.
- **Personal Knowledge Search** is the shared retrieval/search service and dedicated search experience.
- Reuse one indexing pipeline and authorization model; do **not** create two competing knowledge databases.

**MVP acceptance criteria**
- Search finds saved notes with keyword relevance.
- AI answers show matching source records and acknowledge uncertainty.
- A user cannot search another user's private records.
- Semantic search may be phased in after keyword retrieval is reliable.

---

## 3. Central AI Chief of Staff

The AI should coordinate the eight experiences using **explicit, typed backend tools**. It does not receive raw database credentials or unrestricted execution access.

### Initial approved read-oriented tools (examples)

- `get_todays_agenda(user_id, date)`
- `list_pending_tasks(user_id, filters)`
- `get_goal_progress(user_id, goal_id)`
- `get_habit_summary(user_id, date_range)`
- `search_authorized_knowledge(user_id, query, filters)`
- `get_meeting_actions(user_id, date_range)`
- `get_email_priorities(user_id, date_range)`

### Suggested write flows

- `propose_task_from_email` → display suggestion → user confirms → application creates task.
- `propose_next_day_plan` → display plan → user confirms selected items → save updates.
- `extract_meeting_actions` → display owner/date suggestions → user reviews → save.

**Rules:** tool allowlist; validate schemas; enforce user ownership in the server; per-tool permissions; audit material side effects; safe timeouts and retries; prompt-injection defenses; cost ceilings; sensitive-data minimization; no publishing or external writes without action-specific approval.

---

## 4. Experience and navigation design

### Suggested main navigation

```text
Personal OS
├── Dashboard
├── Today / Calendar
├── Tasks & Reminders
├── Second Brain / Life Library
│   ├── Inbox
│   ├── Collections & Tags
│   └── Ask Your Library
├── Daily Review
├── Goals
├── Habits & Routines
├── Meetings & Decisions
├── Email Command Center
├── Knowledge Search
├── AI Chief of Staff
├── Reports & Insights
└── Settings
    ├── Integrations
    ├── Notifications
    ├── Privacy & Data
    └── Account & Security
```

### Main dashboard wireframe (conceptual)

```text
┌─────────────────────────────────────────────────────────────────────┐
│ PERSONAL OS             Search everything...      Alerts   Profile │
├──────────────────────┬──────────────────────────────────────────────┤
│ Navigation           │ Today • Briefing • Date                    │
│ Dashboard            │ 3 priorities    2 meetings    5 tasks      │
│ Tasks / Calendar     ├───────────────────────┬──────────────────────┤
│ Life Library         │ Schedule / Tasks      │ AI Chief of Staff  │
│ Review               │                       │ Ask / Suggestions  │
│ Goals / Habits       ├───────────────────────┼──────────────────────┤
│ Meetings             │ Goals / Habits        │ Priority Inbox     │
│ Email                │                       │                      │
│ Knowledge Search     ├───────────────────────┴──────────────────────┤
│ Settings             │ Quick Actions + Evening Review             │
└──────────────────────┴──────────────────────────────────────────────┘
```

**UX standards:** accessible contrast, keyboard navigation, clear empty states, light/dark mode, mobile-friendly cards, no excessive widgets, user-controlled notification frequency, loading/error/retry states.

---

## 5. Technical baseline (verify against existing repository)

| Layer | Proposed technology | Notes |
|---|---|---|
| Web | Next.js + TypeScript | Reuse the current app and design conventions. |
| Mobile | React Native + Expo + TypeScript | Add after stable API contracts; offline-friendly data capture. |
| Backend | Python + FastAPI | Modular monolith with domain modules. |
| Database | PostgreSQL | SQLAlchemy 2.x + Alembic migrations if compatible with existing code. |
| AI | Claude API | Server-side only; permissioned tool calling. |
| Worker | Celery + Redis | Scheduled reviews, syncing, ingestion jobs when needed. |
| Search | PostgreSQL text search first | Evaluate pgvector later for semantic search and RAG. |
| UI | Existing design system, optionally Tailwind + shadcn/ui | Do not replace working UI blindly. |
| Authentication | Secure sessions and standards-based OAuth | Support web/mobile appropriately. |
| Integrations | Google APIs with OAuth 2.0 | Minimal scopes; initially Gmail/Calendar read-only. |
| Quality | Pytest + frontend tests + E2E | CI before production deployment. |
| Operations | Docker, GitHub Actions, backups, monitoring | Choose hosting after cost and risk review. |

### Suggested backend modules

```text
backend/app/
├── core/                  # settings, security, logging, permissions
├── db/                    # session, models, migrations integration
├── api/                   # versioned HTTP routes
├── modules/
│   ├── dashboard/
│   ├── tasks/
│   ├── calendar/
│   ├── library/
│   ├── reviews/
│   ├── goals/
│   ├── habits/
│   ├── meetings/
│   ├── email_center/
│   └── knowledge_search/
├── ai/                    # provider adapter, tools, guardrails
├── integrations/          # Gmail, Google Calendar, Drive, etc.
├── automation/            # jobs and scheduling
└── notifications/
```

**Note:** This is an illustrative structure. Actual paths must be decided after inspecting the existing repository.

---

## 6. Initial database model proposal

Do not create all tables immediately. Reuse existing entities and implement migrations module-by-module.

| Domain | Candidate entities | Important design points |
|---|---|---|
| Identity | `users`, `user_preferences`, `user_consents` | Ownership, time zone, privacy preferences |
| Dashboard/tasks | `tasks`, `task_events`, `reminders` | Status, priority, due date, completion history |
| Calendar | `calendar_events`, `external_record_mappings` | Provider IDs, sync version, deduplication |
| Library | `library_items`, `library_collections`, `tags`, `library_item_tags` | Source URL, type, metadata, rights/retention |
| Retrieval | `content_chunks`, optional `chunk_embeddings` | Link chunks back to their original authorized source |
| Daily reviews | `daily_reviews`, `review_suggestions` | Source dates, approval status, no duplicate application |
| Goals | `goals`, `goal_milestones`, `goal_checkins` | Measurable targets, history |
| Habits | `habits`, `habit_schedules`, `habit_checkins`, `habit_exceptions` | Unique check-ins and time-zone-aware streaks |
| Meetings | `meetings`, `meeting_decisions`, `meeting_actions` | Owner, source excerpt, user confirmation |
| Email | `email_threads`, `email_message_metadata`, `reply_suggestions`, `email_followups` | Minimal content storage, provider IDs |
| Integrations | `integration_connections`, `sync_runs`, `sync_checkpoints` | Encrypted credentials, retry, reconnect, disconnect |
| AI | `ai_conversations`, `ai_tool_audit`, `ai_approvals`, `ai_usage` | Permissions, redaction, cost limits |

### General database rules

- Primary keys, foreign keys, timestamps, indexes, and unique constraints where appropriate.
- Enforce ownership and object-level authorization on every data access.
- External identifiers need provider-scoped uniqueness to prevent duplicate imports.
- Do not cascade-delete unrelated user records accidentally.
- Define retention and user export/deletion behavior.
- Do not store full raw emails or meeting transcripts by default when metadata or short authorized extracts are sufficient.

---

## 7. Proposed API surface (illustrative)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/dashboard/today` | User's daily briefing inputs |
| GET/POST | `/api/v1/tasks` | List or create tasks |
| PATCH | `/api/v1/tasks/{id}` | Update status, priority, due date |
| GET | `/api/v1/calendar/events` | User's authorized events |
| GET/POST | `/api/v1/library/items` | Browse or capture content |
| GET | `/api/v1/library/search` | Search library metadata/content |
| POST | `/api/v1/library/ask` | Grounded answer with source references |
| POST | `/api/v1/reviews/daily/generate` | Generate a review draft |
| POST | `/api/v1/reviews/{id}/approve` | Approve selected suggestions |
| GET/POST | `/api/v1/goals` | List or create goals |
| GET/POST | `/api/v1/habits` | List or create habits |
| POST | `/api/v1/habits/{id}/checkins` | Log a habit occurrence |
| POST | `/api/v1/meetings/analyze` | Extract proposed summary/actions |
| GET | `/api/v1/meetings/{id}` | Retrieve notes, decisions, actions |
| GET | `/api/v1/email/threads` | Authorized Gmail thread summaries |
| POST | `/api/v1/email/reply-suggestions` | Create an unsent reply draft |
| POST | `/api/v1/knowledge/search` | Unified authorized semantic/keyword search |
| POST | `/api/v1/ai/chat` | Chief of Staff chat with permissioned tools |
| GET | `/api/v1/integrations` | Connection statuses and last sync |
| POST | `/api/v1/integrations/{provider}/sync` | Authorized idempotent manual sync |

**API contract rules:** authentication, resource-level authorization, Pydantic validation, pagination/filtering, consistent error envelopes, explicit side-effect semantics, rate limiting, OpenAPI, and automated tests.

---

## 8. External integrations and consent

### Phase-one integrations

1. **Google Calendar:** Read-only agenda and event conflict visibility; future write permissions separately approved.
2. **Gmail:** Read-only thread metadata and selected content for classification; no autonomous send/modify.
3. **Google Tasks:** Evaluate syncing existing tasks and completion status; defer write scopes until separately approved.
4. **Google Drive:** User-selected authorized files for the Life Library; avoid broad account access.

### Later integrations

- YouTube links and permitted metadata/transcripts for Library ingestion.
- Meeting integrations only where provider permissions, consent, and access permit.
- Job/news/social integrations from the broader Personal OS roadmap after MVP.

### Security checklist

- OAuth 2.0 with least privilege, proper PKCE/state where applicable.
- Encrypted refresh-token storage and controlled token rotation.
- Never save provider account passwords.
- Connection health, last sync, manual sync, automatic sync, revoke, and disconnect.
- Idempotent import with unique provider IDs, checkpoints, and backoff on rate limits.
- No private content in logs, browser bundles, analytics, or public GitHub.

---

## 9. AI and retrieval design

### Grounded answering flow

```text
User question
  → Authenticate and authorize user
  → Choose permitted source collections
  → Retrieve relevant chunks/records
  → Apply ownership and source filters
  → Ask Claude to answer using supplied evidence
  → Return answer + source citations + uncertainty
```

**Retrieval principles:** keyword search first; only introduce embeddings when needed; citation to source IDs/URLs; permission checks before and after retrieval; no fabricated quotations; content lifecycle management; protect against prompt-injection in emails, webpages, and transcripts.

### User approval matrix

| Action | Default behavior |
|---|---|
| Read authorized internal tasks | Allowed under session permissions |
| Summarize saved notes | Allowed with appropriate data consent |
| Generate suggested tasks or replies | Draft only |
| Change a task or goal | Explicit in-app confirmation or user-initiated edit |
| Create Google Calendar event | Future write scope + action-specific confirmation |
| Send an email | Not in MVP; explicit separate approval if added |
| Record/transcribe a meeting | Consent and legal compliance required |
| Delete data / publish externally | Explicit approval and audit |
| Financial transaction | Not supported |

---

## 10. Milestone-by-milestone development plan

### M0 — Read-only repository audit (must happen first)

- Inspect actual files, frameworks, working functionality, tests, integrations, and Git status.
- Map current features to the eight experiences and to previously planned managers.
- Review privacy/security risks, technical debt, and deployment constraints.
- Propose actual file paths and an incremental migration strategy.
- **Deliverable:** Evidence-based audit and plan only; **no modifications**.

### M1 — Application foundation

- Secure authentication, user preferences/time zone, backend API contracts, PostgreSQL migrations, environment/secrets, test harness, and baseline design system.
- **Done when:** authenticated access and CRUD integration tests pass, with existing behavior preserved.

### M2 — Tasks, calendar view, and Personal Dashboard

- Task CRUD, priorities, reminders, daily view, dashboard widgets, empty states; Calendar integration can begin as mocked/local then authorized read-only sync.
- **Done when:** daily workflow works end-to-end with real persisted user data.

### M3 — Goals and Habits

- Goal/milestone CRUD, habit schedules/check-ins, progress calculations, dashboard summaries.
- **Done when:** progress and streak calculations pass time-zone and duplicate-entry tests.

### M4 — Second Brain capture and organization

- Notes, saved links, collections/tags, metadata, content inbox, safe source handling.
- **Done when:** capture, search, tag, retrieve, and delete work end-to-end.

### M5 — Knowledge Search and Ask Your Library

- Unified search service, source-linked answers, optional semantic retrieval after validating keyword search.
- **Done when:** grounded answers, source links, auth boundaries, and low-evidence handling pass tests.

### M6 — Daily Review Agent

- Deterministic recap inputs, AI narrative, draft tomorrow plan, review history, optional scheduling.
- **Done when:** reviews reflect actual data and accepted suggestions do not duplicate tasks.

### M7 — Meeting Memory Assistant

- Note/transcript import (with consent), structured draft extraction, decisions, action-item review, task linking.
- **Done when:** review/approval and provenance work end-to-end.

### M8 — Email Command Center

- Gmail read-only OAuth, secure sync, thread classification, draft reply suggestions, follow-up tasks.
- **Done when:** token security, deduplication, sync recovery, and no-send policy are verified.

### M9 — Mobile, automation, and deployment hardening

- Expo app using shared APIs, offline-friendly local entry, synchronization, notifications, monitoring, backups, privacy testing, deployment/runbooks.
- **Done when:** critical mobile paths, recovery scenarios, and deployment validation pass.

**Sequence is provisional.** Reorder small milestones to reuse existing completed work after M0.

---

## 11. Engineering and security standards

- Modular architecture, not premature microservices.
- Reuse and preserve working code; change architecture only with justified approval.
- No hardcoded API keys, OAuth tokens, passwords, or secrets.
- Use migrations, backups, restore tests, and transactional data updates.
- Authentication, authorization, validation, CSRF/CORS measures as appropriate, and secure credential storage.
- Rate limits, structured redacted logging, error monitoring, timeout/retry policies.
- Keep AI costs bounded and record usage without excessive sensitive content.
- Prefer stable dependencies and verify official documentation and licenses.
- Automated backend/frontend tests; integration tests for providers using safe mocks.
- Accessible UI, responsive design, latency and loading-state handling.
- Data export and deletion with clear retention rules.

### Definition of done (per implemented milestone)

1. Scope and file paths agreed.
2. Code actually written and reviewed.
3. Database migration documented and tested if applicable.
4. Tests executed and results shown accurately.
5. User-owned data protected by authorization.
6. Relevant failure paths handled.
7. Documentation updated.
8. No existing functionality unintentionally removed.
9. Remaining issues honestly reported.

---

## 12. Claude Code instructions — read before doing any work

**Work environment:** Existing Personal OS repository opened in VS Code.

1. Start by **inspecting the current repository**; do not assume the proposed directory layout is already implemented.
2. Treat this document as a **product vision and planning reference**, not evidence that any feature exists.
3. Preserve the previously specified eight long-term manager domains and all working code while prioritizing the eight experiences in this document.
4. During the initial audit, **do not create, modify, move, or delete files; install packages; run migrations; or deploy services**.
5. Deliver an audit with actual file-path evidence, a gap analysis, database/API recommendations, and the first small implementation milestone.
6. Explain trade-offs, prerequisites, security implications, and dependencies before making changes.
7. Request my explicit approval before implementation and before destructive operations, external publishing, financial actions, or external write permissions.
8. After approval, implement **one milestone at a time** with exact file paths, commands, explanations, test results, and rollback guidance.
9. Never report an untested or unimplemented feature as completed.
10. Protect user data and never expose secrets in prompts, source code, outputs, or logs.

### First message to Claude Code

> Read `PERSONAL_OS_PROJECT.md` and inspect my existing repository in read-only mode. Compare current functionality to the eight Personal OS experiences. Give me an evidence-based repository audit, a proposed modular architecture, a minimal schema and API plan, and the recommended first milestone. Do not modify files or install anything until I explicitly approve.

---

## 13. Future roadmap beyond the eight initial experiences

The wider Personal OS vision also includes the previously specified **Professional Work/Career Growth, Finance, Health, Jobs, Social Media, and AI News** capabilities, including the original **Zero-to-Pro Developer Skill Roadmap** idea. Keep these as planned or existing domains as appropriate based on the repository audit. Do not delete them or claim they are already completed.

**Guiding principle:** Make the next useful feature work reliably before adding another agent, plugin, or integration.
