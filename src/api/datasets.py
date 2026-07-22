import json
from uuid import uuid4

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from api._common import api_error, ok
from config.settings import get_settings
from db.models import DatasetRow, RunRow
from db.session import get_session
from domain.dataset import DatasetOut
from domain.question import ColumnDescriptionPatch, DerivedDatasetRequest
from ingest import store
from ingest.loader import IngestError, load_csv, materialize_derived
from observability.events import get_logger

router = APIRouter()
log = get_logger("api.datasets")


def _to_out(row: DatasetRow) -> dict:
    return DatasetOut(
        id=row.id,
        name=row.name,
        original_filename=row.original_filename,
        table_name=row.table_name,
        source=row.source,
        status=row.status,
        error_message=row.error_message,
        row_count=row.row_count,
        size_bytes=row.size_bytes,
        columns=json.loads(row.columns_json or "[]"),
        profile=json.loads(row.profile_json or "null"),
        created_at=row.created_at.isoformat() if row.created_at else None,
    ).model_dump()


def _error_row(display: str, filename: str, message: str, size: int) -> DatasetRow:
    return DatasetRow(
        name=display,
        original_filename=filename,
        table_name=f"ds_{uuid4().hex[:12]}",  # placeholder, no table behind it
        source="csv",
        status="error",
        error_message=message,
        size_bytes=size,
    )


@router.post("/datasets")
async def upload_datasets(files: list[UploadFile], session: Session = Depends(get_session)) -> dict:
    if not files:
        raise api_error("NO_FILES", "Attach at least one CSV file.", 400)
    s = get_settings()
    cap_bytes = s.max_upload_mb * 1024 * 1024
    out: list[dict] = []
    for f in files[:10]:
        data = await f.read()
        filename = f.filename or "upload.csv"
        display = filename.rsplit(".", 1)[0][:80] or "dataset"
        if len(data) > cap_bytes:
            row = _error_row(display, filename, f"File is over the {s.max_upload_mb} MB limit.", len(data))
        else:
            try:
                loaded = load_csv(data, filename)
                row = DatasetRow(
                    name=display,
                    original_filename=filename,
                    table_name=loaded["table_name"],
                    source="csv",
                    status="ready",
                    row_count=loaded["row_count"],
                    size_bytes=len(data),
                    columns_json=json.dumps(loaded["columns"], ensure_ascii=False),
                    profile_json=json.dumps(loaded["profile"], ensure_ascii=False),
                )
                log.info("dataset.loaded", rows=loaded["row_count"], file=filename)
            except IngestError as exc:
                row = _error_row(display, filename, str(exc), len(data))
                log.info("dataset.failed", file=filename, error=str(exc))
        session.add(row)
        session.flush()
        out.append(_to_out(row))
    return ok(out)


@router.post("/datasets/derived")
def save_derived(req: DerivedDatasetRequest, session: Session = Depends(get_session)) -> dict:
    """Save a run's full result as a reusable dataset (spec/capabilities/derived-datasets.md)."""
    run = session.get(RunRow, req.run_id)
    if run is None:
        raise api_error("NOT_FOUND", f"Run {req.run_id} not found", 404)
    if not run.sql_text or run.status != "completed":
        raise api_error("NOT_DERIVABLE", "This run has no executed query to save.", 409)
    try:
        loaded = materialize_derived(run.sql_text)
    except IngestError as exc:
        raise api_error("DERIVE_FAILED", str(exc), 409)

    profile = loaded["profile"]
    profile["provenance"] = {
        "run_id": run.id,
        "question": run.input_text,
        "sql": run.sql_text,
    }
    row = DatasetRow(
        name=req.name,
        original_filename=f"derived from: {(run.input_text or '')[:60]}",
        table_name=loaded["table_name"],
        source="derived",
        status="ready",
        row_count=loaded["row_count"],
        columns_json=json.dumps(loaded["columns"], ensure_ascii=False),
        profile_json=json.dumps(profile, ensure_ascii=False),
    )
    session.add(row)
    session.flush()
    log.info("dataset.derived", id=row.id, from_run=run.id, rows=row.row_count)
    return ok(_to_out(row))


@router.patch("/datasets/{dataset_id}/columns/{column_name}")
def set_column_description(
    dataset_id: str,
    column_name: str,
    patch: ColumnDescriptionPatch,
    session: Session = Depends(get_session),
) -> dict:
    """Data dictionary: annotate a column; the agent reads these in every prompt
    (spec/capabilities/data-dictionary.md)."""
    row = session.get(DatasetRow, dataset_id)
    if row is None:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found", 404)
    columns = json.loads(row.columns_json or "[]")
    target = next((c for c in columns if c.get("name") == column_name), None)
    if target is None:
        raise api_error("NOT_FOUND", f"Column {column_name} not found", 404)
    target["description"] = patch.description
    row.columns_json = json.dumps(columns, ensure_ascii=False)
    log.info("dataset.dictionary_updated", id=dataset_id, column=column_name)
    return ok(_to_out(row))


@router.get("/datasets")
def list_datasets(session: Session = Depends(get_session)) -> dict:
    rows = session.query(DatasetRow).order_by(DatasetRow.created_at.desc()).all()
    return ok([_to_out(r) for r in rows])


@router.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(DatasetRow, dataset_id)
    if row is None:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found", 404)
    if row.status == "ready":
        try:
            store.drop_table(row.table_name)
        except store.QueryError as exc:
            log.error("dataset.drop_failed", id=dataset_id, error=str(exc))
    session.delete(row)
    log.info("dataset.deleted", id=dataset_id)
    return ok({"deleted": True})
