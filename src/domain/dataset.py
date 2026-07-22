from pydantic import BaseModel


class ColumnInfo(BaseModel):
    name: str
    original_name: str
    type: str                       # "integer" | "real" | "text" | "date"
    null_count: int = 0
    distinct_count: int | None = None
    min: str | None = None
    max: str | None = None
    top_values: list[str] = []
    description: str = ""           # data-dictionary text (editable in Phase 2)


class DatasetProfile(BaseModel):
    warnings: list[str] = []
    date_columns: list[str] = []
    profiled_rows: int = 0
    provenance: dict | None = None   # derived datasets: {run_id, question, sql}


class DatasetOut(BaseModel):
    id: str
    name: str
    original_filename: str
    table_name: str
    source: str
    status: str
    error_message: str | None = None
    row_count: int | None = None
    size_bytes: int | None = None
    columns: list[ColumnInfo] = []
    profile: DatasetProfile | None = None
    district: str | None = None
    synced_at: str | None = None
    created_at: str | None = None
