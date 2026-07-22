"""Phase 3: sync engine (fake adapter), scheduler decisions, summaries, freshness."""
import json
from datetime import datetime
from unittest.mock import patch

from sqlalchemy.orm import Session

from db.models import DatasetRow, ReportRow, ScheduleRow, SyncRunRow, SyncTableRow
from ingest import store
from sources import scheduler, summaries, sync_engine


class FakeAdapter:
    """Yields configured batches; can be told to explode mid-stream."""

    def __init__(self, batches, fail_after=None):
        self.batches = batches
        self.fail_after = fail_after

    def fetch_batches(self, table, incremental_column=None, after_value=None, batch_size=None):
        for i, (cols, rows) in enumerate(self.batches):
            if incremental_column and after_value is not None:
                idx = cols.index(incremental_column)
                rows = [r for r in rows if str(r[idx]) > str(after_value)]
                if not rows:
                    continue
            yield cols, rows
            if self.fail_after is not None and i + 1 >= self.fail_after:
                raise RuntimeError("connection lost mid-sync")


def _cfg(_isolated_db, incremental_column=None) -> str:
    with Session(_isolated_db) as s:
        cfg = SyncTableRow(source_table="dbo.FIR", dataset_name="FIR (MsSQL)",
                           incremental_column=incremental_column)
        s.add(cfg)
        s.commit()
        return cfg.id


BATCH1 = (["id", "district", "fir_date"], [[1, "Lucknow", "2025-01-01"], [2, "Agra", "2025-01-02"]])
BATCH2 = (["id", "district", "fir_date"], [[3, "Meerut", "2025-01-03"]])


def test_full_sync_lands_exact_rows_and_freshness(_isolated_db):
    cfg_id = _cfg(_isolated_db, incremental_column="id")
    out = sync_engine.sync_table(cfg_id, FakeAdapter([BATCH1, BATCH2]))
    assert out == {"status": "completed", "rows": 3, "mode": "full", "error": None}
    with Session(_isolated_db) as s:
        ds = s.query(DatasetRow).filter(DatasetRow.source == "mssql").one()
        assert ds.row_count == 3
        assert ds.synced_at is not None
        cfg = s.get(SyncTableRow, cfg_id)
        assert cfg.last_synced_value == "3"
        result = store.run_select(f'SELECT COUNT(*) FROM "{ds.table_name}"')
        assert result["rows"][0][0] == 3


def test_incremental_sync_appends_only_delta(_isolated_db):
    cfg_id = _cfg(_isolated_db, incremental_column="id")
    sync_engine.sync_table(cfg_id, FakeAdapter([BATCH1, BATCH2]))
    delta = (["id", "district", "fir_date"], [[4, "Varanasi", "2025-01-04"], [5, "Agra", "2025-01-05"]])
    out = sync_engine.sync_table(cfg_id, FakeAdapter([delta]))
    assert out["mode"] == "incremental" and out["rows"] == 2
    with Session(_isolated_db) as s:
        ds = s.query(DatasetRow).filter(DatasetRow.source == "mssql").one()
        assert ds.row_count == 5
        assert s.get(SyncTableRow, cfg_id).last_synced_value == "5"


def test_midsync_failure_keeps_previous_extract(_isolated_db):
    cfg_id = _cfg(_isolated_db)
    sync_engine.sync_table(cfg_id, FakeAdapter([BATCH1, BATCH2]))       # good sync: 3 rows
    out = sync_engine.sync_table(cfg_id, FakeAdapter([BATCH1], fail_after=1))
    assert out["status"] == "failed"
    with Session(_isolated_db) as s:
        ds = s.query(DatasetRow).filter(DatasetRow.source == "mssql").one()
        assert store.run_select(f'SELECT COUNT(*) FROM "{ds.table_name}"')["rows"][0][0] == 3
        assert s.query(SyncRunRow).filter(SyncRunRow.status == "failed").count() == 1


