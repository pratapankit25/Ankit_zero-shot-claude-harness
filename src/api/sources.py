import threading

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api._common import api_error, ok
from api.auth import require_role
from config.settings import get_settings
from db.models import DatasetRow, SyncRunRow, SyncTableRow
from db.session import get_session
from observability.events import get_logger
from sources import mssql, sync_engine

router = APIRouter()
log = get_logger("api.sources")
_sync_running = threading.Event()


class TableConfig(BaseModel):
    source_table: str
    dataset_name: str
    incremental_column: str | None = None


class TablesPut(BaseModel):
    tables: list[TableConfig]


@router.get("/sources")
def get_sources(request: Request, session: Session = Depends(get_session)) -> dict:
    require_role(request, "admin", "analyst")
    s = get_settings()
    tables = []
    for cfg in session.query(SyncTableRow).order_by(SyncTableRow.created_at.asc()).all():
        ds = session.get(DatasetRow, cfg.dataset_id) if cfg.dataset_id else None
        last = (
            session.query(SyncRunRow)
            .filter(SyncRunRow.source_table == cfg.source_table)
            .order_by(SyncRunRow.started_at.desc())
            .first()
        )
        tables.append({
            "id": cfg.id,
            "source_table": cfg.source_table,
            "dataset_name": cfg.dataset_name,
            "incremental_column": cfg.incremental_column,
            "enabled": bool(cfg.enabled),
            "dataset_id": cfg.dataset_id,
            "synced_at": ds.synced_at.isoformat() if ds is not None and ds.synced_at else None,
            "row_count": ds.row_count if ds is not None else None,
            "last_run": {
                "status": last.status, "rows": last.rows, "note": last.note,
                "error": last.error_message,
                "started_at": last.started_at.isoformat() if last.started_at else None,
            } if last else None,
        })
    runs = session.query(SyncRunRow).order_by(SyncRunRow.started_at.desc()).limit(20).all()
    return ok({
        "configured": mssql.is_configured(),
        "host": (s.mssql_host[:3] + "…" if s.mssql_host else None),
        "database": s.mssql_database or None,
        "sync_hour": s.sync_hour,
        "sync_running": _sync_running.is_set(),
        "tables": tables,
        "recent_runs": [{
            "source_table": r.source_table, "status": r.status, "rows": r.rows,
            "mode": r.mode, "note": r.note, "error": r.error_message,
            "started_at": r.started_at.isoformat() if r.started_at else None,
        } for r in runs],
    })


@router.post("/sources/test")
def test_connection(request: Request) -> dict:
    require_role(request, "admin")
    if not mssql.is_configured():
        raise api_error("NOT_CONFIGURED", "Set AGENT_MSSQL_HOST/DATABASE/USERNAME/PASSWORD in .env first.", 409)
    try:
        tables = mssql.MssqlAdapter().list_tables()[:200]
    except mssql.MssqlError as exc:
        raise api_error("CONNECT_FAILED", str(exc), 502)
    return ok({"tables": tables})


@router.put("/sources/tables")
def put_tables(req: TablesPut, request: Request, session: Session = Depends(get_session)) -> dict:
    require_role(request, "admin")
    keep = {t.source_table for t in req.tables}
    for row in session.query(SyncTableRow).all():
        if row.source_table not in keep:
            session.delete(row)  # config removed; the synced dataset stays in the library
    for t in req.tables:
        row = session.query(SyncTableRow).filter(SyncTableRow.source_table == t.source_table).first()
        if row is None:
            session.add(SyncTableRow(
                source_table=t.source_table,
                dataset_name=t.dataset_name.strip()[:80] or t.source_table,
                incremental_column=t.incremental_column,
            ))
        else:
            row.dataset_name = t.dataset_name.strip()[:80] or t.source_table
            row.incremental_column = t.incremental_column
            row.enabled = 1
    session.flush()
    return ok({"tables": len(req.tables)})


@router.post("/sources/sync")
def sync_now(request: Request) -> dict:
    require_role(request, "admin")
    if not mssql.is_configured():
        raise api_error("NOT_CONFIGURED", "MsSQL is not configured in .env.", 409)
    if _sync_running.is_set():
        raise api_error("BUSY", "A sync is already running.", 409)

    def work() -> None:
        _sync_running.set()
        try:
            sync_engine.sync_all(mssql.MssqlAdapter(), note="manual sync")
        except Exception as exc:
            log.error("sync.manual_crashed", error=str(exc))
        finally:
            _sync_running.clear()

    threading.Thread(target=work, daemon=True).start()
    return ok({"started": True})
