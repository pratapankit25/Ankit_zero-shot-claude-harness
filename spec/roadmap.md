# Roadmap

---

## What This Agent Does

A bilingual (Hindi/English) data-analyst agent for Uttar Pradesh Police. Users upload CSV exports (FIR/crime records, Dial-112 call logs, personnel/admin data, ad-hoc extracts from the department MsSQL system) into a persistent dataset library, then ask questions in plain language. The agent profiles every upload automatically, chooses the relevant datasets itself, writes and runs SQL over the full data, checks its own results, and answers in the language the question was asked in — with the numbers, the SQL, its working steps, caveats, and suggested follow-ups. Later phases add charts and exports, a nightly low-load sync from the large MsSQL database, scheduled summaries, and role-based access.

## Who Uses It

- **The district/HQ data cell** — daily, as their main analysis tool (primary persona).
- **Senior officers** — occasionally, before reviews and briefings; they read answers and circulate reports.
- **Officers across districts** — concurrently, on demand (supported from Phase 4 with roles).

## Core Problem Being Solved

Today, answering "how many FIRs under section X in district Y last quarter, and is it rising?" means finding the right export, opening Excel, building pivots by hand — or raising a request to the data cell and waiting days. Ad-hoc questions against the large MsSQL system either don't get asked or load the production DB. This agent turns those questions into seconds-long conversations over a local store that never touches the production DB during the day.

## Success Criteria

- [ ] A user can upload multiple CSVs (up to ~100 MB each) and see an automatic profile of each within seconds of load completing.
- [ ] A question asked in English or Hindi about the uploaded data returns a correct, verifiable answer (SQL shown on demand) computed over the **full** dataset — validated against fixtures with pre-computed ground truths.
- [ ] Follow-up questions resolve against conversation context ("now break that down by district").
- [ ] Every question is auditable: question, SQL, result, timings, and token usage stored per run.
- [ ] (Phase 3) Daytime questions over MsSQL-sourced data hit only the local store — zero daytime queries against the MsSQL server.

## What This Agent Does NOT Do (Out of Scope)

- No writes of any kind to source systems — the MsSQL connection is read-only, extract-only, off-peak-only.
- No row-level data sent to the LLM API — schema and small computed aggregates only.
- No WhatsApp delivery and no portal embedding/SSO in v0.1 (listed for a future version; email delivery is Phase 4).
- No free-form code execution — the agent generates **SQL only**, validated read-only before running.
- No predictive policing / person-targeting analytics; it answers aggregate analytical questions about the data it is given.

## Key Constraints

- **Privacy line:** the LLM sees dataset schemas, column profiles, and small computed result tables (≤50 rows) — never raw uploads or full result dumps.
- **Cost:** very low running cost; one LLM provider (Gemini), minimal calls per question (adaptive depth).
- **DB load:** the future MsSQL DB is touched only by scheduled off-peak extracts (Phase 3), never by daytime user questions.
- **Latency:** typical answers < 30 s on 100 MB-scale datasets.
- **Prototype deployment:** user's machine first; server deployment later without redesign.
- **Build reality (this session):** built in a cloud sandbox that cannot reach the Gemini API — real-LLM gate tests are written to run on the user's machine (`AGENT_SKIP_LLM_TESTS=1` skips only in the sandbox; the user's gate runs them for real).

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** Real on the tested path, labelled stubs for everything later.

### Phase 1 — Ask Your Data (upload → profile → ask → answer)

- **Goal:** Upload CSVs into a persistent library, ask questions in English or Hindi in a conversation, get correct streamed answers with live step ticker, SQL/steps/caveats on demand, follow-up suggestions, and a full audit record per question.
- **Capabilities:** [upload-datasets](capabilities/upload-datasets.md), [ask-question](capabilities/ask-question.md), [conversation-history](capabilities/conversation-history.md), [audit-trail](capabilities/audit-trail.md)
- **Independent slices (parallel build units):**
  - `db-and-domain` (backend) — migration 0002, models, domain schemas; deps: none
  - `ingest` (backend) — CSV parsing/loading/profiling into the analytics store; deps: none
  - `agent-graph` (backend) — LangGraph nodes/edges/state/prompts for plan→SQL→execute→check→compose; deps: none
  - `api-routes` (backend) — datasets, questions (SSE), conversations routers; deps: db-and-domain, ingest, agent-graph (wiring only)
  - `frontend-app` (frontend) — full UI: library sidebar, chat, ticker, disclosures, stubs; deps: none (contract fixed in spec/api.md)
  - `fixtures-and-tests` (backend) — synthetic UP-police fixture CSVs with pre-computed answers; unit/integration/e2e suites; deps: none