def test_daytime_questions_touch_no_mssql(fake_llm, _isolated_db):
    """Zero MsSQL connections during /questions (spec success criterion)."""
    from graph.runner import run_question
    fake_llm.reset([json.dumps({"language": "en", "mode": "clarify", "clarification": "Upload data first."})])
    with patch("sources.mssql._connect", side_effect=AssertionError("MsSQL touched during a question!")) as spy:
        run_question("How many FIRs?")
    assert spy.call_count == 0


def test_scheduler_due_logic(_isolated_db, monkeypatch):
    monkeypatch.setenv("AGENT_MSSQL_HOST", "db.example")
    monkeypatch.setenv("AGENT_MSSQL_DATABASE", "cctns")
    monkeypatch.setenv("AGENT_MSSQL_USERNAME", "ro_user")
    import config.settings as m
    m._settings = None
    _cfg(_isolated_db)

    calls = []
    monkeypatch.setattr(scheduler.sync_engine if hasattr(scheduler, "sync_engine") else scheduler,
                        "tick", scheduler.tick)  # no-op guard
    with patch("sources.sync_engine.sync_all", side_effect=lambda a, note=None: calls.append(note) or []):
        # 01:00 — before the window: nothing
        scheduler.tick(datetime(2026, 7, 22, 1, 0))
        assert calls == []
        # 02:00 — in the window: on-time run
        scheduler.tick(datetime(2026, 7, 22, 2, 0))
        assert calls == [None]
        # 09:00 same day, already synced (a completed run exists?) — sync_all was mocked,
        # so no completed SyncRunRow exists; a late run fires instead
        scheduler.tick(datetime(2026, 7, 22, 9, 0))
        assert len(calls) == 2 and calls[1] is not None  # late note


def test_summary_report_generated_with_failures_inline(_isolated_db):
    with Session(_isolated_db) as s:
        sched = ScheduleRow(name="Morning brief", questions_json=json.dumps(["Q1", "Q2"]))
        s.add(sched)
        s.commit()
        sched_id = sched.id

    def fake_run_question(question, conversation_id=None, on_event=None, user=None):
        if question == "Q1":
            return {"status": "completed", "answer": "**42** FIRs.", "freshness": "Data as of: uploaded now",
                    "result": {"columns": ["n"], "rows": [[42]], "row_count": 1, "truncated": False}}
        raise RuntimeError("LLM down")

    with patch("graph.runner.run_question", side_effect=fake_run_question):
        report_id = summaries.run_schedule(sched_id, note="test")

    with Session(_isolated_db) as s:
        report = s.get(ReportRow, report_id)
        assert report.status == "partial"
        assert "**42** FIRs." in report.content_md
        assert "Could not answer" in report.content_md
        assert s.get(ScheduleRow, sched_id).last_run_at is not None


def test_freshness_recorded_on_answers(fake_llm, _isolated_db):
    from graph.runner import run_question
    from ingest.loader import load_csv
    loaded = load_csv(b"district,n\nLucknow,1\nAgra,2\n", "d.csv")
    with Session(_isolated_db) as s:
        ds = DatasetRow(name="d", original_filename="d.csv", table_name=loaded["table_name"],
                        status="ready", row_count=2, columns_json=json.dumps(loaded["columns"]))
        s.add(ds)
        s.commit()
        ds_id = ds.id
    fake_llm.reset([
        json.dumps({"language": "en", "mode": "answer", "approach": "count",
                    "dataset_ids": [ds_id], "steps": ["count"]}),
        json.dumps({"sql": f'SELECT COUNT(*) FROM "{loaded["table_name"]}"'}),
        "There are **2** rows.\n---CAVEATS---\n- none\n---FOLLOWUPS---\n- more?",
    ])
    detail = run_question("How many rows?")
    assert detail["status"] == "completed"
    assert detail["freshness"] and detail["freshness"].startswith("Data as of: uploaded")
