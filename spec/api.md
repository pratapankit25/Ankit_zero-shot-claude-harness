# API

---

## API Style

REST + one SSE streaming endpoint. Every JSON route returns the envelope `{"data": ..., "error": null}` or raises `{"detail": {"code", "message"}}`. All routes are unauthenticated in v0.1 (Phase 4 adds auth).

## Endpoints

### `POST /datasets`

**Purpose:** upload one or more CSVs into the library (multipart form, repeated `files` field).

**Request:** `multipart/form-data`, field `files` (1..10 per call), each ≤ `AGENT_MAX_UPLOAD_MB` MB.

**Response:** `{"data": [Dataset, ...]}` — each with `id, name, status, row_count, columns, profile`; a file that failed to parse comes back `status="error"` with `error_message` (other files still load).

| Status | Condition |
|--------|-----------|
| 400 | no files / a file exceeds size cap / not parseable as CSV at all (that entry errors, request still 200 if any file present; 400 only when zero files) |
| 413 | file over size cap |

### `GET /datasets`

**Purpose:** the library. **Response:** `{"data": [Dataset]}` newest first.

### `DELETE /datasets/{id}`

**Purpose:** remove a dataset and drop its `ds_` table. **Response:** `{"data": {"deleted": true}}`. 404 unknown id.

### `POST /questions/stream`

**Purpose:** ask a question; stream progress + answer. **Request:**
```json
{ "question": "Which district had the most FIRs in 2025?", "conversation_id": "optional-uuid" }
```
**Response:** `text/event-stream`. Events, in order:
```
event: run        data: {"run_id", "conversation_id"}
event: step       data: {"label_en", "label_hi", "status": "start"|"done", "detail"?}   (repeats)
event: answer_delta data: {"text"}                                                      (repeats)
event: final      data: {"run": RunDetail}
event: error      data: {"message"}    (terminal, instead of final)
```
422 empty question; a missing/invalid `conversation_id` starts a new conversation.

### `POST /questions`

**Purpose:** same, non-streaming (integration tests, API consumers). **Response:** `{"data": RunDetail}`.

`RunDetail` = `{run_id, conversation_id, status, question, answer, language, sql, steps[], result{columns,rows,row_count,truncated}, caveats[], followups[], usage{input_tokens,output_tokens}, duration_ms, error}`.

### `GET /conversations`

**Response:** `{"data": [{id, title, updated_at, run_count}]}` newest first.

### `GET /conversations/{id}`

**Response:** `{"data": {id, title, runs: [RunDetail]}}` oldest first (chat reload). 404 unknown.

### `GET /runs/{run_id}` *(baseline, kept — audit detail)*

**Response:** `{"data": RunDetail}`. 404 unknown.

### `GET /health` *(baseline, kept)*

`{"data": {"status": "ok"}}`

## Authentication

None in v0.1 (localhost prototype, per intake). Phase 4: session auth with admin-created accounts + district roles; every endpoint then scopes datasets/conversations by role.
