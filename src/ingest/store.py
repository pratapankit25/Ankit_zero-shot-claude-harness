"""Analytics store — the second SQLite file holding dataset tables (ds_*).

Written only by ingest; read by the agent over a read-only connection with a
deny-by-default authorizer, statement timeout, and row cap.
(spec/architecture.md → Security & Privacy Boundaries)
"""
import re
import sqlite3
import time
from pathlib import Path

from config.settings import get_settings


class QueryError(Exception):
    """A rejected or failed analytics query — message is safe to show the LLM/user."""


_ALLOWED_AUTH_CODES = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}

_SELECT_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


def analytics_path() -> Path:
    p = Path(get_settings().analytics_db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def write_conn() -> sqlite3.Connection:
    """Read-write connection — ingest and Phase-3 sync only, never the agent."""
    conn = sqlite3.connect(analytics_path())
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def read_conn() -> sqlite3.Connection:
    """Read-only connection with an allow-list authorizer (defense in depth)."""
    path = analytics_path()
    if not path.exists():
        # create the empty store so ro-open succeeds before any upload
        write_conn().close()
    # as_uri() yields a valid file:// URI on every platform (Windows backslashes
    # break the naive f"file:{path}" form)
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)

    def _authorizer(code: int, *_args) -> int:
        return sqlite3.SQLITE_OK if code in _ALLOWED_AUTH_CODES else sqlite3.SQLITE_DENY

    conn.set_authorizer(_authorizer)
    return conn


def validate_select(sql: str) -> str:
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise QueryError("Empty SQL statement.")
    if ";" in sql:
        raise QueryError("Only a single SQL statement is allowed.")
    if not _SELECT_RE.match(sql):
        raise QueryError("Only read-only SELECT statements are allowed.")
    return sql


def run_select(
    sql: str,
    *,
    timeout_s: float | None = None,
    row_cap: int | None = None,
) -> dict:
    """Validate + execute one SELECT. Returns {columns, rows, row_count, truncated}.

    Raises QueryError with a message safe to feed back to the SQL-writing LLM.
    """
    s = get_settings()
    timeout_s = timeout_s if timeout_s is not None else s.sql_timeout_s
    row_cap = row_cap if row_cap is not None else s.result_row_cap
    sql = validate_select(sql)

    conn = read_conn()
    deadline = time.monotonic() + timeout_s
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 50_000)
    try:
        try:
            cur = conn.execute(sql)
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc).lower():
                raise QueryError(f"Query timed out after {timeout_s:.0f}s — simplify or aggregate.")
            raise QueryError(f"SQL error: {exc}")
        except sqlite3.DatabaseError as exc:
            raise QueryError(f"SQL error: {exc}")

        columns = [d[0] for d in cur.description] if cur.description else []
        try:
            fetched = cur.fetchmany(row_cap + 1)
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc).lower():
                raise QueryError(f"Query timed out after {timeout_s:.0f}s — simplify or aggregate.")
            raise QueryError(f"SQL error: {exc}")
        truncated = len(fetched) > row_cap
        rows = [list(r) for r in fetched[:row_cap]]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }
    finally:
        conn.close()


def drop_table(table_name: str) -> None:
    if not re.fullmatch(r"ds_[0-9a-f]{12}", table_name):
        raise QueryError(f"Refusing to drop non-dataset table {table_name!r}")
    with write_conn() as conn:
        conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')


def table_row_count(table_name: str) -> int:
    with read_conn() as conn:
        return conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
