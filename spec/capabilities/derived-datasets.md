# Capability: Derived datasets *(Phase 2)*

## What It Does
Saves an answer's result as a new named dataset in the library (source=`derived`), reusable in later questions and joins.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| run_id + name | JSON | `POST /datasets/derived` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| new Dataset (full result materialized, profiled) | Dataset | library + analytics store |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Analytics store | `CREATE TABLE ds_x AS <stored sql>` (write path via ingest, not the agent's ro connection) | surfaced error; nothing partial left behind |

## Business Rules
- Provenance recorded (source run + SQL) and visible in the dataset profile.
- Derived datasets behave exactly like uploads (profile, ask, join, delete).

## Success Criteria
- [ ] Save → appears in library with correct row_count; a follow-up question can query and join it.
- [ ] Provenance shows the originating question + SQL.
