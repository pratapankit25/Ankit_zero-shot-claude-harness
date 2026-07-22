# Capability: Upload datasets

## What It Does
Accepts one or more CSV files, loads the **full** contents into the analytics store, auto-profiles each, and registers them in the persistent library.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| files | 1..10 CSV files, each ≤ AGENT_MAX_UPLOAD_MB (120) MB | multipart upload | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Dataset records (profile incl. per-column type/nulls/top values, warnings) | Dataset | app DB + response |
| Data table `ds_<id>` (all rows) | SQLite table | analytics store |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Analytics store | chunked table create + insert | dataset marked `error` with reason; partial table dropped |

(No LLM call — profiling is pure computation.)

## Business Rules
- Full load, never a sample; `row_count` equals the file's data rows.
- Encoding tolerance: UTF-8 (with/without BOM), UTF-16, common Windows codepages; delimiter sniffed (`,`, `;`, tab, `|`).
- Column names sanitized to SQL-safe snake_case; originals preserved in the registry; duplicate/blank headers deduped (`col_2`), files with no header row get `col_1..n` and a warning.
- Devanagari (Hindi) text in cells and headers loads intact.
- Numeric-looking and date-looking text columns are typed as such when ≥90% of a 500-value sample parses; otherwise TEXT with a `mixed types` warning.
- A failed file never blocks sibling files in the same request.

## Success Criteria
- [ ] A 3,000+-row fixture loads with exact row_count and expected column types; a query can hit row 3,000 (full-data, not sample).
- [ ] A messy fixture (blank + duplicate headers, mixed types, Hindi cells, cp1252 encoding) loads `ready` with the documented warnings.
- [ ] An unparseable file (binary/xlsx) yields `status=error` with a human-readable reason; a sibling CSV in the same request loads fine.
- [ ] Deleting a dataset removes its registry row and its `ds_` table.
