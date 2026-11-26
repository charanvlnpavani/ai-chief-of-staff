# Personal OS

One private, intelligent workspace to plan the day, capture knowledge, review progress, achieve
goals, build habits, remember meetings, manage email, and search personal information with
trustworthy source references. The full blueprint is in [docs/vision.md](docs/vision.md).

> **Status: in development.** Working today: sign-in, Tasks, Habits, Goals, learning Roadmaps (basic to pro, day by day), the Life Library (save links, videos, quotes and notes; tag, organise and search them), the Today dashboard, a
> read-only AI Chief of Staff, and Work & learning (learning time vs a daily goal, DSA practice
> with spaced review, skills). Next up: finishing M2 (calendar view, reminders, daily briefing). Knowledge Search (Ask Your Library), Daily Review,
> Meetings and Email follow, one milestone at a time. See [docs/roadmap.md](docs/roadmap.md).

| Layer | Stack |
|---|---|
| Web | Next.js 16 (App Router), React 19, TypeScript, Tailwind 4, shadcn/ui (Radix), TanStack Query |
| API | Python 3.13, FastAPI, SQLAlchemy 2.1 (async, psycopg 3), Alembic, Pydantic 2 |
| Data | PostgreSQL 17 |
| AI | Claude (`claude-opus-5-5`) via the Anthropic SDK; self-hosted tool loop |
| Tooling | pnpm workspaces, uv, ruff, mypy (strict), pytest, ESLint, Vitest, gitleaks, GitHub Actions |

## Quick start (macOS)

Prerequisites: Node 26, pnpm 11, [uv](https://docs.astral.sh/uv/), PostgreSQL 17 binaries (Homebrew `postgresql@17`).

```bash
pnpm install                              # JS dependencies (web + api-client)
(cd backend && uv sync)                   # Python 3.13 environment
cp backend/.env.example backend/.env      # then fill in SECRET_KEY and ENCRYPTION_KEYS (see comments)
pnpm db:setup                             # project-local Postgres on localhost:55432 + migrations
pnpm dev                                  # API on :8000, web on :3000
```

Open http://localhost:3000 and choose **Continue (local development)**. The dev sign-in only works
for addresses in `ALLOWED_LOGIN_EMAILS` and is refused in production.

After a reboot, start the database again with `pnpm db:start`.

### Optional: Google sign-in

Create an OAuth client ("Web application") in Google Cloud with redirect URI
`http://localhost:3000/api/v1/auth/google/callback`, put the ID and secret in `backend/.env`, and
add your Google address to `ALLOWED_LOGIN_EMAILS`. Only `openid email profile` is requested.

### Optional: AI (Chief of Staff, roadmap drafts)

AI runs on **each user's own connection**, set up in **Settings → AI provider**:

| Provider | Key | Notes |
|---|---|---|
| Claude (Anthropic) | platform.claude.com | Native SDK: prompt caching, adaptive thinking, refusal fallback |
| ChatGPT models (OpenAI) | platform.openai.com | |
| Google Gemini | aistudio.google.com | Free tier |
| OpenRouter | openrouter.ai | Hundreds of models; `:free` models cost nothing |
| Groq | console.groq.com | Free tier |
| Ollama | none | Free, private, **offline**: models run on your computer |
| Custom | optional | Any OpenAI-compatible URL (LM Studio, DeepSeek, Mistral, ...) |

After connecting, pick a model from the provider's live list (the Chief of Staff needs one
that supports tool calling). Keys are checked with the provider, stored encrypted (AES-256-GCM,
bound to your account) and never shown again. Every call is recorded in a usage ledger and
blocked once the monthly budget (Settings, default $25) is reached; free models cost $0, and
models without a known price are counted at Claude Opus rates. Set a spend limit with your
provider too.

`AI_KEY_MODE=user` (the default) makes a personal connection mandatory and is enforced in
production. For a single-user self-host, `AI_KEY_MODE=server` lets `ANTHROPIC_API_KEY` act as a
fallback. Provider URLs that point at localhost or a private network (such as Ollama on the
same machine) are allowed in development and refused in production unless
`AI_ALLOW_PRIVATE_ENDPOINTS=true`.

### Optional: "Learn more" from roadmap.sh

Every roadmap shows a link to the matching roadmap on [roadmap.sh](https://roadmap.sh). For
notes on each day's concept, clone its content repository on your own machine and point the
backend at it:

```bash
git clone --depth 1 https://github.com/nilbuild/developer-roadmap.git ~/code/developer-roadmap
echo "ROADMAP_SH_CONTENT_DIR=$HOME/code/developer-roadmap" >> backend/.env   # then restart the API
```

That content is licensed for **personal use only**. Personal OS reads it from your machine
when you open a day and shows it to you. It is never stored in the database, committed to this
repository, published, or sent to an AI provider. Do not copy it into this repository.

## Everyday commands

| Command | What it does |
|---|---|
| `pnpm dev` | API (reload) + web dev server |
| `pnpm test` | Web unit tests + backend tests (real Postgres) |
| `pnpm lint` / `pnpm typecheck` | ESLint + ruff / tsc + mypy strict |
| `pnpm build` | Production build of the web app |
| `pnpm db:migrate` | Apply Alembic migrations |
| `pnpm api:generate` | Re-export OpenAPI and regenerate the typed client (CI fails if stale) |
| `pre-commit install` | Secret scanning and formatting before each commit |

## Repository layout

```text
apps/web/              Next.js app (pages in src/app/(app)/…)
packages/api-client/   OpenAPI schema + generated TypeScript types + fetch client
backend/app/core/      config, db, errors, security, crypto, logging, middleware
backend/app/modules/   identity · productivity (tasks) · habits · goals · roadmaps · professional · dashboard
backend/app/ai/        Chief of Staff: client, tool registry, orchestrator, ledger
backend/migrations/    Alembic migrations (hand-reviewed)
backend/tests/         pytest suite (real Postgres, rolled back per test)
docs/                  vision (product blueprint), roadmap, architecture, decisions (ADRs)
scripts/dev-db.sh      project-local Postgres cluster
```

## Principles

- Your data lives in your database. The AI can **read and suggest only** in Release 1; it
  cannot change, delete, send or publish anything, and that is enforced in code, not prompts.
- Every query is scoped to the signed-in user, and tests prove a second user cannot see your data.
- Numbers come from SQL, not the model. Claude explains them.
- Small, verified milestones; nothing ships without tests.

Security policy: [SECURITY.md](SECURITY.md). Architecture: [docs/architecture/overview.md](docs/architecture/overview.md).
