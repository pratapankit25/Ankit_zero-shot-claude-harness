"""Graph orchestration with a scripted fake LLM — deterministic, no network.

These verify routing/state/persistence/streaming mechanics. The REAL-LLM
behaviour is covered by tests/integration (the Phase-1 gate).
"""
import json

from sqlalchemy.orm import Session

import db.session as session_module
from db.models import DatasetRow, RunRow
from graph.runner import run_question
from graph import stream as stream_module
from ingest.loader import load_csv


def _register_dataset(name="firs"):
    loaded = load_csv(
        b"district,fir_date\nLucknow,2025-01-01\nLucknow,2025-02-01\nAgra,2025-03-05\n",
        f"{name}.csv",
    )
    with Session(session_module._engine) as s:
        row = DatasetRow(
            name=name,
            original_filename=f"{name}.csv",
            table_name=loaded["table_name"],
            status="ready",
            row_count=loaded["row_count"],
            columns_json=json.dumps(loaded["columns"]),
            profile_json=json.dumps(loaded["profile"]),
        )
        s.add(row)
        s.commit()
        return row.id, loaded["table_name"]


def _plan_reply(ds_id, steps=None):
    return json.dumps({
        "language": "en", "mode": "answer", "approach": "count by district",
        "dataset_ids": [ds_id], "steps": steps or ["count rows"],
    })


def _answer_reply(text="**Lucknow** had the most FIRs: 2."):
    return (
        f"{text}\n---CAVEATS---\n- counted all rows\n---FOLLOWUPS---\n- By month?\n- By station?"
    )


def test_happy_path_completes_and_persists(fake_llm, _isolated_db):
    ds_id, table = _register_dataset()
    fake_llm.reset([
        _plan_reply(ds_id),
        json.dumps({"sql": f'SELECT district, COUNT(*) AS n FROM "{table}" GROUP BY district ORDER BY n DESC'}),
        _answer_reply(),
    ])
    detail = run_question("Which district has the most FIRs?")
    assert detail["status"] == "completed"
    assert "Lucknow" in detail["answer"]
    assert detail["sql"].lower().startswith("select")
    assert detail["result"]["rows"][0][0] == "Lucknow"
    assert detail["caveats"] == ["counted all rows"]
    assert len(detail["followups"]) == 2
    assert detail["usage"]["input_tokens"] > 0
    with Session(_isolated_db) as s:
        run = s.get(RunRow, detail["run_id"])
        assert run.status == "completed"
        assert run.sql_text == detail["sql"]
        assert len(json.loads(run.steps_json)) >= 4


def test_sql_error_retries_then_succeeds(fake_llm, _isolated_db):
    ds_id, table = _register_dataset()
    fake_llm.reset([
        _plan_reply(ds_id),
        json.dumps({"sql": f'SELECT wrong_col FROM "{table}"'}),          # attempt 1 → SQL error
        json.dumps({"sql": f'SELECT COUNT(*) AS n FROM "{table}"'}),      # attempt 2 → ok
        _answer_reply("There are **3** FIRs."),
    ])
    detail = run_question("How many FIRs?")
    assert detail["status"] == "completed"
    attempts = [s for s in detail["steps"] if s["label_en"].lower().startswith(("writing sql", "correcting sql"))]
    assert len(attempts) == 2
    assert detail["result"]["rows"] == [[3]]


def test_exhausted_retries_fail_cleanly(fake_llm, _isolated_db, monkeypatch):
    monkeypatch.setenv("AGENT_MAX_SQL_ITERATIONS", "2")
    ds_id, table = _register_dataset()
    fake_llm.reset([
        _plan_reply(ds_id),
        json.dumps({"sql": f'SELECT nope FROM "{table}"'}),
        json.dumps({"sql": f'SELECT still_nope FROM "{table}"'}),
    ])
    detail = run_question("How many FIRs?")
    assert detail["status"] == "failed"
    assert "attempts" in detail["error"]
    with Session(_isolated_db) as s:
        assert s.get(RunRow, detail["run_id"]).status == "failed"


def test_clarification_turn(fake_llm, _isolated_db):
    _register_dataset()
    fake_llm.reset([
        json.dumps({"language": "en", "mode": "clarify",
                    "clarification": "Which time period do you mean?"}),
    ])
    detail = run_question("show me the data")
    assert detail["status"] == "clarification"
    assert "time period" in detail["answer"]
    assert detail["sql"] is None


def test_empty_library_clarifies_without_llm_sql(fake_llm, _isolated_db):
    fake_llm.reset([
        json.dumps({"language": "en", "mode": "answer", "dataset_ids": [],
                    "approach": "?", "steps": ["?"]}),
    ])
    detail = run_question("How many FIRs?")
    assert detail["status"] == "clarification"
    assert "upload" in detail["answer"].lower()


def test_llm_failure_persists_failed_run(fake_llm, _isolated_db):
    _register_dataset()

    class Boom(fake_llm):
        def generate(self, prompt, *, system=None):
            from llm.client import LLMError
            raise LLMError("Could not reach the LLM API — check your network/proxy.")

    import graph.nodes as nodes_module
    nodes_module.LLMClient = Boom
    detail = run_question("How many FIRs?")
    assert detail["status"] == "failed"
    assert "LLM API" in detail["error"]
    with Session(_isolated_db) as s:
        run = s.get(RunRow, detail["run_id"])
        assert run.status == "failed"
        assert run.error_message


def test_two_turn_history_reaches_prompt(fake_llm, _isolated_db):
    """Stateful capability rule: the 2nd turn must see the 1st (test-driven.md)."""
    ds_id, table = _register_dataset()
    fake_llm.reset([
        _plan_reply(ds_id),
        json.dumps({"sql": f'SELECT COUNT(*) AS n FROM "{table}" WHERE district=\'Lucknow\''}),
        _answer_reply("Lucknow has **2** FIRs."),
    ])
    first = run_question("How many FIRs in Lucknow?")
    assert first["status"] == "completed"

    fake_llm.reset([
        _plan_reply(ds_id, steps=["split by month"]),
        json.dumps({"sql": f"SELECT substr(fir_date,1,7) AS month, COUNT(*) AS n FROM \"{table}\" WHERE district='Lucknow' GROUP BY month"}),
        _answer_reply("January: 1, February: 1."),
    ])
    second = run_question("now split it by month", conversation_id=first["conversation_id"])
    assert second["status"] == "completed"
    assert second["conversation_id"] == first["conversation_id"]
    plan_prompt = fake_llm.calls[0]["prompt"]
    assert "How many FIRs in Lucknow?" in plan_prompt          # history text
    assert "Lucknow has **2** FIRs." in plan_prompt


def test_stream_events_order(fake_llm, _isolated_db):
    ds_id, table = _register_dataset()
    fake_llm.reset([
        _plan_reply(ds_id),
        json.dumps({"sql": f'SELECT COUNT(*) AS n FROM "{table}"'}),
        _answer_reply("There are **3** FIRs."),
    ])
    events = []
    detail = run_question("How many FIRs?", on_event=events.append)
    types = [e["type"] for e in events]
    assert types[0] == "run"
    assert "step" in types and "answer_delta" in types
    assert types[-1] == "final"
    deltas = "".join(e["text"] for e in events if e["type"] == "answer_delta")
    assert deltas == detail["answer"]                            # scrubbed of ---CAVEATS--- tail
    assert "---CAVEATS---" not in deltas
    assert stream_module._emitters == {}                         # emitter unregistered
