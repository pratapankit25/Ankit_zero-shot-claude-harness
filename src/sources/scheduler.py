"""In-process scheduler: nightly MsSQL sync + scheduled summaries.

A daemon thread ticks every minute (server local time). Missed windows (machine
off at 02:00) run once at startup with a "late run" note — ordering guaranteed:
sync first, then summaries. Disable entirely with AGENT_SCHEDULER=0 (tests).
"""
import json
import os
import threading
import time
from datetime import date, datetime, timezone

from db.models import ScheduleRow, SyncRunRow, SyncTableRow
from db.session import create_db_session
from config.settings import get_settings
from observability.events import get_logger

log = get_logger("scheduler")
_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop = threading.Event()


def _last_completed_sync_day() -> date | None:
    with create_db_session() as s:
        run = (
            s.query(SyncRunRow)
            .filter(SyncRunRow.status == "completed")
            .order_by(SyncRunRow.started_at.desc())
            .first()
        )
        return run.started_at.date() if run else None


def _sync_due(now: datetime) -> tuple[bool, str | None]:
    from sources import mssql

    if not mssql.is_configured():
        return False, None
    with create_db_session() as s:
        if not s.query(SyncTableRow).filter(SyncTableRow.enabled == 1).count():
            return False, None
    last_day = _last_completed_sync_day()
    window_hour = get_settings().sync_hour
    if last_day == now.date():
        return False, None
    if now.hour == window_hour:
        return True, None
    if now.hour > window_hour:
        return True, "late run (machine was off at the scheduled time)"
    return False, None


def _schedules_due(now: datetime) -> list[tuple[str, str | None]]:
    due: list[tuple[str, str | None]] = []
    with create_db_session() as s:
        for sched in s.query(ScheduleRow).filter(ScheduleRow.enabled == 1).all():
            last = sched.last_run_at.date() if sched.last_run_at else None
            if last == now.date():
                continue
            if sched.cadence == "weekly":
                target_weekday = sched.weekday if sched.weekday is not None else 0
                if now.weekday() != target_weekday:
                    continue
            if now.hour == sched.hour:
                due.append((sched.id, None))
            elif now.hour > sched.hour:
                due.append((sched.id, "late run"))
    return due


def tick(now: datetime | None = None) -> dict:
    """One scheduler pass — separated from the thread for tests."""
    from sources import mssql, sync_engine, summaries

    now = now or datetime.now()
    result = {"synced": 0, "reports": 0}
    if not _lock.acquire(blocking=False):
        return result
    try:
        due, note = _sync_due(now)
        if due:
            outcomes = sync_engine.sync_all(mssql.MssqlAdapter(), note=note)
            result["synced"] = sum(1 for o in outcomes if o["status"] == "completed")
        for schedule_id, snote in _schedules_due(now):
            try:
                summaries.run_schedule(schedule_id, note=snote)
                result["reports"] += 1
            except Exception as exc:
                log.error("scheduler.summary_failed", schedule=schedule_id, error=str(exc))
    finally:
        _lock.release()
    return result


def _loop() -> None:
    while not _stop.wait(60):
        try:
            tick()
        except Exception as exc:
            log.error("scheduler.tick_failed", error=str(exc))


def start() -> None:
    global _thread
    if os.environ.get("AGENT_SCHEDULER", "1") == "0":
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="analyst-scheduler")
    _thread.start()
    log.info("scheduler.started", sync_hour=get_settings().sync_hour)
    try:  # catch up missed windows shortly after boot
        tick()
    except Exception as exc:
        log.error("scheduler.startup_tick_failed", error=str(exc))
