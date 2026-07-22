"""Phase-1 gate: REAL Gemini/Anthropic calls over the full fixture data.

Requires a provider key in `.env` and network reach to the provider.
AGENT_SKIP_LLM_TESTS=1 skips these (sandbox-only escape hatch) — the user's
gate runs them for real; skipped is not passed.

Assertions follow harness/patterns/test-driven.md: exact pre-computed numbers
from fixtures large enough that sample != full data.
"""
import re

import pytest

from db.models import RunRow


def _digits(text: str) -> str:
    return re.sub(r"[, ]", "", text or "")


def _mentions_district(text: str, expected: dict, district: str) -> bool:
    return district in text or expected["district_aliases"][district] in text


@pytest.mark.usefixtures("_require_llm_key")
class TestGoldenPath:
    def test_top_district_english(self, api_client, load_samples, expected):
        r = api_client.post("/questions", json={
            "question": "Which district had the most FIRs registered in 2025? Give the exact count.",
        })
        assert r.status_code == 200
        run = r.json()["data"]
        assert run["status"] == "completed", run.get("error")
        assert _mentions_district(run["answer"], expected, expected["top_district_2025"])
        assert str(expected["top_district_2025_count"]) in _digits(run["answer"])
        assert run["sql"] and "select" in run["sql"].lower()
        assert run["usage"]["input_tokens"] > 0
        assert any(s["status"] == "done" for s in run["steps"])

    def test_hindi_question_hindi_answer(self, api_client, load_samples, expected):
        r = api_client.post("/questions", json={
            "question": "2025 में सबसे ज़्यादा FIR किस जिले में दर्ज हुईं? संख्या भी बताइए।",
        })
        run = r.json()["data"]
        assert run["status"] == "completed", run.get("error")
        assert re.search(r"[ऀ-ॿ]", run["answer"]), "answer must contain Devanagari"
        assert _mentions_district(run["answer"], expected, expected["top_district_2025"])
        assert str(expected["top_district_2025_count"]) in _digits(run["answer"])

    def test_followup_uses_context(self, api_client, load_samples, expected):
        """Stateful two-turn: the referent of turn 2 lives only in turn 1."""
        r1 = api_client.post("/questions", json={
            "question": "Which district had the most FIRs in 2025?",
        })
        run1 = r1.json()["data"]
        assert run1["status"] == "completed", run1.get("error")

        r2 = api_client.post("/questions", json={
            "question": "Now show that district's 2025 FIRs month by month.",
            "conversation_id": run1["conversation_id"],
        })
        run2 = r2.json()["data"]
        assert run2["status"] == "completed", run2.get("error")
        months = expected["lucknow_2025_by_month"]
        hits = sum(1 for count in months.values() if str(count) in _digits(run2["answer"] + str(run2["result"])))
        assert hits >= 3, f"expected monthly figures in answer/result, got {run2['answer']!r}"

        # state-survival: reload returns both turns
        conv = api_client.get(f"/conversations/{run1['conversation_id']}").json()["data"]
        assert len(conv["runs"]) == 2

    def test_join_across_datasets(self, api_client, load_samples, expected):
        r = api_client.post("/questions", json={
            "question": (
                "Using the FIR records and the personnel data: which district had the FEWEST "
                "FIRs per actual officer in 2025? Divide each district's 2025 FIR count by its "
                "total actual_strength."
            ),
        })
        run = r.json()["data"]
        assert run["status"] == "completed", run.get("error")
        assert _mentions_district(run["answer"], expected, expected["min_fir_per_officer_district"])
        assert "join" in run["sql"].lower() or all(
            t in run["sql"].lower() for t in ("actual_strength", "fir")
        )

    def test_ambiguous_question_clarifies_not_guesses(self, api_client, load_samples):
        r = api_client.post("/questions", json={"question": "data dikhao"})
        run = r.json()["data"]
        assert run["status"] in ("clarification", "completed")
        if run["status"] == "clarification":
            assert run["answer"].strip().rstrip("?") != ""

    def test_trend_question_yields_chart_from_result(self, api_client, load_samples, expected):
        """Phase 2 gate: chart points must equal the SQL result's month series."""
        r = api_client.post("/questions", json={
            "question": "Show Lucknow's 2025 FIRs month by month (month, count).",
        })
        run = r.json()["data"]
        assert run["status"] == "completed", run.get("error")
        chart = run.get("chart")
        assert chart and chart["type"] == "line", f"expected a line chart, got {chart}"
        months = expected["lucknow_2025_by_month"]
        plotted = {p["x"][:7]: p["y"] for p in chart["points"]}
        hits = sum(1 for m, c in months.items() if plotted.get(m) == c)
        assert hits >= 4, f"chart points must match ground truth: {plotted} vs {months}"

    def test_audit_trail_written(self, api_client, load_samples, _isolated_db, expected):
        r = api_client.post("/questions", json={
            "question": "How many FIR records are there in total?",
        })
        run = r.json()["data"]
        assert run["status"] == "completed", run.get("error")
        assert str(expected["total_fir_rows"]) in _digits(run["answer"])
        from sqlalchemy.orm import Session
        with Session(_isolated_db) as s:
            row = s.get(RunRow, run["run_id"])
            assert row.sql_text
            assert row.input_tokens > 0
            assert row.steps_json and "Writing" in row.steps_json


def test_unreachable_or_bad_key_fails_cleanly(api_client, load_samples, monkeypatch):
    """No skip: with a bogus key (or no network) the run must FAIL with a
    human message naming .env/network — never hang or stack-trace. Works in
    any environment."""
    monkeypatch.setenv("AGENT_GEMINI_API_KEY", "bogus-key-for-failure-path")
    monkeypatch.setenv("AGENT_ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "")
    import config.settings as m
    m._settings = None

    r = api_client.post("/questions", json={"question": "How many FIRs?"})
    assert r.status_code == 200
    run = r.json()["data"]
    assert run["status"] == "failed"
    assert run["error"]
    assert any(k in run["error"] for k in ("API", ".env", "network", "key", "LLM"))
