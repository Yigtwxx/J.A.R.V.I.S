# J.A.R.V.I.S — Project Guide

An OSINT intelligence console: a FastAPI backend that runs an evidence-driven discovery
pipeline over **public** data, and a Next.js frontend that lets a user watch and steer
each search as it runs.

## Scope boundary

Public sources only. Private-camera access, individual tracking and anything that
depends on compromised or non-public data are out of scope and stay out of scope
even when a request says "no limits". Say so plainly and offer the public-data
equivalent instead.

---

## 1. Repository layout

```
backend/     FastAPI service (Python ≥ 3.11)
frontend/    Next.js 15 App Router (TypeScript, strict)
docs/        Design specs — docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md
```

- Database: SQLite via SQLAlchemy — `backend/data/jarvis.db`, migrations in `backend/alembic/`
- LLM: local Ollama, driven through `app/services/ollama_client.py` and `app/services/ai_service.py`
- Working branch: `main`

## 2. Running

| Task | Command |
|---|---|
| Everything | `docker-compose up` (repo root) |
| Quick start | `start-jarvis.bat` (Windows) · `start-jarvis.sh` (Unix) |
| Frontend only | `cd frontend && npm run dev` → `:3000` |
| Backend only | `cd backend && ./venv/Scripts/python.exe -m uvicorn app.main:app --reload` → `:8000` |

The backend has its own virtualenv at `backend/venv`. The system Python does not
have the dependencies installed — always invoke tooling through that interpreter.

---

## 3. Backend — Python / FastAPI

### Layout (`backend/app/`)

| Path | Responsibility |
|---|---|
| `main.py` | App wiring, middleware stack, global SSE log tap, startup checks |
| `config.py` | `Settings` (pydantic-settings, `.env`) |
| `database/connection.py` | Engine, `Base`, `get_db` |
| `routes/` | HTTP surface, one module per feature area |
| `discovery/` | The discovery pipeline (see below) |
| `services/` | Everything outside the pipeline: AI, breach, GitHub, reports, watch |
| `models/`, `schemas/` | SQLAlchemy models and Pydantic schemas |
| `middleware/` | Auth, rate limiting, CSRF, audit |
| `agents/`, `plugins/`, `utils/` | Autonomous agents, plugin loader, logging |

### The discovery pipeline (`app/discovery/`)

This is the heart of the product and it rests on four invariants. Breaking one of
them is a bug even when the tests pass:

1. **Nothing is ever silently empty.** Every fetch, existence check and platform
   reports a status. `blocked` (the platform refused us) is never conflated with
   `not_found` (we looked, there is no account) or with `found`.
2. **A URL is never matched as a string.** Host equality plus anchored path
   patterns, so `roblox.com/users/1` can never be read as an X profile.
3. **One identity per answer.** Candidates are clustered by mutual corroboration
   and exactly one cluster is elected; narrative, avatar and accounts all come
   from that cluster.
4. **Every claim traces to evidence.** Confidence is a deterministic sum of named
   signals, and the biography is grounded in stored evidence.

Key modules: `loop/` (runner, rounds, seeds, state), `platforms/` (the catalogue
and existence oracles), `engines/` (search backends), `fetch/` (HTTP and stealth
tiers), `matching/`, `identity/`, `evidence/`, `hitl/` (the questions a search
pauses on), `session/` (per-session event bus).

### Two search paths

- **Interactive (default)** — `POST /api/search/sessions` returns 202 immediately,
  then streams progress over a per-session SSE channel and can pause to ask the
  user a clarifying question.
- **Blocking fallback** — `POST /api/search/` still exists but cannot ask
  questions, because an HTTP request cannot wait on a human. It is reached only
  when `DISCOVERY_ENABLED=false`, and the frontend says so out loud when it
  falls back.

`GET /api/status/stream` is a **process-wide** log tap that interleaves every
concurrent search. It feeds the live-status panel, so anything broadcast there is
read by a user as search progress. Infrastructure warnings (auth, rate limits,
CSRF, audit) must use `logger.log_warning(..., broadcast=False)`: they stay on the
console and in the log file and out of the feed.

