"""run_question — the single entry point for answering. Creates the conversation/run
rows, wires the per-run emitter, invokes the graph, returns a RunDetail-shaped dict."""
import json
import time
from collections.abc import Callable

from db.models import ConversationRow, RunRow
from db.session import create_db_session, init_db
from graph.agent import agentic_ai
from graph.state import AgentState
from graph.stream import register, unregister, emit


def _ensure_conversation(question: str, conversation_id: str | None, user_id: str | None) -> str:
    with create_db_session() as session:
        if conversation_id:
            conv = session.get(ConversationRow, conversation_id)
            if conv is not None:
                return conv.id
        title = question.strip()[:80] or "New conversation"
        conv = ConversationRow(title=title, user_id=user_id)
        session.add(conv)
        session.flush()
        return conv.id


def run_detail_from_row(run: RunRow) -> dict:
    return {
        "run_id": run.id,
        "conversation_id": run.conversation_id,
        "status": run.status,
        "question": run.input_text,
        "answer": run.output_text,
        "language": run.language,
        "sql": run.sql_text,
        "steps": json.loads(run.steps_json or "[]"),
        "result": json.loads(run.result_json or "null"),
        "caveats": json.loads(run.caveats_json or "[]"),
        "followups": json.loads(run.followups_json or "[]"),
        "chart": json.loads(run.chart_json or "null"),
        "flags": json.loads(run.flags_json or "[]"),
        "usage": {"input_tokens": run.input_tokens or 0, "output_tokens": run.output_tokens or 0},
        "duration_ms": run.duration_ms,
        "error": run.error_message,
        "freshness": run.freshness,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def run_question(
    question: str,
    conversation_id: str | None = None,
    on_event: Callable[[dict], None] | None = None,
    user: dict | None = None,
) -> dict:
    init_db()
    user_id = (user or {}).get("id")
    conv_id = _ensure_conversation(question, conversation_id, user_id)

    with create_db_session() as session:
        run = RunRow(status="pending", input_text=question, conversation_id=conv_id, user_id=user_id)
        session.add(run)
        session.flush()
        run_id = run.id

    if on_event is not None:
        register(run_id, on_event)
    emit(run_id, {"type": "run", "run_id": run_id, "conversation_id": conv_id})

    started = time.monotonic()
    try:
        initial: AgentState = {
            "run_id": run_id,
            "conversation_id": conv_id,
            "question": question,
            "error": None,
        }
        if user_id:
            initial["user_id"] = user_id
        if user and user.get("role") == "viewer" and user.get("district"):
            initial["user_district"] = user["district"]
        agentic_ai.invoke(initial)
    finally:
        duration_ms = round((time.monotonic() - started) * 1000)
        with create_db_session() as session:
            row = session.get(RunRow, run_id)
            if row is not None:
                row.duration_ms = duration_ms
                if row.status == "pending":  # graph died before persisting
                    row.status = "failed"
                    row.error_message = row.error_message or "The run ended unexpectedly."
                detail = run_detail_from_row(row)
        emit(run_id, {"type": "final", "run": detail})
        if on_event is not None:
            unregister(run_id)

    return detail

