# Architecture

---

## System Overview

A single FastAPI service (port 8001) serves both the JSON/SSE API and the static Next.js UI at `/app`. Uploaded CSVs are parsed and loaded into a local **analytics store** (a separate SQLite database file opened read-only at query time); app metadata (dataset registry, conversations, run audit) lives in the main app database. A LangGraph agent answers questions: it plans against the dataset registry's schemas, generates SQL, executes it read-only against the analytics store, inspects the result, retries if needed, and composes a streamed answer. The LLM (Gemini) only ever receives schemas, column profiles, and small computed aggregates — never raw rows. In Phase 3 a scheduler performs off-peak extracts from the department MsSQL server into the same analytics store, so daytime questions never touch MsSQL.

## Component Map

```
Browser (Next.js static export at /app)
    ↓ fetch / SSE
FastAPI (src/api)  ──►  Ingest (src/ingest)  ──►  Analytics store (data/analytics.db, tables ds_*)
    │                                                     ▲ read-only SQL
    ▼                                                     │
LangGraph agent (src/graph) ──► LLM client (src/llm) ──► Gemini API   [schema + aggregates only]
    │
    ▼
App DB (data/agent.db: datasets, conversations, runs)          [Phase 3] MsSQL ──nightly──► Analytics store
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| API (`src/api`) | HTTP/SSE endpoints, request validation, response envelope |
| Agent (`src/graph`) | Plan → SQL → execute → check → compose loop; state; streaming events |
| Ingest (`src/ingest`) | CSV sniffing/parsing/loading, profiling, table lifecycle in the analytics store |
| LLM (`src/llm`) | Provider-agnostic client (Anthropic/Gemini), usage accounting, streaming |
| Storage (`src/db`) | SQLAlchemy models + sessions for the app DB; analytics store accessor |
| Observability (`src/observability`) | structlog JSON events per request/node/LLM call |

## Data Flow

1. Trigger: user uploads CSVs → `POST /datasets` → ingest loads full data into `data/analytics.db` table `ds_<id>`, computes profile, registers dataset in app DB.
2. User asks a question → `POST /questions/stream` (SSE) → run row created → graph starts; step events stream to the browser.
3. Graph: prepare context (registry schemas + conversation history) → plan (datasets, approach, language, or clarification) → write SQL → execute read-only with limits/timeouts → check (retry ≤ N on error/empty) → compose answer (streamed deltas, caveats, follow-ups).
4. Output: final SSE event with answer, SQL, steps, result table (≤200 rows), caveats, follow-ups, usage; run row updated (audit).

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Gemini API (`generativelanguage.googleapis.com`) | plan / SQL generation / answer composition | Answer run fails with a clear surfaced error naming `.env`/network; audit row records failure; UI shows human message |
| MsSQL server (Phase 3) | nightly extract source | Sync marked failed + surfaced in sources panel; previous extract stays live; daytime questions unaffected |
| SMTP (Phase 4) | report email delivery | Delivery marked failed and retried; report remains downloadable |

## Stack

- **Language:** Python 3.11+
- **Agent framework:** LangGraph (conditional retry loop requires a graph, not a chain)
- **LLM provider + model:** Gemini — `gemini-3.1-pro` default, env-overridable via `AGENT_LLM_MODEL`; `gemini-2.5-flash` is the documented low-cost alternative. Provider abstraction retains Anthropic support (`AGENT_ANTHROPIC_API_KEY` switches provider automatically).
- **Backend:** FastAPI + uvicorn, port 8001; SSE via `StreamingResponse`
- **Database + ORM:** SQLite + SQLAlchemy 2.0 (app DB `data/agent.db`, Alembic migrations). **Analytics store:** separate SQLite file `data/agent-analytics.db`, written by ingest only, opened `mode=ro` with a deny-by-default authorizer for agent queries.
- **Frontend:** Next.js 15 static export + React 19 + Tailwind v4, served by FastAPI at `/app`
- **Dependency management:** uv (Python) / pnpm (frontend)

| Key library | Version | Purpose |
|-------------|---------|---------|
| pandas | ≥2.2 | CSV parsing, type inference, chunked load to SQLite |
| langgraph | ≥0.4 | agent graph |
| google-genai | ≥1.16 | Gemini SDK (non-stream + stream + usage metadata) |
| sse-starlette-style manual SSE | n/a | plain `StreamingResponse` with `text/event-stream`; no extra dep |
| react-markdown + remark-gfm | ^9 / ^4 | render LLM markdown answers |
| @playwright/test | ^1.49 | E2E suite (`tests/e2e`) |

> **Assumed:** SQLite as the analytics engine because intake chose "baseline only" (no DuckDB). Decision point recorded: if Phase 3 MsSQL extract volumes make aggregate queries exceed the 30 s latency budget, swap the analytics store to DuckDB behind `src/ingest/store.py` — the interface (load table / run read-only SQL) is designed so nothing else changes.

**Avoid:** any ORM access to `ds_*` tables (raw read-only SQL only); LLM SDK calls outside `src/llm`; sending result sets >50 rows or raw rows to the LLM; `pnpm dev` as a test path (static-export + basePath makes `:3000` misleading — single origin `:8001/app/` only).

## Deployment Model

Prototype: single process on the user's machine (`uv run python -m src`), SQLite files under `data/`. Same shape deploys to an on-prem server later; PostgreSQL for the app DB and DuckDB for analytics are the documented scale-up swaps (Phase 3+ decision points), neither required for v0.1.

## Security & Privacy Boundaries

- Agent SQL runs on a read-only connection with an allow-list authorizer (SELECT/READ/FUNCTION only), statement timeout (`AGENT_SQL_TIMEOUT_S`, default 8 s), single-statement enforcement, and a hard row cap (200 fetched, ≤50 serialized to the LLM).
- Uploads are size-capped (`AGENT_MAX_UPLOAD_MB`, default 120) and parsed as data only (no formulas/macros).
- Secrets live in `.env` (gitignored); the server never returns them; logs never contain key material.
- The audit trail (runs) records question, SQL, result summary, timings, and token counts — not full result payloads beyond the stored preview.
