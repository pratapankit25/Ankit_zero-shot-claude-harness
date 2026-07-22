"""Phase 4: auth/bootstrap/roles, district scoping (incl. SQL-level), costs, PDFs, email."""
import json
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from db.models import ConversationRow, DatasetRow, ReportRow, RunRow, ScheduleRow, DeliveryRow
from reports import email_delivery
from reports.pdf import build_report_pdf, build_run_pdf


# ---------------------------------------------------------------- auth & roles

def test_open_mode_then_bootstrap_then_login_required(api_client):
    # open mode: no users → everything works without a session
    assert api_client.get("/datasets").status_code == 200
    me = api_client.get("/auth/me").json()["data"]
    assert me["auth_required"] is False

    # first admin via bootstrap
    r = api_client.post("/auth/bootstrap", json={"username": "adminsahab", "password": "strongpass1"})
    assert r.status_code == 200
    assert r.json()["data"]["user"]["role"] == "admin"

    # bootstrap is one-shot
    assert api_client.post("/auth/bootstrap", json={"username": "second", "password": "strongpass1"}).status_code == 409

    # cookie from bootstrap keeps the admin logged in
    assert api_client.get("/datasets").status_code == 200

    # a cookie-less client is now locked out of data endpoints but not /health
    api_client.cookies.clear()
    assert api_client.get("/datasets").status_code == 401
    assert api_client.get("/health").status_code == 200

    # login works; wrong password rejected
    assert api_client.post("/auth/login", json={"username": "adminsahab", "password": "wrong"}).status_code == 401
    assert api_client.post("/auth/login", json={"username": "adminsahab", "password": "strongpass1"}).status_code == 200
    assert api_client.get("/datasets").status_code == 200


@pytest.fixture
def admin_client(api_client):
    api_client.post("/auth/bootstrap", json={"username": "admin1", "password": "strongpass1"})
    return api_client


def _login_as(api_client, username, password):
    api_client.cookies.clear()
    r = api_client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return api_client


def test_roles_and_district_scoping(admin_client, _isolated_db):
    c = admin_client
    # admin creates a district-scoped viewer + an analyst
    assert c.post("/admin/users", json={"username": "agra_v", "password": "viewerpass1",
                                        "role": "viewer", "district": "Agra"}).status_code == 200
    assert c.post("/admin/users", json={"username": "hq_a", "password": "analystpass1",
                                        "role": "analyst"}).status_code == 200

    # admin uploads two datasets and tags one to Lucknow
    r = c.post("/datasets", files=[
        ("files", ("agra.csv", b"n\n1\n", "text/csv")),
        ("files", ("lucknow.csv", b"n\n2\n", "text/csv")),
    ])
    ds = {d["name"]: d for d in r.json()["data"]}
    assert c.patch(f"/datasets/{ds['lucknow']['id']}/district", json={"district": "Lucknow"}).status_code == 200
    assert c.patch(f"/datasets/{ds['agra']['id']}/district", json={"district": "Agra"}).status_code == 200

    # viewer sees only their district (+untagged)
    _login_as(c, "agra_v", "viewerpass1")
    names = [d["name"] for d in c.get("/datasets").json()["data"]]
    assert "agra" in names and "lucknow" not in names
    # viewer cannot upload, delete, or manage users/sources/schedules
    assert c.post("/datasets", files=[("files", ("x.csv", b"a\n1\n", "text/csv"))]).status_code == 403
    assert c.delete(f"/datasets/{ds['agra']['id']}").status_code == 403
    assert c.get("/admin/users").status_code == 403
    assert c.get("/schedules").status_code == 403

    # SQL-level block: even hand-crafted SQL naming the other district's table fails
    from ingest.store import QueryError, run_select
    with pytest.raises(QueryError):
        run_select(f"SELECT * FROM \"{ds['lucknow']['table_name']}\"",
                   allowed_tables=[ds["agra"]["table_name"]])
    ok = run_select(f"SELECT * FROM \"{ds['agra']['table_name']}\"",
                    allowed_tables=[ds["agra"]["table_name"]])
    assert ok["row_count"] == 1

    # analyst can upload; cannot manage users
    _login_as(c, "hq_a", "analystpass1")
    assert c.post("/datasets", files=[("files", ("y.csv", b"a\n1\n", "text/csv"))]).status_code == 200
    assert c.get("/admin/users").status_code == 403


def test_viewer_sees_only_own_runs_and_conversations(admin_client, _isolated_db):
    c = admin_client
    c.post("/admin/users", json={"username": "v1", "password": "viewerpass1", "role": "viewer"})
    with Session(_isolated_db) as s:
        admin_id = None  # runs made by others
        conv = ConversationRow(title="admin conv", user_id="someone-else")
        s.add(conv)
        run = RunRow(status="completed", input_text="q", user_id="someone-else", sql_text="SELECT 1")
        s.add(run)
        s.commit()
        other_run = run.id
    _login_as(c, "v1", "viewerpass1")
    assert c.get(f"/runs/{other_run}").status_code == 403
    titles = [x["title"] for x in c.get("/conversations").json()["data"]]
    assert "admin conv" not in titles


