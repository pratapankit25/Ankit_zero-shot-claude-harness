# Agent

---

## Agent Architecture Pattern

**Chosen:** Graph (LangGraph) — a ReAct-style loop with explicit nodes and a conditional retry edge (write_sql → execute → check → retry/compose), plus a clarification branch. Cites patterns #17 ReAct, #5 Tool Use (SQL execution as the single tool), #18 Guardrails (SQL validator), #12 Exception Handling (retry with error feedback), #8 Memory (conversation history), #16 Resource-Aware (adaptive depth: simple questions take the shortest path through the same graph).

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| plan | Gemini | `gemini-3.1-pro` (via `AGENT_LLM_MODEL`) | one model for all nodes keeps cost/config simple in v0.1 |
| write_sql | Gemini | same | SQL quality matters most here |
| compose_answer | Gemini | same, **streaming** | streamed deltas to the UI |

**Fallback behaviour:** provider errors are caught per node → `state.error` → `handle_error` → run recorded `failed` with a clear message ("Could not reach the Gemini API — check AGENT_GEMINI_API_KEY in .env / network"). One automatic retry on transient 429/5xx with 2 s backoff inside the LLM client. No stub path — a failed LLM call is a failed run, visibly.

**Prompt strategy:** system prompts are `.md` files in `src/prompts/` (`plan.md`, `sql.md`, `answer.md`). plan and write_sql demand strict JSON (parsed with one repair retry: the malformed output is sent back with "return valid JSON only"). compose_answer is free-form markdown, streamed. Language rule in every prompt: reply in the language of the user's question (Hindi → Hindi/Devanagari, Hinglish → Hinglish, English → English); SQL and JSON keys always English.

## Tools & Tool Calling

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `run_sql` (in-graph, code) | validate + execute one read-only SELECT against the analytics store | sql: str | rows (≤200), columns, truncated flag, row_count, error | none (read-only connection) |

**Tool selection strategy:** none needed — `execute_sql` is the only action node; the LLM chooses *what SQL*, never *which tool*.

**Tool failure handling:** SQL error text is fed back verbatim to `write_sql` on retry (≤ `AGENT_MAX_SQL_ITERATIONS`, default 4); timeout and validation rejections count as failures with explanatory text.

## Agent State

```python
class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                    # set by runner
    conversation_id: str           # set by runner

    # Input
    question: str                  # user's question, verbatim
    history: list[dict]            # prior turns [{question, answer, sql}], newest last, ≤10
    datasets: list[dict]           # registry snapshot: [{id, table_name, name, columns:[{name,type,description}], row_count}]

    # Pipeline (populated progressively)
    language: str                  # "en" | "hi" | "hinglish" — set by plan
    mode: str                      # "answer" | "clarify" — set by plan
    plan: dict                     # {approach, dataset_ids, steps[]}
    sql: str                       # current SQL attempt
    sql_attempts: list[dict]       # [{sql, error | row_count}] — full trace
    iterations: int                # write_sql count
    result: dict                   # {columns, rows≤200, row_count, truncated}
    steps: list[dict]              # user-facing ticker log [{label, detail, status}]

    # Output
    answer: str                    # final markdown (streamed during compose)
    caveats: list[str]
    followups: list[str]
    usage: dict                    # {input_tokens, output_tokens}

    # Control
    error: str | None
    status: str                    # completed | failed | clarification
```

## Nodes / Steps

### `prepare_context`
**Reads:** run_id, conversation_id, question. **Writes:** history, datasets, steps. **LLM:** no.
Loads dataset registry (schemas + profiles + dictionary descriptions) and the last ≤10 turns of this conversation from the app DB. Fails fatally (`error`) only if the registry is unreadable; an empty library is not an error (plan handles it with a "no datasets yet" clarification).

### `plan`
**Reads:** question, history, datasets. **Writes:** language, mode, plan | clarification text (in `answer`), steps. **LLM:** yes — `plan.md`, JSON out: `{language, mode, clarification?, approach?, dataset_ids?, steps?}`.
Detects language; decides clarify vs answer (clarify only when genuinely ambiguous — e.g. "show me the data" with 6 datasets); selects datasets; for complex questions outlines 1–4 sub-steps, for simple ones a single step. Empty library → mode=clarify with guidance to upload.

### `write_sql`
**Reads:** plan, datasets (selected schemas + column profiles), sql_attempts (incl. prior errors), question, history. **Writes:** sql, iterations, steps. **LLM:** yes — `sql.md`, JSON `{sql}`.
Generates ONE SQLite SELECT over `ds_*` tables (joins allowed) answering the question/current step. Prompt embeds: schema DDL, column descriptions, top values for categoricals (so it filters on real spellings, e.g. district names), today's date, and hard rules (single SELECT, no writes, LIMIT ≤ 200 unless aggregating).

### `execute_sql`
**Reads:** sql. **Writes:** result | attempt error, sql_attempts, steps. **LLM:** no.
| System | Operation | On Failure |
|--------|-----------|------------|
| Analytics store (SQLite ro) | validated SELECT | attempt error recorded → check routes to retry; never fatal until iterations exhausted |
Validation: single statement, authorizer allows SELECT/READ/FUNCTION only, 8 s progress-handler timeout, fetch cap 200 + truncated flag.

