from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api._common import api_error, ok
from db.models import RunRow
from db.session import get_session
from graph.runner import run_detail_from_row

router = APIRouter()


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    """Audit detail for one question run (spec/capabilities/audit-trail.md)."""
    run = session.get(RunRow, run_id)
    if run is None:
        raise api_error("NOT_FOUND", f"Run {run_id} not found", 404)
    return ok(run_detail_from_row(run))
