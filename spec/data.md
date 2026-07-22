# Data Model

---

## Storage Technology

Two SQLite files under `data/` (gitignored):

- **App DB** `data/agent.db` — SQLAlchemy 2.0 + Alembic. Entities below.
- **Analytics store** `data/agent-analytics.db` — one physical table per dataset (`ds_<id>`), written only by ingest (and Phase 3 sync), read by the agent over a read-only connection. No ORM, no migrations (tables are data, created/dropped with their dataset).

## Entities

### Entity: Dataset (`datasets`, app DB)

One uploaded (or, Phase 3, synced) tabular dataset in the library.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | Text (uuid) | yes | PK |
| name | Text | yes | display name (from filename, editable later) |
| original_filename | Text | yes | as uploaded |
| table_name | Text | yes | `ds_<12-hex>` in the analytics store |
| source | Text | yes | `csv` (Phase 3 adds `mssql`) |
| status | Text | yes | `ready` \| `error` |
| error_message | Text | no | parse/load failure reason |
| row_count | Integer | no | full loaded row count |
| size_bytes | Integer | no | upload size |
| columns_json | Text (JSON) | no | `[{name, original_name, type, null_count, distinct_count, min, max, top_values[], description}]` |
| profile_json | Text (JSON) | no | `{warnings[], date_columns[], profiled_rows}` |
| created_at / updated_at | TIMESTAMP | yes | |

### Entity: Conversation (`conversations`, app DB)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | Text (uuid) | yes | PK |
| title | Text | yes | first question, truncated 80 chars |
| created_at / updated_at | TIMESTAMP | yes | |

### Entity: Run (`runs`, app DB — extends the baseline table; the audit trail)

One question→answer turn.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | Text (uuid) | yes | PK |
| conversation_id | Text FK→conversations | no | null for legacy rows |
| status | Text | yes | `pending` \| `completed` \| `failed` \| `clarification` |
| input_text | Text | no | the question, verbatim (baseline column, reused) |
| output_text | Text | no | the final answer markdown (baseline column, reused) |
| error_message | Text | no | |
| language | Text | no | `en` \| `hi` \| `hinglish` |
| sql_text | Text | no | final executed SQL |
| steps_json | Text (JSON) | no | full step/attempt trace |
| result_json | Text (JSON) | no | `{columns, rows≤200, row_count, truncated}` preview |
| caveats_json / followups_json | Text (JSON) | no | |
| input_tokens / output_tokens | Integer | no | usage accounting (cost dashboard source, Phase 4) |
| duration_ms | Integer | no | |
| created_at / updated_at | TIMESTAMP | yes | |

### Relationships

Conversation 1—N Run. Dataset ↔ Run: informational only (dataset_ids inside steps_json), no FK — datasets may be deleted while audit rows remain.

## Data Lifecycle

- Dataset: created on upload; `ds_` table dropped and row deleted on user delete (confirmed in UI). Re-upload = new dataset (no versioning in v0.1).
- Conversation/Run: append-only; no retention limit in v0.1 (audit requirement).
- Analytics store and app DB are local files; backup = copy `data/`.

## Sensitive Data

Uploaded police data stays in local SQLite files, never leaves the machine except as schema + ≤50-row computed aggregates to the LLM API (the intake-agreed boundary). `.env` holds the API key (gitignored). Logs contain SQL and metadata, not raw row dumps beyond the capped previews. Phase 4 adds users/roles; until then the app binds to localhost by default usage.
