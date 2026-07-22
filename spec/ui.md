# UI

---

## UI Type

Single-page web app (chat + library), served at `http://localhost:8001/app/`. Bilingual surface: UI chrome in English with Hindi step labels; user content in whatever language it was asked/answered in.

## Views / Screens

### Screen: Analyst Workspace (the single page)

**Purpose:** upload data, converse with the analyst, inspect its working.

**Layout:** left sidebar (library + conversations + coming-soon), main chat pane.

**Key elements — sidebar:**
- **Datasets** header + `Upload CSVs` button (multi-select file input; per-file progress; instant refresh on completion).
- Dataset cards: name, row count × column count, source badge (`CSV`), relative upload time; expandable profile (columns with types + null % + top values; warnings); delete (confirm dialog naming the dataset: "This removes <name> and its data. Questions already answered stay in the audit log.").
- **Conversations**: `New conversation` + recent list (title, relative time); clicking loads history.
- **Coming soon** block — labelled, disabled chips with phase tags: Charts (Phase 2), Excel/PDF export (Phase 2), Saved datasets (Phase 2), Data dictionary (Phase 2), MsSQL nightly sync (Phase 3), Scheduled summaries (Phase 3), Login & district roles (Phase 4), Cost dashboard (Phase 4). Tooltip: "Planned — not built yet." A stub must never look like a broken button.

**Key elements — chat pane:**
- Message list: user bubbles (question, as typed, any script) and assistant answers rendered as **markdown** (react-markdown + remark-gfm — tables, bold, lists).
- **While running:** live step ticker replacing a plain spinner — each step's EN + HI label with state (`Reading your data…` ✓, `Writing SQL…` ⏳), then the answer streaming token-wise into the bubble. Elapsed seconds shown after 3 s.
- **Per answer disclosures** (collapsed by default): `SQL` (monospace block, copy button), `Steps` (the full attempt trace incl. retries), `Caveats & assumptions`; result table (first ≤200 rows, sticky header, "showing N of M" when truncated).
- **Follow-up chips**: 2–3 suggested questions under each answer; click = ask.
- Composer: textarea (Enter sends, Shift+Enter newline), disabled while a run is active; placeholder "Ask in English or हिंदी…".

**Actions:** upload, delete dataset, new/switch conversation, ask, click follow-up, expand disclosures, copy SQL.

## Error States

- Upload failure: the file's card shows `status=error` + reason ("Could not parse as CSV — is it an Excel file? Export as CSV first."); other files unaffected.
- Question failure: assistant bubble shows the plain-language error (e.g. "Could not reach the Gemini API — check AGENT_GEMINI_API_KEY in .env") with a Retry button; never a stack trace.
- Empty library: chat empty-state explains the two steps (upload → ask) with an arrow to the upload button; composer works but the agent will ask you to upload first (clarification).
- Loading states: skeleton cards during library fetch; step ticker during runs; button spinners on upload/delete.
- Clarification turns render as a normal assistant question with an "Answering helps me get this right" hint.

## Tech Stack

Next.js 15 static export + React 19 + Tailwind v4 (baseline config untouched: `postcss.config.mjs`, `@source "../";` in `globals.css`), react-markdown + remark-gfm. Single file `frontend/src/app/page.tsx` plus small components in `frontend/src/app/components/` if the file exceeds ~600 lines.
