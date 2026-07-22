# Capability: MsSQL nightly sync *(Phase 3)*

## What It Does
Extracts configured tables/views from the department MsSQL server into the analytics store on an off-peak schedule (default 02:00 IST), so daytime questions never touch MsSQL.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| connection (host, db, read-only login), table/view list, schedule, optional incremental key per table | source config | admin UI / `POST /sources` (secrets to `.env`) | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| datasets (source=`mssql`, synced_at) | Dataset per table | library + analytics store |
| sync log (started, rows, duration, status) | records | app DB + sources panel |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| MsSQL (pyodbc/pymssql, read-only) | `SELECT` full or incremental (`WHERE key > last`) with server-side paging | sync marked failed + surfaced; previous extract stays queryable; retry next window or manual "sync now" |

## Business Rules
- Read-only login enforced in docs and connection options (`ApplicationIntent=ReadOnly` where available); statement-level paging keeps memory bounded; extraction rate is capped to stay light even off-peak.
- Sync writes to a staging table, then atomically swaps — a failed sync never leaves a half-updated dataset.
- No sync activity outside the configured window except an explicit manual trigger.
- Row scale target: tables in the millions; this is the recorded decision point for a DuckDB analytics-store swap if latency demands it (see architecture).

## Success Criteria
- [ ] Against a disposable SQL Server fixture: full sync lands exact row counts; incremental sync moves only the delta.
- [ ] Mid-sync failure leaves the previous extract intact and queryable.
- [ ] With sync configured, answering questions issues zero MsSQL connections (asserted via connection spy).
