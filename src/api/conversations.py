from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from api._common import api_error, ok
from db.models import ConversationRow, RunRow
from db.session import get_session
from graph.runner import run_detail_from_row

router = APIRouter()


@router.get("/conversations")
def list_conversations(session: Session = Depends(get_session)) -> dict:
    counts = dict(
        session.query(RunRow.conversation_id, func.count(RunRow.id))
        .group_by(RunRow.conversation_id)
        .all()
    )
    rows = session.query(ConversationRow).order_by(ConversationRow.updated_at.desc()).limit(100).all()
    return ok([
        {
            "id": r.id,
            "title": r.title,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "run_count": counts.get(r.id, 0),
        }
        for r in rows
    ])


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, session: Session = Depends(get_session)) -> dict:
    conv = session.get(ConversationRow, conversation_id)
    if conv is None:
        raise api_error("NOT_FOUND", f"Conversation {conversation_id} not found", 404)
    runs = (
        session.query(RunRow)
        .filter(RunRow.conversation_id == conversation_id)
        .order_by(RunRow.created_at.asc())
        .all()
    )
    return ok({
        "id": conv.id,
        "title": conv.title,
        "runs": [run_detail_from_row(r) for r in runs],
    })