### `check_result` *(edge function, no LLM)*
attempt error or empty result, and iterations < max → back to `write_sql` (error/emptiness fed into the next prompt). Otherwise → `compose_answer`. Iterations exhausted with no result → `handle_error` (message includes last SQL error).

### `compose_answer`
**Reads:** question, language, plan, sql, result (≤50 rows serialized), history, sql_attempts. **Writes:** answer (streamed), caveats, followups, usage, steps. **LLM:** yes — `answer.md`, streaming; after the stream, one cheap JSON extraction of `{caveats[], followups[]}` from the same call's tail section (the prompt asks for answer, then `---CAVEATS---` / `---FOLLOWUPS---` blocks parsed by code — no second LLM call).
Answers in the question's language with exact numbers from the result, states assumptions/filters, flags data-quality issues it can see (empty groups, truncation), proposes 2–3 follow-ups.

### `finalize`
**Reads:** everything. **Writes:** status. **LLM:** no. Persists the run row (answer, sql, steps, result preview, caveats, followups, usage, duration, language, status=completed|clarification).

### `handle_error`
Persists run status=failed with `error_message`; emits a human-readable error event.

## Graph / Flow Topology

```
START → prepare_context ──(error)──► handle_error ──► END
            │
            ▼
          plan ──(error)──► handle_error
            │ (mode=clarify)──────────────► finalize ──► END
            ▼ (mode=answer)
        write_sql ──(error)──► handle_error
            │
            ▼
       execute_sql
            │
   check_result (edge)
    │ retry (err/empty, iter<max)──► write_sql
    │ exhausted ──► handle_error
    ▼ ok
     compose_answer ──(error)──► handle_error
            │
            ▼
        finalize ──► END
```

| Source | Condition | Target |
|--------|-----------|--------|
| prepare_context | state.error | handle_error |
| plan | mode == "clarify" | finalize |
| plan | mode == "answer" | write_sql |
| execute_sql → check_result | attempt failed/empty AND iterations < max | write_sql |
| execute_sql → check_result | attempt failed AND iterations ≥ max | handle_error |
| execute_sql → check_result | result ok | compose_answer |

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| Within a run | LangGraph state | everything above |
| Conversation | app DB `runs` rows per conversation | question, answer, sql per turn; last 10 loaded into `history` |
| Across sessions | app DB `datasets` (+ descriptions) | the persistent library and its dictionary |

**Context window management:** history capped at 10 turns with answers truncated to 500 chars; schemas capped at 40 columns per dataset in prompts (rest summarized); result serialization to LLM capped at 50 rows / 4,000 chars.

## Streaming & Progress Events

The runner registers an in-process emitter (per run_id) that nodes use to publish: `step` events (bilingual label EN + HI, e.g. "Writing SQL / SQL लिख रहा हूँ"), `answer_delta` chunks during compose, and `final`/`error`. The API layer bridges the emitter queue to SSE. Tests subscribe a collector to assert event order.

## Human-in-the-Loop Checkpoints

| Checkpoint | Shown | Action | Timeout |
|------------|-------|--------|---------|
| Clarification turn | the agent's clarifying question as the answer (status=clarification) | user replies in the conversation | none — it's a normal turn |

## Error Handling & Recovery

**Node-level:** every node try/excepts; fatal → `state.error` → handle_error. **Graph-level:** handle_error persists failed run + emits `error` SSE with a plain-language message (never a stack trace). **Resume:** none in v0.1 — runs are seconds-long; the user re-asks. **Partial failure:** SQL retry loop is the partial-failure path; a failed caveat/followup parse degrades to empty lists, never fails the run.

## Observability

| Signal | What | Where |
|--------|------|-------|
| Node events | node name, run_id, duration, outcome | structlog JSON → stdout |
| LLM calls | model, latency, input/output tokens, node | structlog JSON |
| SQL | full SQL, duration, row_count, truncated, error | structlog JSON + `runs.steps_json` |
| Run outcome | status, total duration, usage totals | app DB `runs` + log |

LangSmith optional: honored via standard `LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY` envs when set; never required.

## Concurrency Model

- **Run isolation:** parallel runs, each scoped by run_id (per-run emitter registry); SQLite WAL mode on the app DB.
- **Parallel nodes:** none within a run (the loop is sequential by design).
- **Checkpointing:** none (short runs).

## Graph Assembly (`src/graph/agent.py`)

```python
g = StateGraph(AgentState)
for name, fn in [("prepare_context", prepare_context), ("plan", plan),
                 ("write_sql", write_sql), ("execute_sql", execute_sql),
                 ("compose_answer", compose_answer), ("finalize", finalize),
                 ("handle_error", handle_error)]:
    g.add_node(name, fn)
g.set_entry_point("prepare_context")
g.add_conditional_edges("prepare_context", after_prepare, {"plan": "plan", "handle_error": "handle_error"})
g.add_conditional_edges("plan", after_plan, {"write_sql": "write_sql", "finalize": "finalize", "handle_error": "handle_error"})
g.add_conditional_edges("write_sql", after_write_sql, {"execute_sql": "execute_sql", "handle_error": "handle_error"})
g.add_conditional_edges("execute_sql", check_result, {"write_sql": "write_sql", "compose_answer": "compose_answer", "handle_error": "handle_error"})
g.add_conditional_edges("compose_answer", after_compose, {"finalize": "finalize", "handle_error": "handle_error"})
g.add_edge("finalize", END); g.add_edge("handle_error", END)
agentic_ai = g.compile()
```
