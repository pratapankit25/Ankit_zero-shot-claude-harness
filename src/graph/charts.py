"""Deterministic chart-spec detection from an executed result.

No LLM involvement (spec/capabilities/charts.md): chart data is exactly the
SQL result's rows. Role-based detection tolerates the shapes real LLM SQL
produces — extra constant columns, numeric values returned as text, and any
column order. Genuinely multi-dimensional or single-number results yield None.
"""
import re
from numbers import Number

MAX_POINTS = 60
BAR_TOP_N = 20
MAX_ROWS = 240
NUMERIC_RATIO = 0.9

_DATE_X = re.compile(r"^\d{4}([-/]\d{1,2}([-/]\d{1,2})?)?$")  # 2025 | 2025-03 | 2025-03-08
# year/date-shaped values act as LABELS even though they coerce to numbers
_YEARISH = re.compile(r"^(19|20)\d{2}([-/]\d{1,2}([-/]\d{1,2})?)?$")


def _coerce_number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, Number):
        return v
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                return None
    return None


def _column_roles(columns: list, rows: list) -> tuple[list[int], list[int]]:
    """Classify column indexes into (numeric_measures, labels), dropping constants."""
    numeric: list[int] = []
    labels: list[int] = []
    for i in range(len(columns)):
        values = [r[i] for r in rows if len(r) > i and r[i] is not None]
        if not values:
            continue
        distinct = {str(v) for v in values}
        if len(distinct) <= 1 and len(rows) > 1:
            continue  # constant column (e.g. a selected year) — irrelevant to the chart
        yearish = sum(1 for v in values if _YEARISH.match(str(v).strip()))
        if yearish >= NUMERIC_RATIO * len(values):
            labels.append(i)  # years/months read as an axis, not a measure
            continue
        coerced = [_coerce_number(v) for v in values]
        ok = sum(1 for c in coerced if c is not None)
        if ok >= NUMERIC_RATIO * len(values):
            numeric.append(i)
        else:
            labels.append(i)
    return numeric, labels


def build_chart_spec(columns: list, rows: list) -> dict | None:
    if not columns or not (2 <= len(rows) <= MAX_ROWS):
        return None
    numeric, labels = _column_roles(columns, rows)
    if not numeric or len(labels) != 1:
        return None  # no measure, or multi-dimensional (2+ label columns) — v1 skips
    x_i = labels[0]
    y_i = numeric[0]  # first numeric column is the measure; header names it

    pairs = []
    seen_x = set()
    for r in rows:
        if len(r) <= max(x_i, y_i) or r[x_i] is None:
            continue
        y = _coerce_number(r[y_i])
        if y is None:
            continue
        x = str(r[x_i]).strip()
        if x in seen_x:
            return None  # repeated labels = flattened multi-series; a naive chart would mislead
        seen_x.add(x)
        pairs.append((x, y))
    if len(pairs) < 2 or len(pairs) < 0.8 * len(rows):
        return None

    date_like = sum(1 for x, _ in pairs if _DATE_X.match(x)) >= 0.9 * len(pairs)
    if date_like:
        points = sorted(({"x": x, "y": y} for x, y in pairs), key=lambda p: p["x"])[:MAX_POINTS]
        kind = "line"
    else:
        points = [{"x": x[:40], "y": y} for x, y in pairs][:BAR_TOP_N]
        kind = "bar"

    if len(points) < 2:
        return None
    return {
        "type": kind,
        "x": str(columns[x_i]),
        "y": str(columns[y_i]),
        "points": points,
    }
