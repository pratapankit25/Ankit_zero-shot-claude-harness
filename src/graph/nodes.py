"""Graph nodes: prepare_context → plan → write_sql → execute_sql → compose_answer → finalize.

Spec: spec/agent.md. LLM sees schemas + profiles + ≤ settings.llm_result_rows result rows —
never raw uploads (spec/architecture.md privacy boundary).
"""
import json
import re
import time
from pathlib import Path

from config.settings import get_settings
from db.models import ConversationRow, DatasetRow, RunRow
from db.session import create_db_session
from graph.anomalies import build_flags
from graph.charts import build_chart_spec
from graph.state import AgentState
from graph.stream import emit, emit_step
from ingest import store
from llm.client import LLMClient, LLMError
from observability.events import get_logger

_PROMPTS = Path(__file__).parent.parent / "prompts"
log = get_logger("graph")


def _prompt(name: str) -> str:
    return (_PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()


def _parse_json_block(text: str) -> dict:
    """Extract the first JSON object from LLM text (tolerates ``` fences)."""
    cleaned = re.sub(r"```(?:json)?", "", text or "").strip().strip("`")
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object found in: {cleaned[:200]!r}")
    return json.loads(match.group(0))


def _llm_json(client: LLMClient, system: str, prompt: str, usage: dict) -> dict:
    """One JSON generation with a single repair retry on malformed output."""
    result = client.generate(prompt, system=system)
    _track(usage, result)
    try:
        return _parse_json_block(result.text)
    except (ValueError, json.JSONDecodeError):
        repair = client.generate(
            f"{prompt}\n\nYour previous reply was not valid JSON:\n{result.text[:1000]}\n\n"
            "Return ONLY the valid JSON object now.",
            system=system,
        )
        _track(usage, repair)
        return _parse_json_block(repair.text)


def _track(usage: dict, result) -> None:
    usage["input_tokens"] = usage.get("input_tokens", 0) + result.input_tokens
    usage["output_tokens"] = usage.get("output_tokens", 0) + result.output_tokens


def _dataset_catalog(datasets: list, *, selected_ids: list | None = None, full: bool) -> str:
    """Serialize the registry for prompts. full=True includes per-column profile detail."""
    lines: list[str] = []
    for d in datasets:
        if selected_ids and d["id"] not in selected_ids:
            continue
        lines.append(f"Dataset id={d['id']} table={d['table_name']} name=\"{d['name']}\" rows={d['row_count']}")
        cols = d.get("columns", [])[:40]
        for c in cols:
            bits = [f"  - {c['name']} ({c['type']})"]
            if c.get("description"):
                bits.append(f"meaning: {c['description'][:200]}")
            if c.get("null_count"):
                bits.append(f"nulls: {c['null_count']}")
            if c.get("min") is not None:
                bits.append(f"range: {c['min']}..{c['max']}")
            if full and c.get("top_values"):
                bits.append("top values: " + ", ".join(repr(v)[:60] for v in c["top_values"]))
            lines.append("; ".join(bits))
        if len(d.get("columns", [])) > 40:
            lines.append(f"  … and {len(d['columns']) - 40} more columns")
    return "\n".join(lines) if lines else "(the library is empty — no datasets uploaded yet)"


def _history_text(history: list) -> str:
    if not history:
        return "(no prior turns)"
    parts = []
    for h in history:
        parts.append(f"User: {h['question']}\nAnalyst: {(h.get('answer') or '')[:500]}")
        if h.get("sql"):
            parts.append(f"(SQL used: {h['sql'][:300]})")
    return "\n".join(parts)


# ---------------------------------------------------------------- nodes

def prepare_context(state: AgentState) -> AgentState:
    try:
        emit_step(state, "Reading your data library", "आपकी डेटा लाइब्रेरी पढ़ रहा हूँ", "start")
        s = get_settings()
        with create_db_session() as session:
            ds_rows = (
                session.query(DatasetRow)
                .filter(DatasetRow.status == "ready")
                .order_by(DatasetRow.created_at.desc())
                .all()
            )
            allowed_district = state.get("user_district")  # set for district-scoped viewers
            datasets = [
                {
                    "id": r.id,
                    "name": r.name,
                    "table_name": r.table_name,
                    "row_count": r.row_count,
                    "columns": json.loads(r.columns_json or "[]"),
                    "source": r.source,
                    "district": r.district,
                    "synced_at": r.synced_at.isoformat() if r.synced_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in ds_rows
                if allowed_district is None or r.district is None or r.district == allowed_district
            ]
            history: list = []
            conv_id = state.get("conversation_id")
            if conv_id:
                runs = (
                    session.query(RunRow)
                    .filter(
                        RunRow.conversation_id == conv_id,
                        RunRow.id != state["run_id"],
                        RunRow.status.in_(["completed", "clarification"]),
                    )
                    .order_by(RunRow.created_at.desc())
                    .limit(s.history_turns)
                    .all()
                )
                history = [
                    {"question": r.input_text or "", "answer": r.output_text or "", "sql": r.sql_text or ""}
                    for r in reversed(runs)
                ]
        state["steps"][-1]["status"] = "done"
        return {**state, "datasets": datasets, "history": history, "usage": {"input_tokens": 0, "output_tokens": 0}}
    except Exception as exc:
        log.error("prepare_context.failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"Could not read the dataset library: {exc}"}


def plan(state: AgentState) -> AgentState:
    try:
        emit_step(state, "Understanding the question", "सवाल समझ रहा हूँ", "start")
        client = LLMClient()
        usage = state.get("usage", {})
        prompt = (
            f"DATASET CATALOG:\n{_dataset_catalog(state['datasets'], full=False)}\n\n"
            f"CONVERSATION SO FAR:\n{_history_text(state['history'])}\n\n"
            f"USER QUESTION:\n{state['question']}"
        )
        data = _llm_json(client, _prompt("plan"), prompt, usage)

        language = data.get("language") or "en"
        mode = data.get("mode") or "answer"
        known_ids = {d["id"] for d in state["datasets"]}
        dataset_ids = [i for i in (data.get("dataset_ids") or []) if i in known_ids]
        if mode == "answer" and not dataset_ids:
            if not state["datasets"]:
                mode = "clarify"
                data["clarification"] = data.get("clarification") or (
                    "अभी लाइब्रेरी में कोई डेटा नहीं है — पहले बाईं ओर से CSV फ़ाइल अपलोड करें।"
                    if language in ("hi", "hinglish")
                    else "There's no data in the library yet — upload a CSV from the left panel first."
                )
            else:
                dataset_ids = [d["id"] for d in state["datasets"]]

        state["steps"][-1]["status"] = "done"
        if mode == "clarify":
            answer = (data.get("clarification") or "Could you clarify what you'd like to know?").strip()
            emit(state.get("run_id", ""), {"type": "answer_delta", "text": answer})
            return {**state, "language": language, "mode": "clarify", "answer": answer,
                    "usage": usage, "status": "clarification"}
        plan_obj = {
            "approach": data.get("approach") or "",
            "dataset_ids": dataset_ids,
            "steps": data.get("steps") or ["Answer the question with one query"],
        }
        return {**state, "language": language, "mode": "answer", "plan": plan_obj, "usage": usage}
    except LLMError as exc:
        return {**state, "error": str(exc)}
    except Exception as exc:
        log.error("plan.failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"Planning failed: {exc}"}


def write_sql(state: AgentState) -> AgentState:
    try:
        iteration = state.get("iterations", 0) + 1
        emit_step(
            state,
            "Writing SQL" if iteration == 1 else f"Correcting SQL (attempt {iteration})",
            "SQL लिख रहा हूँ" if iteration == 1 else f"SQL सुधार रहा हूँ (प्रयास {iteration})",
            "start",
        )
        client = LLMClient()
        usage = state.get("usage", {})
        attempts = state.get("sql_attempts", [])
        attempts_text = ""
        if attempts:
            last = attempts[-1]
            outcome = f"ERROR: {last['error']}" if last.get("error") else f"returned {last.get('row_count', 0)} rows (empty)"
            attempts_text = f"\n\nPREVIOUS ATTEMPT:\n{last['sql']}\nOutcome: {outcome}\nFix the cause and return a corrected query."
        prompt = (
            f"TABLES:\n{_dataset_catalog(state['datasets'], selected_ids=state['plan']['dataset_ids'], full=True)}\n\n"
            f"CONVERSATION SO FAR:\n{_history_text(state['history'])}\n\n"
            f"USER QUESTION:\n{state['question']}\n\n"
            f"APPROACH:\n{state['plan']['approach']}\nSteps: {'; '.join(state['plan']['steps'])}"
            f"{attempts_text}"
        )
        data = _llm_json(client, _prompt("sql"), prompt, usage)
        sql = (data.get("sql") or "").strip()
        state["steps"][-1]["status"] = "done"
        state["steps"][-1]["detail"] = sql[:500]
        if not sql:
            return {**state, "iterations": iteration, "usage": usage,
                    "sql_attempts": attempts + [{"sql": "", "error": "model returned no SQL"}]}
        return {**state, "sql": sql, "iterations": iteration, "usage": usage}
    except LLMError as exc:
        return {**state, "error": str(exc)}
    except Exception as exc:
        log.error("write_sql.failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"SQL generation failed: {exc}"}


def execute_sql(state: AgentState) -> AgentState:
    sql = state.get("sql", "")
    attempts = list(state.get("sql_attempts", []))
    emit_step(state, "Running the query on your data", "आपके डेटा पर क्वेरी चला रहा हूँ", "start")
    start = time.monotonic()
    try:
        allowed = [d["table_name"] for d in state.get("datasets", [])] if state.get("user_district") else None
        result = store.run_select(sql, allowed_tables=allowed)
        duration = round((time.monotonic() - start) * 1000)
        attempts.append({"sql": sql, "row_count": result["row_count"], "duration_ms": duration})
        state["steps"][-1]["status"] = "done"
        state["steps"][-1]["detail"] = f"{result['row_count']} rows in {duration} ms"
        log.info("sql.executed", run_id=state.get("run_id"), rows=result["row_count"], ms=duration)
        return {**state, "result": result, "sql_attempts": attempts}
    except store.QueryError as exc:
        attempts.append({"sql": sql, "error": str(exc)})
        state["steps"][-1]["status"] = "error"
        state["steps"][-1]["detail"] = str(exc)[:300]
        log.info("sql.rejected", run_id=state.get("run_id"), error=str(exc))
        return {**state, "result": {}, "sql_attempts": attempts}
    except Exception as exc:
        log.error("execute_sql.failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"Query execution failed: {exc}"}


def compose_answer(state: AgentState) -> AgentState:
    try:
        emit_step(state, "Writing your answer", "आपका जवाब लिख रहा हूँ", "start")
        s = get_settings()
        client = LLMClient()
        usage = state.get("usage", {})
        result = state.get("result", {})

        # Phase 2: deterministic chart + anomaly flags from the executed result
        chart = build_chart_spec(result.get("columns", []), result.get("rows", []))
        flags = build_flags(result, state.get("datasets", []),
                            (state.get("plan") or {}).get("dataset_ids", []), state.get("sql", ""))
        rows = result.get("rows", [])[: s.llm_result_rows]
        result_for_llm = json.dumps(
            {
                "columns": result.get("columns", []),
                "rows": rows,
                "rows_shown_to_you": len(rows),
                "preview_row_count": result.get("row_count", 0),
                "truncated_at_fetch": result.get("truncated", False),
            },
            ensure_ascii=False,
            default=str,
        )[:6000]
        prompt = (
            f"USER QUESTION ({state.get('language', 'en')}):\n{state['question']}\n\n"
            f"CONVERSATION SO FAR:\n{_history_text(state['history'])}\n\n"
            f"SQL EXECUTED:\n{state.get('sql', '')}\n\n"
            f"SQL RESULT (JSON):\n{result_for_llm}"
        )

        run_id = state.get("run_id", "")
        scrubber = _AnswerScrubber(run_id)
        llm_result = client.generate_stream(prompt, system=_prompt("answer"), on_delta=scrubber.on_delta)
        _track(usage, llm_result)
        answer, caveats, followups = _split_answer(llm_result.text)
        scrubber.flush(answer)
        state["steps"][-1]["status"] = "done"
        return {**state, "answer": answer, "caveats": caveats, "followups": followups,
                "chart": chart, "flags": flags, "usage": usage}
    except LLMError as exc:
        return {**state, "error": str(exc)}
    except Exception as exc:
        log.error("compose.failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"Answer composition failed: {exc}"}


_CAVEAT_MARKER = "---CAVEATS---"
_FOLLOWUP_MARKER = "---FOLLOWUPS---"


class _AnswerScrubber:
    """Stream deltas to the client, holding back the ---CAVEATS--- tail sections."""

    HOLDBACK = len(_CAVEAT_MARKER) + 4

    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self._full = ""
        self._sent = 0
        self._stopped = False

    def on_delta(self, text: str) -> None:
        if self._stopped:
            return
        self._full += text
        marker = self._full.find(_CAVEAT_MARKER)
        if marker != -1:
            visible_end = max(self._sent, len(self._full[:marker].rstrip()))
            self._stopped = True
        else:
            visible_end = max(self._sent, len(self._full) - self.HOLDBACK)
        if visible_end > self._sent:
            emit(self._run_id, {"type": "answer_delta", "text": self._full[self._sent:visible_end]})
            self._sent = visible_end

    def flush(self, final_answer: str) -> None:
        if len(final_answer) > self._sent:
            emit(self._run_id, {"type": "answer_delta", "text": final_answer[self._sent:]})


def _split_answer(text: str) -> tuple[str, list, list]:
    body = text or ""
    caveats: list = []
    followups: list = []
    if _FOLLOWUP_MARKER in body:
        body, tail = body.split(_FOLLOWUP_MARKER, 1)
        followups = [ln.strip("-• \t") for ln in tail.strip().splitlines() if ln.strip("-• \t")][:3]
    if _CAVEAT_MARKER in body:
        body, tail = body.split(_CAVEAT_MARKER, 1)
        caveats = [ln.strip("-• \t") for ln in tail.strip().splitlines() if ln.strip("-• \t")][:4]
    return body.strip(), caveats, followups


def _freshness_line(state: AgentState) -> str | None:
    """Oldest freshness among the datasets this answer used (spec/capabilities/data-freshness.md)."""
    used_ids = (state.get("plan") or {}).get("dataset_ids") or []
    used = [d for d in state.get("datasets", []) if d["id"] in used_ids]
    if not used:
        return None
    stamps = []
    for d in used:
        if d.get("source") == "mssql" and d.get("synced_at"):
            stamps.append((d["synced_at"], f"synced {d['synced_at'][:16].replace('T', ' ')}"))
        elif d.get("created_at"):
            stamps.append((d["created_at"], f"uploaded {d['created_at'][:16].replace('T', ' ')}"))
    if not stamps:
        return None
    oldest = min(stamps, key=lambda x: x[0])
    return f"Data as of: {oldest[1]} (UTC)"


def _persist(state: AgentState, status: str) -> None:
    with create_db_session() as session:
        run = session.get(RunRow, state["run_id"])
        if run is None:
            return
        run.status = status
        run.conversation_id = state.get("conversation_id")
        run.input_text = state.get("question")
        run.output_text = state.get("answer")
        run.error_message = state.get("error")
        run.language = state.get("language")
        run.sql_text = state.get("sql")
        run.steps_json = json.dumps(state.get("steps", []), ensure_ascii=False)
        run.result_json = json.dumps(state.get("result") or {}, ensure_ascii=False, default=str)
        run.caveats_json = json.dumps(state.get("caveats", []), ensure_ascii=False)
        run.followups_json = json.dumps(state.get("followups", []), ensure_ascii=False)
        run.chart_json = json.dumps(state.get("chart"), ensure_ascii=False, default=str)
        run.flags_json = json.dumps(state.get("flags", []), ensure_ascii=False)
        run.freshness = _freshness_line(state)
        run.user_id = state.get("user_id")
        usage = state.get("usage", {})
        run.input_tokens = usage.get("input_tokens", 0)
        run.output_tokens = usage.get("output_tokens", 0)
        conv = session.get(ConversationRow, state.get("conversation_id") or "")
        if conv is not None:
            conv.updated_at = run.updated_at


def finalize(state: AgentState) -> AgentState:
    status = state.get("status") or "completed"
    try:
        _persist(state, status)
    except Exception as exc:
        log.error("finalize.persist_failed", run_id=state.get("run_id"), error=str(exc))
    log.info("run.finished", run_id=state.get("run_id"), status=status,
             tokens=state.get("usage"), steps=len(state.get("steps", [])))
    return {**state, "status": status}


def handle_error(state: AgentState) -> AgentState:
    error = state.get("error")
    if not error:
        attempts = state.get("sql_attempts", [])
        last_err = next((a["error"] for a in reversed(attempts) if a.get("error")), None)
        if last_err:
            error = (
                f"I could not get a working query after {len(attempts)} attempts. "
                f"Last error: {last_err}"
            )
        else:
            error = "Something went wrong."
    state = {**state, "error": error}
    if not state.get("answer"):
        state = {**state, "answer": ""}
    try:
        _persist(state, "failed")
    except Exception as exc:
        log.error("handle_error.persist_failed", run_id=state.get("run_id"), error=str(exc))
    emit(state.get("run_id", ""), {"type": "error", "message": error})
    log.info("run.failed", run_id=state.get("run_id"), error=error)
    return {**state, "status": "failed"}
