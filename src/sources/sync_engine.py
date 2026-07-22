"""Sync a configured MsSQL table into the analytics store.

Full mode: load into a staging table, then swap atomically — a failed sync
never leaves a half-updated dataset. Incremental mode: append only the delta
past last_synced_value. (spec/capabilities/mssql-nightly-sync.md)
"""
import json
import re
from datetime import datetime, timezone
from numbers import Number
from uuid import uuid4

import pandas as pd

from db.models import DatasetRow, SyncRunRow, SyncTableRow
from db.session import create_db_session
from ingest import store
from ingest.profiler import profile_frame
from observability.events import get_logger

log = get_logger("sync")


def _sql_type(v) -> str:
    if isinstance(v, bool):
        return "INTEGER"
    if isinstance(v, int):
        return "INTEGER"
    if isinstance(v, Number):
        return "REAL"
    return "TEXT"


def _sanitize(name: str) -> str:
    base = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip().lower()).strip("_") or "col"
    return f"c_{base}" if base[0].isdigit() else base


def _create_table(conn, table: str, columns: list[str], sample_row: list) -> list[str]:
    cols = [_sanitize(c) for c in columns]
    seen: dict[str, int] = {}
    final = []
    for c in cols:
        n = seen.get(c, 0)
        seen[c] = n + 1
        final.append(c if n == 0 else f"{c}_{n + 1}")
    defs = ", ".join(
        f'"{c}" {_sql_type(sample_row[i]) if i < len(sample_row) else "TEXT"}'
        for i, c in enumerate(final)
    )
    conn.execute(f'CREATE TABLE "{table}" ({defs})')
    return final


def _profile_table(table: str) -> tuple[list, dict, int]:
    conn = store.write_conn()
    try:
        row_count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        df = pd.read_sql_query(f'SELECT * FROM "{table}" LIMIT 100000', conn)
    finally:
        conn.close()
    columns, profile = profile_frame(df, {c: c for c in df.columns}, [])
    return columns, profile, int(row_count)


def sync_table(cfg_id: str, adapter, note: str | None = None) -> dict:
    """Returns {status, rows, mode, error}. Never raises for sync failures —
    everything lands in sync_runs and the return value."""
    with create_db_session() as s:
        cfg = s.get(SyncTableRow, cfg_id)
        if cfg is None or not cfg.enabled:
            return {"status": "skipped", "rows": 0, "mode": None, "error": None}
        source_table, dataset_name = cfg.source_table, cfg.dataset_name
        incremental_column = cfg.incremental_column
        last_value = cfg.last_synced_value
        existing_dataset_id = cfg.dataset_id

    incremental = bool(incremental_column and last_value is not None and existing_dataset_id)
    mode = "incremental" if incremental else "full"

    with create_db_session() as s:
        run = SyncRunRow(source_table=source_table, status="running", mode=mode, note=note)
        s.add(run)
        s.flush()
        run_id = run.id

    staging = f"ds_{uuid4().hex[:12]}"
    total = 0
    max_value = last_value
    conn = store.write_conn()
    created_cols: list[str] | None = None
    try:
        target = None
        if incremental:
            with create_db_session() as s:
                ds = s.get(DatasetRow, existing_dataset_id)
                target = ds.table_name if ds is not None else None
            if target is None:
                incremental, mode = False, "full"

        for columns, rows in adapter.fetch_batches(
            source_table,
            incremental_column=incremental_column,
            after_value=last_value if incremental else None,
        ):
            if created_cols is None and not incremental:
                created_cols = _create_table(conn, staging, columns, rows[0])
            write_table = target if incremental else staging
            ncols = len(columns)
            placeholders = ",".join("?" * ncols)
            conn.executemany(f'INSERT INTO "{write_table}" VALUES ({placeholders})', rows)
            total += len(rows)
            if incremental_column and incremental_column in columns:
                idx = columns.index(incremental_column)
                for r in rows:
                    v = r[idx]
                    if v is not None and (max_value is None or str(v) > str(max_value)):
                        max_value = str(v)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        try:
            store.drop_table(staging)
        except Exception:
            pass
        with create_db_session() as s:
            run = s.get(SyncRunRow, run_id)
            run.status = "failed"
            run.error_message = str(exc)[:500]
            run.finished_at = datetime.now(timezone.utc)
        log.error("sync.failed", table=source_table, error=str(exc))
        return {"status": "failed", "rows": total, "mode": mode, "error": str(exc)}
    conn.close()

    now = datetime.now(timezone.utc)
    if not incremental:
        if created_cols is None:  # zero-row source table: create empty target anyway
            conn = store.write_conn()
            conn.execute(f'CREATE TABLE "{staging}" ("empty" TEXT)')
            conn.commit()
            conn.close()
        columns, profile, row_count = _profile_table(staging)
        with create_db_session() as s:
            cfg = s.get(SyncTableRow, cfg_id)
            old_table = None
            ds = s.get(DatasetRow, cfg.dataset_id) if cfg.dataset_id else None
            if ds is None:
                ds = DatasetRow(
                    name=cfg.dataset_name,
                    original_filename=f"mssql: {source_table}",
                    table_name=staging,
                    source="mssql",
                    status="ready",
                )
                s.add(ds)
                s.flush()
                cfg.dataset_id = ds.id
            else:
                old_table = ds.table_name
                ds.table_name = staging
            ds.row_count = row_count
            ds.columns_json = json.dumps(columns, ensure_ascii=False)
            ds.profile_json = json.dumps(profile, ensure_ascii=False)
            ds.synced_at = now
            ds.status = "ready"
            cfg.last_synced_value = max_value
        if old_table:
            try:
                store.drop_table(old_table)
            except Exception:
                log.error("sync.old_table_drop_failed", table=old_table)
    else:
        columns, profile, row_count = _profile_table(target)
        with create_db_session() as s:
            cfg = s.get(SyncTableRow, cfg_id)
            ds = s.get(DatasetRow, cfg.dataset_id)
            if ds is not None:
                ds.row_count = row_count
                ds.columns_json = json.dumps(columns, ensure_ascii=False)
                ds.profile_json = json.dumps(profile, ensure_ascii=False)
                ds.synced_at = now
            cfg.last_synced_value = max_value

    with create_db_session() as s:
        run = s.get(SyncRunRow, run_id)
        run.status = "completed"
        run.rows = total
        run.finished_at = datetime.now(timezone.utc)
    log.info("sync.completed", table=source_table, rows=total, mode=mode)
    return {"status": "completed", "rows": total, "mode": mode, "error": None}


def sync_all(adapter, note: str | None = None) -> list[dict]:
    with create_db_session() as s:
        ids = [r.id for r in s.query(SyncTableRow).filter(SyncTableRow.enabled == 1).all()]
    return [sync_table(i, adapter, note=note) for i in ids]