### Conventions

- Imports at the top of the file. No inline or duplicated imports.
- Type hints are mandatory. `async` on I/O-bound paths.
- Schema changes: `alembic revision --autogenerate -m "..."`.
- Comments explain **why**, not what. A comment that restates the code is noise;
  one that records the failure a line prevents is worth keeping.

### Lint, format, test

```bash
cd backend
./venv/Scripts/python.exe -m ruff check .          # E, F, W, I, UP, B, SIM · line-length 120
./venv/Scripts/python.exe -m ruff format --check .
./venv/Scripts/python.exe -m pytest -q             # tests/ + tests/discovery/
```

`app/utils/logger.py` carries a handful of pre-existing ruff findings. Leave them
unless you are working in that file — reformatting untouched code buries the real
diff.

---

## 4. Frontend — TypeScript / Next.js

### Stack

Next.js 15 (App Router), React 19, TypeScript `strict`, Zustand, Axios, zod
(response validation), next-intl, Tailwind, framer-motion, lucide-react,
react-force-graph-2d, react-leaflet, Sentry.

### Layout (`frontend/`)

| Path | Responsibility |
|---|---|
| `app/` | App Router entry, `globals.css` |
| `components/chat/` | The console shell: input bar, tabs, reactor, live status |
| `components/discovery/` | Live session UI: progress, platform grid, questions, results |
| `components/panels/` | Feature panels (Logs, Memory, Watch, Plugins, System, Health) |
| `store/` | `chatStore` (UI + search state), `discoveryStore` (session state machine) |
| `services/` | `api.ts` (Axios) and `discoveryApi.ts` (fetch + SSE) |
| `lib/` | zod schemas, response validation, error normalisation, prefs |
| `types/` | Domain types, mostly inferred from the zod schemas |
| `messages/`, `i18n/` | Translations — `tr.json` and `en.json` must stay key-for-key identical |

### Conventions

- No `any`. Use `unknown` when the type is genuinely unknown, and define shared
  shapes as interfaces under `types/`.
- Prefer `async`/`await` over `.then()` chains.
- Top-level imports only; no inline `import()`.
- Function components with hooks.
- Every API response goes through `validateResponse` against its zod schema.
- User-visible strings live in `messages/`, never inline in a component.
- State that must survive a reload is written through a guarded helper (see
  `lib/platformPrefs.ts`): private-window storage failures degrade to a default,
  they never throw into a render.

### Lint and test

```bash
cd frontend
npx tsc --noEmit
npx eslint <paths>       # or: npm run lint
npm test                 # jest + Testing Library
```

Test conventions that matter:

- Mock **child components**, not icon libraries. An icon mock has to be updated
  every time a component gains an icon, and it fails as `undefined is not a
  component` far from the cause.
- Assert on behaviour a user could observe, and write the assertion message so a
  failure explains itself.

---

## 5. Cross-cutting rules

**Language.** Communication, analysis and explanation in **Turkish**. All code,
identifiers, comments, commit messages and documentation in **English**.

**Secrets.** Never hard-code an API key, token or credential, never print `.env`
contents, and never log a raw upstream response that may carry one. Everything
comes from the environment.

**Git.** The user commits, pushes and opens PRs themselves. Do not run `git
commit`, `git push` or open a PR unless explicitly asked.

**Scope.** Python rules apply to `backend/`, TypeScript rules to `frontend/`.
Do not leak one into the other.

## 6. Definition of done

Before reporting work as finished:

1. `ruff check` and `ruff format --check` clean on the files you touched.
2. `npx tsc --noEmit` and `eslint` clean.
3. `pytest` and `npm test` green — and say so with the actual counts.
4. New behaviour is covered by a test that would fail without the change.
5. If something is still broken, blocked or unverified, say which part and why.
   A partially working change reported as done is worse than one reported as
   partial.
