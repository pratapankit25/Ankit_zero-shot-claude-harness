"""Deterministic chart-spec detection from an executed result.

No LLM involvement (spec/capabilities/charts.md): chart data is exactly the
SQL result's rows. Unchartable shapes return None.
"""
import re
from numbers import Number

MAX_POINTS = 60
BAR_TOP_N = 20

_DATE_X = re.compile(r"^\d{4}([-/]\d{1,2}([-/]\d{1,2})?)?$")  # 2025 | 2025-03 | 2025-03-08


def _numeric(v) -> bool:
    return isinstance(v, Number) and not isinstance(v, bool)


def build_chart_spec(columns: list, rows: list) -> dict | None:
    if len(columns) != 2 or not (2 <= len(rows) <= MAX_POINTS * 4):
        return None
    pairs = [(r[0], r[1]) for r in rows if r[0] is not None and _numeric(r[1])]
    if len(pairs) < 2 or len(pairs) < 0.8 * len(rows):
        return None

    x_vals = [str(p[0]).strip() for p in pairs]
    date_like = sum(1 for x in x_vals if _DATE_X.match(x)) >= 0.9 * len(x_vals)

    if date_like:
        points = sorted(
            ({"x": str(x).strip(), "y": y} for x, y in pairs),
            key=lambda p: p["x"],
        )[:MAX_POINTS]
        kind = "line"
    else:
        points = [{"x": str(x).strip()[:40], "y": y} for x, y in pairs][:BAR_TOP_N]
        kind = "bar"

    if len(points) < 2:
        return None
    return {
        "type": kind,
        "x": str(columns[0]),
        "y": str(columns[1]),
        "points": points,
    }
