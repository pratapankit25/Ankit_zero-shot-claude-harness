import json
import threading

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from api._common import api_error, ok
from api.auth import require_role
from db.models import DeliveryRow, ReportRow, ScheduleRow
from db.session import get_session
from observability.events import get_logger
from sources import summaries

router = APIRouter()
log = get_logger("api.schedules")


class ScheduleCreate(BaseModel):
    name: str
    cadence: str = "daily"                 # daily | weekly
    hour: int = 7
    weekday: int | None = None             # 0=Mon (weekly)
    questions: list[str]
    language: str = "en"
    recipients: list[str] = []

    @field_validator("questions")
    @classmethod
    def _q(cls, v: list[str]) -> list[str]:
        v = [q.strip() for q in v if q.strip()]
        if not v:
            raise ValueError("at least one question is required")
        return v[:10]


class SchedulePatch(BaseModel):
    enabled: bool | None = None
    hour: int | None = None
    recipients: list[str] | None = None


def _out(r: ScheduleRow) -> dict:
    return {
        "id": r.id, "name": r.name, "cadence": r.cadence, "hour": r.hour,
        "weekday": r.weekday, "questions": json.loads(r.questions_json or "[]"),
        "language": r.language, "recipients": json.loads(r.recipients_json or "[]"),
        "enabled": bool(r.enabled),
        "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
    }


@router.get("/schedules")
def list_schedules(request: Request, session: Session = Depends(get_session)) -> dict:
    require_role(request, "admin", "analyst")
    return ok([_out(r) for r in session.query(ScheduleRow).order_by(ScheduleRow.created_at.asc()).all()])


@router.post("/schedules")
def create_schedule(req: ScheduleCreate, request: Request, session: Session = Depends(get_session)) -> dict:
    require_role(request, "admin")
    if req.cadence not in ("daily", "weekly"):
        raise api_error("BAD_CADENCE", "cadence must be daily or weekly", 400)
    if not 0 <= req.hour <= 23:
        raise api_error("BAD_HOUR", "hour must be 0-23", 400)
    row = ScheduleRow(
        name=req.name.strip()[:80] or "Brief",
        cadence=req.cadence,
        hour=req.hour,
        weekday=req.weekday,
        questions_json=json.dumps(req.questions, ensure_ascii=False),
        language=req.language if req.language in ("en", "hi") else "en",
        recipients_json=json.dumps(req.recipients, ensure_ascii=False),
    )
    session.add(row)
    session.flush()
    return ok(_out(row))


@router.patch("/schedules/{schedule_id}")
def patch_schedule(schedule_id: str, req: SchedulePatch, request: Request,
                   session: Session = Depends(get_session)) -> dict:
    require_role(request, "admin")
    row = session.get(ScheduleRow, schedule_id)
    if row is None:
        raise api_error("NOT_FOUND", "Schedule not found", 404)
    if req.enabled is not None:
        row.enabled = 1 if req.enabled else 0
    if req.hour is not None and 0 <= req.hour <= 23:
        row.hour = req.hour
    if req.recipients is not None:
        row.recipients_json = json.dumps(req.recipients, ensure_ascii=False)
    return ok(_out(row))


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: str, request: Request, session: Session = Depends(get_session)) -> dict:
    require_role(request, "admin")
    row = session.get(ScheduleRow, schedule_id)
    if row is None:
        raise api_error("NOT_FOUND", "Schedule not found", 404)
    session.delete(row)
    return ok({"deleted": True})


@router.post("/schedules/{schedule_id}/run")
def run_now(schedule_id: str, request: Request, session: Session = Depends(get_session)) -> dict:
    require_role(request, "admin")
    if session.get(ScheduleRow, schedule_id) is None:
        raise api_error("NOT_FOUND", "Schedule not found", 404)

    def work() -> None:
        try:
            summaries.run_schedule(schedule_id, note="manual run")
        except Exception as exc:
            log.error("schedule.manual_failed", schedule=schedule_id, error=str(exc))

    threading.Thread(target=work, daemon=True).start()
    return ok({"started": True})


@router.get("/reports")
def list_reports(request: Request, session: Session = Depends(get_session)) -> dict:
    require_role(request, "admin", "analyst")
    rows = session.query(ReportRow).order_by(ReportRow.created_at.desc()).limit(50).all()
    return ok([{
        "id": r.id, "title": r.title, "status": r.status, "note": r.note,
        "schedule_id": r.schedule_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows])


@router.get("/reports/{report_id}")
def get_report(report_id: str, request: Request, session: Session = Depends(get_session)) -> dict:
    require_role(request, "admin", "analyst")
    r = session.get(ReportRow, report_id)
    if r is None:
        raise api_error("NOT_FOUND", "Report not found", 404)
    deliveries = session.query(DeliveryRow).filter(DeliveryRow.report_id == report_id).all()
    return ok({
        "id": r.id, "title": r.title, "status": r.status, "note": r.note,
        "content_md": r.content_md,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "deliveries": [{"recipient": d.recipient, "status": d.status,
                        "attempts": d.attempts, "error": d.error_message} for d in deliveries],
    })


@router.get("/reports/{report_id}/pdf")
def report_pdf(report_id: str, request: Request, session: Session = Depends(get_session)) -> Response:
    require_role(request, "admin", "analyst")
    r = session.get(ReportRow, report_id)
    if r is None:
        raise api_error("NOT_FOUND", "Report not found", 404)
    from reports.pdf import build_report_pdf
    data = build_report_pdf(r.title, r.content_md)
    return Response(
        content=data, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="brief-{report_id[:8]}.pdf"'},
    )
