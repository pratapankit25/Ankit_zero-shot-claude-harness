"""Computed anomaly flags — deterministic checks on the fetched result and the
stored dataset profiles. Code-phrased, never LLM-invented.
(spec/capabilities/anomaly-flags.md)
"""
import re

_MONTH_X = re.compile(r"^(\d{4})-(\d{2})$")
_HIGH_NULL_RATIO = 0.30


def _month_index(y: int, m: int) -> int:
    return y * 12 + (m - 1)


def _coverage_gaps(rows: list) -> list[str]:
    months = []
    for r in rows:
        if not r:
            continue
        m = _MONTH_X.match(str(r[0]).strip())
        if m:
            months.append((int(m.group(1)), int(m.group(2))))
    if len(months) < 3:
        return []
    idx = sorted({_month_index(y, m) for y, m in months})
    missing = []
    for a, b in zip(idx, idx[1:]):
        for gap in range(a + 1, b):
            missing.append(f"{gap // 12}-{gap % 12 + 1:02d}")
    return missing


def build_flags(result: dict, datasets: list, dataset_ids: list, sql: str) -> list[dict]:
    """Returns [{kind, message}] — empty on a clean result (no crying wolf)."""
    flags: list[dict] = []
    rows = (result or {}).get("rows", [])

    missing = _coverage_gaps(rows)
    if missing:
        shown = ", ".join(missing[:4]) + ("…" if len(missing) > 4 else "")
        flags.append({
            "kind": "coverage-gap",
            "message": f"No data for {len(missing)} month(s) in this range ({shown}) — the trend may look smoother or sharper than reality.",
        })

    sql_low = (sql or "").lower()
    for d in datasets or []:
        if dataset_ids and d.get("id") not in dataset_ids:
            continue
        total = d.get("row_count") or 0
        if not total:
            continue
        for c in d.get("columns", []):
            name = c.get("name", "")
            nulls = c.get("null_count") or 0
            if name and nulls / total > _HIGH_NULL_RATIO and re.search(rf"\b{re.escape(name)}\b", sql_low):
                flags.append({
                    "kind": "high-nulls",
                    "message": f"Column '{name}' is {round(100 * nulls / total)}% empty in '{d.get('name')}' — figures using it undercount.",
                })
    return flags[:4]
