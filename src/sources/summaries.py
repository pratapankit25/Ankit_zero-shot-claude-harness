"""Scheduled summaries: run each configured question through the normal agent,
assemble a markdown report. One failing question never sinks the report.
(spec/capabilities/scheduled-summaries.md)"""
import json
from datetime import datetime, timezone

from db.models import ReportRow, ScheduleRow
from db.session import create_db_session
from observability.events import get_logger

log = get_logger("summaries")


def _result_table_md(result: dict | None, cap: int = 10) -> str:
    if not result or not result.get("rows"):
        return ""
    cols = result["columns"]
    rows = result["rows"][:cap]
    head = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = "\n".join("| " + " | ".join("" if v is None else str(v) for v in r) + " |" for r in rows)
    more = f"\n_…{result['row_count'] - cap} more rows in the app._" if result["row_count"] > cap else ""
    return f"\n{head}\n{sep}\n{body}{more}\n"


def run_schedule(schedule_id: str, note: str | None = None) -> str:
    """Executes the schedule now; returns the report id."""
    from graph.runner import run_question

    with create_db_session() as s:
        sched = s.get(ScheduleRow, schedule_id)
        if sched is None:
            raise ValueError(f"schedule {schedule_id} not found")
        name = sched.name
        questions = json.loads(sched.questions_json or "[]")
        language = sched.language

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [f"# {name}", f"_Generated {stamp}{' — ' + note if note else ''}_", ""]
    failures = 0
    for q in questions:
        question = q if language == "en" else q  # questions are asked verbatim; language guides the agent's answer
        try:
            detail = run_question(question)
            if detail["status"] == "completed":
                parts.append(f"## {question}")
                if detail.get("freshness"):
                    parts.append(f"_{detail['freshness']}_")
                parts.append(detail.get("answer") or "")
                parts.append(_result_table_md(detail.get("result")))
            else:
                failures += 1
                parts.append(f"## {question}")
                parts.append(f"> Could not answer: {detail.get('error') or detail['status']}")
        except Exception as exc:
            failures += 1
            parts.append(f"## {question}")
            parts.append(f"> Could not answer: {exc}")
        parts.append("")

    status = "completed" if failures == 0 else ("partial" if failures < len(questions) else "failed")
    with create_db_session() as s:
        report = ReportRow(
            schedule_id=schedule_id,
            title=f"{name} — {datetime.now(timezone.utc).strftime('%d %b %Y')}",
            content_md="\n".join(parts).strip(),
            status=status,
            note=note,
        )
        s.add(report)
        s.flush()
        report_id = report.id
        sched = s.get(ScheduleRow, schedule_id)
        sched.last_run_at = datetime.now(timezone.utc)
    log.info("summary.generated", schedule=name, status=status, failures=failures)

    try:  # phase 4: email delivery (no-op when SMTP/recipients unset)
        from reports.email_delivery import deliver_report
        deliver_report(report_id)
    except Exception as exc:
        log.error("summary.delivery_error", error=str(exc))
    return report_id
