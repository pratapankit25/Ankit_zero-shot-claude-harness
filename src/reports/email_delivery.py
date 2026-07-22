"""Email a generated report (PDF attached) to its schedule's recipients.
3 attempts with backoff; every attempt logged. No-op when SMTP or recipients
are unconfigured. (spec/capabilities/email-delivery.md)"""
import json
import smtplib
import time
from email.message import EmailMessage

from config.settings import get_settings
from db.models import DeliveryRow, ReportRow, ScheduleRow
from db.session import create_db_session
from observability.events import get_logger
from reports.pdf import build_report_pdf

log = get_logger("email")
MAX_ATTACH = 10 * 1024 * 1024


def _send(recipient: str, subject: str, body: str, pdf_bytes: bytes | None) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_from or s.smtp_username
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)
    if pdf_bytes is not None:
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename="brief.pdf")
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
        if s.smtp_tls:
            smtp.starttls()
        if s.smtp_username:
            smtp.login(s.smtp_username, s.smtp_password)
        smtp.send_message(msg)


def deliver_report(report_id: str) -> list[dict]:
    s = get_settings()
    if not s.smtp_host:
        return []
    with create_db_session() as db:
        report = db.get(ReportRow, report_id)
        if report is None:
            return []
        sched = db.get(ScheduleRow, report.schedule_id) if report.schedule_id else None
        recipients = json.loads(sched.recipients_json or "[]") if sched else []
        title, content = report.title, report.content_md
    if not recipients:
        return []

    try:
        pdf_bytes = build_report_pdf(title, content)
        if len(pdf_bytes) > MAX_ATTACH:
            pdf_bytes = None
    except Exception as exc:
        log.error("email.pdf_failed", error=str(exc))
        pdf_bytes = None

    body = "Attached: the latest brief from UP Police Data Analyst." if pdf_bytes else content[:5000]
    outcomes = []
    for recipient in recipients:
        attempts, error = 0, None
        for attempts in range(1, 4):
            try:
                _send(recipient, title, body, pdf_bytes)
                error = None
                break
            except Exception as exc:
                error = str(exc)[:300]
                time.sleep([0, 2, 6][attempts - 1] if attempts <= 3 else 6)
        status = "sent" if error is None else "failed"
        with create_db_session() as db:
            db.add(DeliveryRow(report_id=report_id, recipient=recipient,
                               status=status, attempts=attempts, error_message=error))
        log.info("email.delivery", recipient=recipient, status=status, attempts=attempts)
        outcomes.append({"recipient": recipient, "status": status, "attempts": attempts})
    return outcomes
