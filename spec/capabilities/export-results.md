# Capability: Export results *(Phase 2)*

## What It Does
Downloads an answer's full result (not just the 200-row preview) as Excel or CSV, re-executing the stored SQL server-side.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| run_id + format (`xlsx`\|`csv`) | path/query | `GET /runs/{id}/export` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| file download (question + SQL + timestamp on a header sheet for xlsx) | binary | client |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Analytics store | re-run stored SQL (read-only, 60 s cap, 500k-row cap) | 409 with reason (e.g. dataset deleted) |

## Business Rules
- Export re-runs the audited SQL verbatim; if the underlying dataset was deleted, the export fails honestly rather than serving stale previews.

## Success Criteria
- [ ] Export of a truncated-preview run yields the full row set (fixture count asserted, > preview cap).
- [ ] xlsx opens with data sheet + provenance sheet; CSV matches column order.
- [ ] Export after dataset deletion returns the documented 409.