def test_costs_dashboard_math(admin_client, _isolated_db, monkeypatch):
    monkeypatch.setenv("AGENT_PRICE_INPUT_PER_M", "100")
    monkeypatch.setenv("AGENT_PRICE_OUTPUT_PER_M", "200")
    import config.settings as m
    m._settings = None
    with Session(_isolated_db) as s:
        conv = ConversationRow(title="costly")
        s.add(conv)
        s.flush()
        s.add(RunRow(status="completed", conversation_id=conv.id,
                     input_tokens=1_000_000, output_tokens=500_000))
        s.commit()
    body = admin_client.get("/admin/costs").json()["data"]
    assert body["today"]["input_tokens"] == 1_000_000
    assert body["today"]["cost_inr"] == 100 + 100  # 1M in @100 + 0.5M out @200
    assert body["top_conversations"][0]["title"] == "costly"
    assert "estimate" in body["note"]


# ---------------------------------------------------------------- PDFs

_RUN = {
    "question": "Which district had the most FIRs in 2025?",
    "answer": "**Lucknow** topped 2025 with **276** FIRs.",
    "result": {"columns": ["district", "firs"], "rows": [["Lucknow", 276], ["Agra", 120]],
               "row_count": 2, "truncated": False},
    "caveats": ["2025 rows only"], "freshness": "Data as of: uploaded 2026-07-22 09:00 (UTC)",
    "sql": "SELECT district, COUNT(*) FROM ds_x GROUP BY 1",
}


def test_run_pdf_bilingual_numbers_preserved():
    with patch("reports.pdf.translate_answer", return_value="**लखनऊ** 2025 में **276** FIR के साथ शीर्ष पर रहा।"):
        data = build_run_pdf(_RUN, lang="both")
    assert data[:5] == b"%PDF-"
    assert len(data) > 5000  # both fonts embedded


def test_run_pdf_falls_back_when_translation_drops_numbers():
    with patch("reports.pdf.translate_answer", return_value=None) as t:
        data = build_run_pdf(_RUN, lang="hi")
    assert t.called
    assert data[:5] == b"%PDF-"


def test_translation_guard_rejects_number_mismatch():
    from reports.pdf import translate_answer

    class FakeLLM:
        def generate(self, prompt):
            class R: text = "लखनऊ में सबसे ज़्यादा एफ़आईआर।"  # numbers dropped
            return R()

    with patch("reports.pdf.LLMClient", return_value=FakeLLM(), create=True), \
         patch("llm.client.LLMClient", return_value=FakeLLM()):
        assert translate_answer("Lucknow topped with 276.", "hi") is None


def test_report_pdf_renders_markdown_tables():
    md = "# Brief\n\n## Q1\nAnswer text.\n\n| a | b |\n| --- | --- |\n| 1 | 2 |"
    data = build_report_pdf("Morning brief", md)
    assert data[:5] == b"%PDF-"


# ---------------------------------------------------------------- email

class FakeSMTP:
    sent: list = []
    fail_times: int = 0

    def __init__(self, *a, **k): ...
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self): ...
    def login(self, *a): ...

    def send_message(self, msg):
        if FakeSMTP.fail_times > 0:
            FakeSMTP.fail_times -= 1
            raise ConnectionError("smtp down")
        FakeSMTP.sent.append(msg)


@pytest.fixture
def smtp_env(monkeypatch):
    monkeypatch.setenv("AGENT_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("AGENT_SMTP_FROM", "analyst@up.test")
    import config.settings as m
    m._settings = None
    FakeSMTP.sent = []
    FakeSMTP.fail_times = 0
    monkeypatch.setattr(email_delivery.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_delivery.time, "sleep", lambda *_: None)


def _report(_isolated_db, recipients):
    with Session(_isolated_db) as s:
        sched = ScheduleRow(name="Brief", questions_json="[]",
                            recipients_json=json.dumps(recipients))
        s.add(sched)
        s.flush()
        rep = ReportRow(schedule_id=sched.id, title="Brief — today", content_md="# Brief\nAll good.")
        s.add(rep)
        s.commit()
        return rep.id


def test_email_sent_with_pdf(smtp_env, _isolated_db):
    rid = _report(_isolated_db, ["sp@example.in"])
    out = email_delivery.deliver_report(rid)
    assert out == [{"recipient": "sp@example.in", "status": "sent", "attempts": 1}]
    msg = FakeSMTP.sent[0]
    assert msg["Subject"] == "Brief — today"
    assert any(p.get_content_type() == "application/pdf" for p in msg.iter_attachments())
    with Session(_isolated_db) as s:
        assert s.query(DeliveryRow).one().status == "sent"


def test_email_retries_then_fails_honestly(smtp_env, _isolated_db):
    FakeSMTP.fail_times = 99
    rid = _report(_isolated_db, ["dgp@example.in"])
    out = email_delivery.deliver_report(rid)
    assert out[0]["status"] == "failed" and out[0]["attempts"] == 3
    with Session(_isolated_db) as s:
        d = s.query(DeliveryRow).one()
        assert d.status == "failed" and "smtp down" in d.error_message


def test_email_noop_without_smtp_or_recipients(_isolated_db):
    rid = _report(_isolated_db, [])
    assert email_delivery.deliver_report(rid) == []
