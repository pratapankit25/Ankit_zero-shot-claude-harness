"""API contract tests — no LLM, graph patched where needed."""
import json
from unittest.mock import patch

from tests_helpers import read_sample


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


# ---------------------------------------------------------------- datasets

def test_upload_two_csvs(api_client):
    r = api_client.post("/datasets", files=[
        ("files", ("personnel.csv", read_sample("personnel.csv"), "text/csv")),
        ("files", ("a.csv", b"x,y\n1,2\n", "text/csv")),
    ])
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 2
    assert all(d["status"] == "ready" for d in data)
    assert data[0]["row_count"] == 24
    assert data[0]["columns"][0]["name"] == "district"


def test_upload_bad_file_reports_error_but_sibling_loads(api_client):
    r = api_client.post("/datasets", files=[
        ("files", ("book.xlsx", b"PK\x03\x04" + b"\x00" * 50, "application/octet-stream")),
        ("files", ("ok.csv", b"a,b\n1,2\n", "text/csv")),
    ])
    assert r.status_code == 200
    by_name = {d["original_filename"]: d for d in r.json()["data"]}
    assert by_name["book.xlsx"]["status"] == "error"
    assert by_name["book.xlsx"]["error_message"]
    assert by_name["ok.csv"]["status"] == "ready"


def test_upload_no_files_400(api_client):
    r = api_client.post("/datasets", files=[])
    assert r.status_code in (400, 422)


def test_list_and_delete_dataset(api_client):
    r = api_client.post("/datasets", files=[("files", ("d.csv", b"a\n1\n", "text/csv"))])
    ds = r.json()["data"][0]
    assert api_client.get("/datasets").json()["data"][0]["id"] == ds["id"]
    assert api_client.delete(f"/datasets/{ds['id']}").json()["data"]["deleted"] is True
    assert api_client.get("/datasets").json()["data"] == []
    assert api_client.delete(f"/datasets/{ds['id']}").status_code == 404


# ---------------------------------------------------------------- questions

_FAKE_DETAIL = {
    "run_id": "r1", "conversation_id": "c1", "status": "completed",
    "question": "q", "answer": "**42**", "language": "en", "sql": "SELECT 42",
    "steps": [], "result": {"columns": ["n"], "rows": [[42]], "row_count": 1, "truncated": False},
    "caveats": [], "followups": ["next?"], "usage": {"input_tokens": 1, "output_tokens": 2},
    "duration_ms": 5, "error": None, "created_at": None,
}


def test_ask_returns_detail(api_client):
    with patch("api.questions.run_question", return_value=_FAKE_DETAIL) as rq:
        r = api_client.post("/questions", json={"question": "how many?"})
    assert r.status_code == 200
    assert r.json()["data"]["answer"] == "**42**"
    rq.assert_called_once_with("how many?", None)


def test_ask_blank_question_422(api_client):
    assert api_client.post("/questions", json={"question": "   "}).status_code == 422
    assert api_client.post("/questions", json={}).status_code == 422


def test_stream_emits_sse_events(api_client):
    def fake_run(question, conversation_id=None, on_event=None):
        on_event({"type": "run", "run_id": "r1", "conversation_id": "c1"})
        on_event({"type": "step", "label_en": "Writing SQL", "label_hi": "SQL लिख रहा हूँ", "status": "start"})
        on_event({"type": "answer_delta", "text": "**42**"})
        on_event({"type": "final", "run": _FAKE_DETAIL})
        return _FAKE_DETAIL

    with patch("api.questions.run_question", side_effect=fake_run):
        with api_client.stream("POST", "/questions/stream", json={"question": "how many?"}) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            body = "".join(r.iter_text())

    assert "event: run" in body
    assert "event: step" in body and "लिख" in body
    assert "event: answer_delta" in body
    assert "event: final" in body
    final_payload = [ln for ln in body.splitlines() if '"run"' in ln][0]
    assert json.loads(final_payload.split("data: ", 1)[1])["run"]["answer"] == "**42**"


# ---------------------------------------------------------------- conversations & runs

def test_conversation_listing_and_detail(api_client, _isolated_db):
    from sqlalchemy.orm import Session
    from db.models import ConversationRow, RunRow
    with Session(_isolated_db) as s:
        conv = ConversationRow(title="FIR analysis")
        s.add(conv)
        s.flush()
        s.add(RunRow(conversation_id=conv.id, status="completed",
                     input_text="q1", output_text="a1"))
        s.commit()
        conv_id = conv.id

    listing = api_client.get("/conversations").json()["data"]
    assert listing[0]["id"] == conv_id and listing[0]["run_count"] == 1
    detail = api_client.get(f"/conversations/{conv_id}").json()["data"]
    assert detail["title"] == "FIR analysis"
    assert detail["runs"][0]["question"] == "q1"
    assert api_client.get("/conversations/nope").status_code == 404


def test_get_run_detail_and_404(api_client, _isolated_db):
    from sqlalchemy.orm import Session
    from db.models import RunRow
    with Session(_isolated_db) as s:
        run = RunRow(status="completed", input_text="q", output_text="a",
                     sql_text="SELECT 1", steps_json="[]",
                     input_tokens=5, output_tokens=7)
        s.add(run)
        s.commit()
        run_id = run.id
    body = api_client.get(f"/runs/{run_id}").json()["data"]
    assert body["sql"] == "SELECT 1"
    assert body["usage"] == {"input_tokens": 5, "output_tokens": 7}
    assert api_client.get("/runs/nonexistent").status_code == 404
