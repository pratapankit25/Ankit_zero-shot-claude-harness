"""Column profiling — pure computation, no LLM. (spec/capabilities/upload-datasets.md)"""
import pandas as pd

PROFILE_ROW_CAP = 100_000
TOP_VALUES = 5


def _col_type(series: pd.Series) -> str:
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "real"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    return "text"


def profile_frame(df: pd.DataFrame, name_map: dict[str, str], warnings: list[str]) -> tuple[list[dict], dict]:
    """Returns (columns_info, profile). name_map: sanitized -> original."""
    sample = df.head(PROFILE_ROW_CAP)
    columns: list[dict] = []
    date_columns: list[str] = []

    for col in df.columns:
        s = sample[col]
        ctype = _col_type(df[col])
        null_count = int(df[col].isna().sum())
        info: dict = {
            "name": col,
            "original_name": name_map.get(col, col),
            "type": ctype,
            "null_count": null_count,
            "distinct_count": None,
            "min": None,
            "max": None,
            "top_values": [],
            "description": "",
        }
        non_null = s.dropna()
        if len(non_null):
            distinct = int(non_null.nunique())
            info["distinct_count"] = distinct
            if ctype in ("integer", "real", "date"):
                info["min"] = str(non_null.min())
                info["max"] = str(non_null.max())
                if ctype == "date":
                    date_columns.append(col)
            if ctype == "text" or distinct <= 50:
                top = non_null.astype(str).value_counts().head(TOP_VALUES)
                info["top_values"] = [str(v) for v in top.index.tolist()]

        if len(df) and null_count / len(df) > 0.5:
            warnings.append(f"Column '{col}' is more than 50% empty.")
        if len(df) > 1 and info["distinct_count"] == 1:
            warnings.append(f"Column '{col}' has a single constant value.")
        columns.append(info)

    profile = {
        "warnings": warnings,
        "date_columns": date_columns,
        "profiled_rows": int(len(sample)),
    }
    return columns, profile
