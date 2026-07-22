# UP Police Data Analyst

A bilingual (Hindi/English) data-analyst agent. Upload CSV exports — FIR records, Dial-112 logs, personnel data, ad-hoc MsSQL extracts — into a persistent library, then ask questions in plain language. The agent profiles every upload, writes and runs read-only SQL over the **full** data, checks its own results, and streams back answers with the SQL, its working steps, caveats, and suggested follow-ups. Officers act on these numbers, so every question is audited: question, SQL, result, timings, tokens.

Built spec-first with the [zero-shot SDD harness](spec/roadmap.md) — the full spec lives in `spec/`. Phase 1 of 4 is complete; Charts/exports (2), MsSQL nightly sync + scheduled summaries (3), and login/roles/cost dashboard (4) are next and appear in the UI as labelled "Coming soon" stubs.

**Privacy line:** the LLM API receives dataset schemas, column profiles, and small computed aggregates (≤50 rows) — never raw data rows. The eventual MsSQL DB is reached only by off-peak extracts (Phase 3), never by daytime questions.

---

> **All commands run from the repo root.** Every command is copy-paste runnable exactly as written.

## Setup (once)

**Windows, easiest path:** double-click **`Start-Windows.bat`** in the repo root — it checks/installs the tools, asks for your Gemini key once, builds everything, starts the server, and opens the browser itself. Keep its window open while using the app. If it shows a red PROBLEM line, screenshot the window.

Manual path — requires: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20+, [pnpm](https://pnpm.io).

Linux / macOS (bash):

```bash
cp .env.example .env
# edit .env → set AGENT_GEMINI_API_KEY=<your key>   (or AGENT_ANTHROPIC_API_KEY)
uv sync --extra dev
cd frontend && pnpm install && pnpm build && cd ..
pnpm install                      # root: Playwright for E2E tests
npx playwright install chromium   # E2E browser (one-time download)
uv run alembic upgrade head
uv run alembic current            # must print "0002 (head)" — blank output means no migration ran
```

Windows (PowerShell) — one command per line (old PowerShell doesn't support `&&`):

```powershell
copy .env.example .env
# edit .env → set AGENT_GEMINI_API_KEY=<your key>
uv sync --extra dev
cd frontend
pnpm install
pnpm build
cd ..
pnpm install
npx playwright install chromium
uv run alembic upgrade head
uv run alembic current            # must print "0002 (head)"
```

Missing tools on Windows: uv → `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` · Node 20+ → nodejs.org · pnpm → `npm install -g pnpm`.

## Run

```bash
uv run python -m src
```

Open **http://localhost:8001/app/** (note the trailing slash). API docs: http://localhost:8001/docs · Health: http://localhost:8001/health

## First test drive (2 minutes)

1. Click **Upload CSVs** → pick the three files in `tests/fixtures/samples/` (synthetic, fictional data).
2. Watch each dataset appear with an automatic profile (rows, column types, top values).
3. Ask: `Which district had the most FIRs registered in 2025? Give the exact count.` → expect **Lucknow, 276**, streamed live, with the SQL under the answer.
4. Follow up: `अब उस जिले के आँकड़े महीने के हिसाब से दिखाइए` → a Hindi answer for the same district, month by month.

## Tests

```bash
uv run pytest tests/unit -v                 # no key / no network needed
uv run pytest tests/ -v                     # + real-LLM integration gate (key in .env required)
npx playwright test tests/e2e --reporter=line   # E2E against the running server (start it first)
```

The Phase-1 gate (real LLM + full fixtures + E2E) is:

```bash
uv run alembic upgrade head && uv run pytest tests/ -v && npx playwright test tests/e2e --reporter=line
```

Real-LLM tests assert **exact pre-computed numbers** from `tests/fixtures/expected_answers.json` — regenerate fixtures with `uv run python tests/fixtures/generate.py`.

*Authoring note:* this phase was built in a cloud sandbox that cannot reach the Gemini API; there, `AGENT_SKIP_LLM_TESTS=1` and `E2E_LLM=0` skip the real-LLM tests. **Do not set these when gating** — on your machine the gate above runs everything for real.

## What's real vs stubbed (Phase 1)

Real end-to-end: multi-CSV upload (encoding/delimiter tolerant, Devanagari-safe, full load — never sampled), auto-profiling, EN/HI/Hinglish questions, LangGraph plan→SQL→execute→self-check→retry loop, cross-dataset joins, clarification on ambiguity, streamed answers + live step ticker, per-answer SQL/steps/caveats/follow-ups, persistent conversations with context, full audit trail (`GET /runs/{id}`), read-only SQL guardrails (authorizer, timeout, row caps).

Labelled stubs (sidebar "Coming soon"): charts, Excel/PDF export, saved datasets, data dictionary editing (Phase 2); MsSQL nightly sync, scheduled summaries (Phase 3); login & district roles, cost dashboard (Phase 4).

## Architecture (one paragraph)

FastAPI (port 8001) serves the API + the static Next.js UI at `/app`. Uploads load into a separate SQLite **analytics store** (`data/agent-analytics.db`); app metadata (datasets registry, conversations, audit runs) lives in `data/agent.db` via SQLAlchemy/Alembic. A LangGraph agent answers questions; the provider-agnostic LLM client (Gemini default, Anthropic supported — auto-detected from whichever key is in `.env`) streams tokens and reports usage. Full design: `spec/architecture.md`, agent graph: `spec/agent.md`.

## Troubleshooting

- **Answer fails with "model was not found"** → set `AGENT_LLM_MODEL` in `.env` to a model your key can access (e.g. `gemini-2.5-flash`), restart.
- **"Could not reach the LLM API"** → check the key in `.env` and your network/proxy.
- **UI loads unstyled or 404s** → rebuild the frontend: `cd frontend && pnpm build && cd ..`, restart the server, open `/app/` with the trailing slash.
- **`alembic current` prints nothing** → the migration didn't apply; check `AGENT_DATABASE_URL` in `.env`.