- **Key surfaces / files:** `src/db/models.py`, `alembic/versions/0002_*.py`, `src/ingest/*`, `src/graph/*`, `src/prompts/*.md`, `src/api/{datasets,questions,conversations,runs}.py`, `src/domain/*`, `frontend/src/app/page.tsx`, `tests/{unit,integration,e2e,fixtures}/*`
- **Gate command:** `uv run alembic upgrade head && uv run pytest tests/ -v && cd frontend && pnpm build && cd .. && npx playwright test tests/e2e --reporter=line` (real Gemini key in `.env`; run on a machine that can reach the Gemini API)
- **How the user tests it:** `uv sync --extra dev`, set `AGENT_GEMINI_API_KEY` in `.env`, `cd frontend && pnpm install && pnpm build && cd ..`, `uv run alembic upgrade head`, `uv run python -m src`, open `http://localhost:8001/app/` → upload `tests/fixtures/samples/*.csv`, watch profiles appear, ask "Which district had the most FIRs in 2025?" then "अब महीने के हिसाब से दिखाओ" → correct streamed answers, SQL visible under each. **Real:** everything on that path. **Labelled stubs:** Charts, Excel/PDF export, Saved datasets, Data dictionary (Phase 2); MsSQL sync, Scheduled summaries (Phase 3); Login/roles, Cost dashboard (Phase 4).

### Phase 2 — Richer Answers (charts, exports, saved datasets, dictionary)

- **Goal:** Answers gain charts and downloadable exports; users can save derived tables and teach the agent column meanings; the agent flags anomalies it notices.
- **Capabilities:** [charts](capabilities/charts.md), [export-results](capabilities/export-results.md), [derived-datasets](capabilities/derived-datasets.md), [data-dictionary](capabilities/data-dictionary.md), [anomaly-flags](capabilities/anomaly-flags.md)
- **Independent slices:** `chart-spec-node` (backend), `export-endpoints` (backend), `dictionary-and-derived` (backend), `frontend-rich` (frontend). Deps: frontend-rich consumes the three backend slices' contracts.
- **Key surfaces / files:** `src/graph/nodes.py` (chart node), `src/api/{exports,dictionary,datasets}.py`, `frontend/src/app/page.tsx` (chart render, export buttons, dictionary editor)
- **Gate command:** `uv run pytest tests/ -v && npx playwright test tests/e2e --reporter=line` (real key)
- **How the user tests it:** ask a trend question → chart renders; click Export → Excel downloads; save a result as dataset; edit a column description and see the next answer use it; upload a file with a data gap → anomaly flag appears.

### Phase 3 — MsSQL, Fresh & Light (nightly sync, freshness, schedules)

- **Goal:** The large MsSQL DB becomes a data source without daytime load: configured tables extracted off-peak into the local store, freshness visible on every dataset and answer, and scheduled daily/weekly summary reports generated automatically.
- **Capabilities:** [mssql-nightly-sync](capabilities/mssql-nightly-sync.md), [data-freshness](capabilities/data-freshness.md), [scheduled-summaries](capabilities/scheduled-summaries.md)
- **Independent slices:** `mssql-connector` (backend), `scheduler` (backend), `frontend-sources` (frontend: sources panel, freshness badges, schedule config).
- **Key surfaces / files:** `src/sources/mssql.py`, `src/scheduler/*`, `src/api/sources.py`, `frontend/src/app/page.tsx`
- **Gate command:** `uv run pytest tests/ -v` (MsSQL tests against a disposable SQL Server via Docker or the user's dev instance; real key)
- **How the user tests it:** configure a test MsSQL source + table list, trigger "sync now", see the dataset appear with freshness "as of tonight's sync"; ask a question against it; enable a daily summary and view the generated report.

### Phase 4 — Many Hands, Safely (login, roles, cost, reports, email)

- **Goal:** Multi-user readiness: admin-created accounts with district-level roles, an admin cost dashboard with daily totals, bilingual (Hindi+English) PDF briefing reports, and email delivery of reports and summaries.
- **Capabilities:** [auth-rbac](capabilities/auth-rbac.md), [cost-dashboard](capabilities/cost-dashboard.md), [bilingual-reports](capabilities/bilingual-reports.md), [email-delivery](capabilities/email-delivery.md)
- **Independent slices:** `auth-backend`, `reports-backend`, `email-backend`, `frontend-admin`.
- **Key surfaces / files:** `src/auth/*`, `src/reports/*`, `src/api/{auth,admin}.py`, `frontend/src/app/*`
- **Gate command:** `uv run pytest tests/ -v && npx playwright test tests/e2e --reporter=line` (real key)
- **How the user tests it:** log in as admin, create a district user, confirm they see only their district's datasets; view the cost dashboard; generate a bilingual PDF; receive it by email.
