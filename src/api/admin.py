from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from api._common import api_error, ok
from api.auth import invalidate_users_cache, require_role
from auth import core
from config.settings import get_settings
from db.models import ConversationRow, DatasetRow, RunRow, UserRow
from db.session import get_session

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"          # admin | analyst | viewer
    district: str | None = None


class PasswordReset(BaseModel):
    password: str


class DistrictPatch(BaseModel):
    district: str | None = None


@router.get("/admin/users")
def list_users(request: Request, session: Session = Depends(get_session)) -> dict:
    require_role(request, "admin")
    rows = session.query(UserRow).order_by(UserRow.created_at.asc()).all()
    return ok([{"id": r.id, "username": r.username, "role": r.role, "district": r.district} for r in rows])


@router.post("/admin/users")
def create_user(req: UserCreate, request: Request, session: Session = Depends(get_session)) -> dict:
    require_role(request, "admin")
    if req.role not in ("admin", "analyst", "viewer"):
        raise api_error("BAD_ROLE", "role must be admin, analyst or viewer", 400)
    if len(req.password) < 8:
        raise api_error("WEAK_PASSWORD", "password must be at least 8 characters", 400)
    if session.query(UserRow).filter(UserRow.username == req.username.strip().lower()).first():
        raise api_error("EXISTS", "That username is taken.", 409)
    user = core.create_user(req.username, req.password, req.role, req.district)
    invalidate_users_cache()
    return ok(user)


@router.delete("/admin/users/{user_id}")
def delete_user(user_id: str, request: Request, session: Session = Depends(get_session)) -> dict:
    me = require_role(request, "admin")
    if me and me["id"] == user_id:
        raise api_error("SELF_DELETE", "You cannot delete your own account.", 400)
    row = session.get(UserRow, user_id)
    if row is None:
        raise api_error("NOT_FOUND", "User not found", 404)
    session.delete(row)
    invalidate_users_cache()
    return ok({"deleted": True})


@router.post("/admin/users/{user_id}/password")
def reset_password(user_id: str, req: PasswordReset, request: Request,
                   session: Session = Depends(get_session)) -> dict:
    require_role(request, "admin")
    if len(req.password) < 8:
        raise api_error("WEAK_PASSWORD", "password must be at least 8 characters", 400)
    row = session.get(UserRow, user_id)
    if row is None:
        raise api_error("NOT_FOUND", "User not found", 404)
    row.password_hash = core.hash_password(req.password)
    return ok({"reset": True})


@router.patch("/datasets/{dataset_id}/district")
def set_dataset_district(dataset_id: str, req: DistrictPatch, request: Request,
                         session: Session = Depends(get_session)) -> dict:
    require_role(request, "admin", "analyst")
    row = session.get(DatasetRow, dataset_id)
    if row is None:
        raise api_error("NOT_FOUND", "Dataset not found", 404)
    row.district = (req.district or "").strip() or None
    return ok({"id": row.id, "district": row.district})


@router.get("/admin/costs")
def costs(request: Request, session: Session = Depends(get_session)) -> dict:
    """Daily token totals + ₹ estimates from the audit trail
    (spec/capabilities/cost-dashboard.md). Admin only."""
    require_role(request, "admin")
    s = get_settings()
    since = datetime.now(timezone.utc) - timedelta(days=14)
    rows = (
        session.query(
            func.date(RunRow.created_at),
            func.coalesce(func.sum(RunRow.input_tokens), 0),
            func.coalesce(func.sum(RunRow.output_tokens), 0),
            func.count(RunRow.id),
        )
        .filter(RunRow.created_at >= since)
        .group_by(func.date(RunRow.created_at))
        .order_by(func.date(RunRow.created_at))
        .all()
    )

    def cost(inp: int, out: int) -> float:
        return round(inp / 1e6 * s.price_input_per_m + out / 1e6 * s.price_output_per_m, 2)

    days = [{"date": str(d), "input_tokens": int(i), "output_tokens": int(o),
             "runs": int(n), "cost_inr": cost(int(i), int(o))} for d, i, o, n in rows]
    today = str(datetime.now(timezone.utc).date())
    today_row = next((d for d in days if d["date"] == today),
                     {"date": today, "input_tokens": 0, "output_tokens": 0, "runs": 0, "cost_inr": 0.0})

    top = (
        session.query(ConversationRow.title,
                      func.coalesce(func.sum(RunRow.input_tokens + RunRow.output_tokens), 0).label("tokens"))
        .join(RunRow, RunRow.conversation_id == ConversationRow.id)
        .group_by(ConversationRow.id)
        .order_by(func.sum(RunRow.input_tokens + RunRow.output_tokens).desc())
        .limit(5)
        .all()
    )
    return ok({
        "note": "Costs are estimates from AGENT_PRICE_*_PER_M in .env; tokens are provider-reported.",
        "today": today_row,
        "days": days,
        "top_conversations": [{"title": t, "tokens": int(tk or 0)} for t, tk in top],
    })
