import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from api._common import api_error, ok
from db.models import RunRow
from db.session import get_session
from graph.runner import run_detail_from_row
from ingest import store
from observability.events import get_logger

router = APIRouter()
log = get_logger("api.runs")

EXPORT_ROW_CAP = 500_000
EXPORT_TIMEOUT_S = 60.0


def _guarded_run(run_id: str, request, session: Session) -> RunRow:
    from api.auth import require_role, require_user, users_exist_cached
    run = session.get(RunRow, run_id)
    if run is None:
        raise api_error("NOT_FOUND", f"Run {run_id} not found", 404)
    if users_exist_cached():
        user = require_user(request)
        if user is None:
            raise api_error("AUTH_REQUIRED", "Login required.", 401)
        if user["role"] == "viewer" and run.user_id != user["id"]:
            raise api_error("FORBIDDEN", "You can only access your own runs.", 403)
    return run


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request, session: Session = Depends(get_session)) -> dict:
    """Audit detail for one question run (spec/capabilities/audit-trail.md)."""
    return ok(run_detail_from_row(_guarded_run(run_id, request, session)))


@router.get("/runs/{run_id}/pdf")
def run_pdf(run_id: str, request: Request, lang: str = "both",
            session: Session = Depends(get_session)) -> Response:
    """Bilingual briefing PDF of one answer (spec/capabilities/bilingual-reports.md)."""
    if lang not in ("en", "hi", "both"):
        raise api_error("BAD_LANG", "lang must be en, hi or both", 400)
    run = _guarded_run(run_id, request, session)
    if run.status != "completed":
        raise api_error("NOT_READY", "Only completed answers can become a report.", 409)
    from reports.pdf import build_run_pdf
    data = build_run_pdf(run_detail_from_row(run), lang=lang)
    return Response(
        content=data, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="answer-{run_id[:8]}.pdf"'},
    )


@router.get("/runs/{run_id}/export")
def export_run(run_id: str, request: Request, format: str = "xlsx",
               session: Session = Depends(get_session)) -> Response:
    """Full-result export — re-runs the audited SQL verbatim (spec/capabilities/export-results.md)."""
    if format not in ("xlsx", "csv"):
        raise api_error("BAD_FORMAT", "format must be xlsx or csv", 400)
    run = _guarded_run(run_id, request, session)
    if not run.sql_text or run.status != "completed":
        raise api_error("NOT_EXPORTABLE", "This run has no executed query to export.", 409)

    try:
        result = store.run_select(run.sql_text, timeout_s=EXPORT_TIMEOUT_S, row_cap=EXPORT_ROW_CAP)
    except store.QueryError as exc:
        raise api_error(
            "EXPORT_FAILED",
            f"Could not re-run the audited query — the underlying dataset may have been deleted. ({exc})",
            409,
        )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    short = run_id[:8]
    log.info("run.exported", run_id=run_id, format=format, rows=result["row_count"])

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(result["columns"])
        writer.writerows(result["rows"])
        return Response(
            content=buf.getvalue().encode("utf-8-sig"),  # BOM so Excel opens Devanagari correctly
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="analyst-export-{short}.csv"'},
        )

    import pandas as pd

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame(result["rows"], columns=result["columns"]).to_excel(
            writer, sheet_name="Data", index=False
        )
        pd.DataFrame(
            {
                "Field": ["Question", "SQL", "Rows exported", "Truncated at cap", "Run id", "Exported at"],
                "Value": [
                    run.input_text or "",
                    run.sql_text,
                    result["row_count"],
                    "yes" if result["truncated"] else "no",
                    run_id,
                    stamp,
                ],
            }
        ).to_excel(writer, sheet_name="About", index=False)
    return Response(
        content=out.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="analyst-export-{short}.xlsx"'},
    )
