"""CSV → analytics store. Full load (never a sample), encoding/delimiter tolerant,
Devanagari-safe. (spec/capabilities/upload-datasets.md)"""
import csv as _csv
import io
import re
from uuid import uuid4

import pandas as pd

from ingest import store
from ingest.profiler import profile_frame


class IngestError(Exception):
    """Human-readable ingest failure."""


_ENCODINGS = ("utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1")
_DATE_SAMPLE = 500
_DATE_THRESHOLD = 0.9


def _decode(data: bytes) -> tuple[str, str]:
    for enc in _ENCODINGS:
        try:
            return data.decode(enc), enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise IngestError("Could not decode the file as text — is it an Excel/binary file? Export as CSV first.")


def _sniff_delimiter(text_head: str) -> str:
    try:
        return _csv.Sniffer().sniff(text_head, delimiters=",;\t|").delimiter
    except _csv.Error:
        return ","


def _looks_like_data(values: list[str]) -> bool:
    """True when a supposed header row is mostly numbers/dates → file has no header."""
    if not values:
        return False
    datalike = 0
    for v in values:
        v = (v or "").strip()
        if not v:
            continue
        try:
            float(v.replace(",", ""))
            datalike += 1
            continue
        except ValueError:
            pass
        if re.fullmatch(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", v):
            datalike += 1
    return datalike >= max(1, len(values) // 2)


def _sanitize_columns(raw_names: list[str], warnings: list[str]) -> tuple[list[str], dict[str, str]]:
    out: list[str] = []
    name_map: dict[str, str] = {}
    seen: dict[str, int] = {}
    for i, raw in enumerate(raw_names):
        original = str(raw)
        # pandas mangles duplicate headers to "Name.1", "Name.2" — undo so our
        # own dedupe (with a warning) applies
        m = re.fullmatch(r"(.+)\.(\d+)", original)
        if m and m.group(1) in raw_names[:i]:
            original = m.group(1)
        base = re.sub(r"[^0-9a-zA-Zऀ-ॿ]+", "_", original.strip().lower()).strip("_")
        base = re.sub(r"_{2,}", "_", base)
        if original.startswith("Unnamed:") or not base:
            base = f"col_{i + 1}"
            if original.startswith("Unnamed:"):
                warnings.append(f"Blank header in position {i + 1} named '{base}'.")
        if base[0].isdigit():
            base = f"c_{base}"
        n = seen.get(base, 0)
        seen[base] = n + 1
        final = base if n == 0 else f"{base}_{n + 1}"
        if n:
            warnings.append(f"Duplicate header '{original}' renamed to '{final}'.")
        out.append(final)
        name_map[final] = original
    return out, name_map


def _is_texty(series: pd.Series) -> bool:
    return series.dtype == object or pd.api.types.is_string_dtype(series)


def _coerce_dates(df: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    for col in df.columns:
        if not _is_texty(df[col]):
            continue
        non_null = df[col].dropna()
        if non_null.empty:
            continue
        sample = non_null.head(_DATE_SAMPLE)
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed", dayfirst=False)
        ratio = parsed.notna().mean()
        if ratio >= _DATE_THRESHOLD:
            full = pd.to_datetime(df[col], errors="coerce", format="mixed", dayfirst=False)
            bad = int(full.isna().sum() - df[col].isna().sum())
            if bad > 0:
                warnings.append(f"Column '{col}': {bad} value(s) did not parse as dates and became empty.")
            df[col] = full
    return df


def materialize_derived(sql: str) -> dict:
    """Materialize a validated SELECT as a new dataset table (Phase 2:
    spec/capabilities/derived-datasets.md). Returns the same shape as load_csv."""
    from uuid import uuid4 as _uuid4

    try:
        clean_sql = store.validate_select(sql)
    except store.QueryError as exc:
        raise IngestError(str(exc)) from exc

    table_name = f"ds_{_uuid4().hex[:12]}"
    conn = store.write_conn()
    try:
        try:
            conn.execute(f'CREATE TABLE "{table_name}" AS {clean_sql}')
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise IngestError(
                f"Could not materialize the result — the underlying data may have been deleted. ({exc})"
            ) from exc
        row_count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        df = pd.read_sql_query(f'SELECT * FROM "{table_name}" LIMIT 100000', conn)
    finally:
        conn.close()

    if row_count == 0:
        store.drop_table(table_name)
        raise IngestError("The result has no rows — nothing to save as a dataset.")

    warnings: list[str] = []
    from ingest.profiler import profile_frame
    columns, profile = profile_frame(df, {c: c for c in df.columns}, warnings)
    return {
        "table_name": table_name,
        "row_count": int(row_count),
        "columns": columns,
        "profile": profile,
    }


def load_csv(data: bytes, original_filename: str) -> dict:
    """Parse + load one CSV fully into the analytics store.

    Returns {table_name, row_count, columns, profile}. Raises IngestError.
    """
    if not data or not data.strip():
        raise IngestError("The file is empty.")
    if b"\x00" in data[:4096] and not data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        raise IngestError("This looks like a binary file (xlsx/zip?), not a CSV. Export as CSV first.")

    text, encoding = _decode(data)
    head = text[:65536]
    delimiter = _sniff_delimiter(head)

    first_line = head.splitlines()[0] if head.splitlines() else ""
    header_cells = next(_csv.reader(io.StringIO(first_line), delimiter=delimiter), [])
    warnings: list[str] = []
    headerless = _looks_like_data(header_cells)

    try:
        df = pd.read_csv(
            io.StringIO(text),
            sep=delimiter,
            header=None if headerless else 0,
            low_memory=False,
            skip_blank_lines=True,
        )
    except Exception as exc:
        raise IngestError(f"Could not parse as CSV: {exc}") from exc

    if df.empty or len(df.columns) == 0:
        raise IngestError("The file parsed but contains no data rows.")

    if headerless:
        df.columns = [f"col_{i + 1}" for i in range(len(df.columns))]
        warnings.append("No header row detected — columns named col_1..col_n.")

    sanitized, name_map = _sanitize_columns([str(c) for c in df.columns], warnings)
    df.columns = sanitized
    if encoding not in ("utf-8", "utf-8-sig"):
        warnings.append(f"File decoded as {encoding}.")

    df = _coerce_dates(df, warnings)
    for col in df.columns:
        if _is_texty(df[col]):
            mixed_numeric = pd.to_numeric(df[col].dropna().head(_DATE_SAMPLE), errors="coerce").notna().mean()
            if 0.3 <= mixed_numeric < _DATE_THRESHOLD:
                warnings.append(f"Column '{col}' has mixed number/text values — kept as text.")

    columns, profile = profile_frame(df, name_map, warnings)

    # datetimes → ISO text for SQLite (date-only when no time component)
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            series = out[col]
            if (series.dropna().dt.normalize() == series.dropna()).all():
                out[col] = series.dt.strftime("%Y-%m-%d")
            else:
                out[col] = series.dt.strftime("%Y-%m-%d %H:%M:%S")

    table_name = f"ds_{uuid4().hex[:12]}"
    conn = store.write_conn()
    try:
        out.to_sql(table_name, conn, if_exists="fail", index=False, chunksize=5000)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        store.drop_table(table_name)
        raise IngestError(f"Could not load the data: {exc}") from exc
    conn.close()

    return {
        "table_name": table_name,
        "row_count": int(len(df)),
        "columns": columns,
        "profile": profile,
    }
