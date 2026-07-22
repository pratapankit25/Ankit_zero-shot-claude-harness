"""Read-only MsSQL adapter (python-tds — pure Python, no ODBC driver needed).

Only the sync engine talks to this; daytime questions never touch MsSQL
(spec/capabilities/mssql-nightly-sync.md). Credentials come from .env only.
"""
from collections.abc import Iterator
from datetime import date, datetime

from config.settings import get_settings


class MssqlError(Exception):
    """Connection/query failure with a user-safe message."""


def is_configured() -> bool:
    s = get_settings()
    return bool(s.mssql_host and s.mssql_database and s.mssql_username)


def _connect():
    import pytds

    s = get_settings()
    try:
        return pytds.connect(
            server=s.mssql_host,
            port=s.mssql_port,
            database=s.mssql_database,
            user=s.mssql_username,
            password=s.mssql_password,
            login_timeout=15,
            as_dict=False,
        )
    except Exception as exc:
        raise MssqlError(f"Could not connect to MsSQL at {s.mssql_host}:{s.mssql_port} — {exc}") from exc


def _norm(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    return v


class MssqlAdapter:
    """fetch_batches yields (columns, rows) with server-side keyset/offset paging —
    bounded memory, gentle on the source even off-peak."""

    def list_tables(self) -> list[str]:
        with _connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT TABLE_SCHEMA + '.' + TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_TYPE='BASE TABLE' ORDER BY 1"
            )
            return [r[0] for r in cur.fetchall()]

    def fetch_batches(
        self,
        table: str,
        incremental_column: str | None = None,
        after_value: str | None = None,
        batch_size: int | None = None,
    ) -> Iterator[tuple[list[str], list[list]]]:
        batch_size = batch_size or get_settings().sync_batch_rows
        safe_table = "].[".join(part.replace("]", "") for part in table.split("."))
        with _connect() as conn:
            cur = conn.cursor()
            offset = 0
            while True:
                if incremental_column:
                    col = incremental_column.replace("]", "")
                    where = f"WHERE [{col}] > %s" if after_value is not None else ""
                    sql = (
                        f"SELECT * FROM [{safe_table}] {where} ORDER BY [{col}] "
                        f"OFFSET {offset} ROWS FETCH NEXT {batch_size} ROWS ONLY"
                    )
                    cur.execute(sql, (after_value,) if after_value is not None else ())
                else:
                    sql = (
                        f"SELECT * FROM [{safe_table}] ORDER BY (SELECT NULL) "
                        f"OFFSET {offset} ROWS FETCH NEXT {batch_size} ROWS ONLY"
                    )
                    cur.execute(sql)
                rows = cur.fetchall()
                if not rows:
                    break
                columns = [d[0] for d in cur.description]
                yield columns, [[_norm(v) for v in r] for r in rows]
                if len(rows) < batch_size:
                    break
                offset += batch_size
