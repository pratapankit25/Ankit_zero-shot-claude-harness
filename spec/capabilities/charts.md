# Capability: Charts *(Phase 2)*

## What It Does
When a result is chartable (time series, ranked categories, comparisons), the agent emits a chart spec alongside the answer and the UI renders it inline.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| result table + question intent | state | graph | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| chart spec `{type: bar\|line, x, y, series?, title}` | JSON on RunDetail | client renders (no chart lib on the server) |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM (compose extended) | choose chart-worthiness + axes | degrade to no chart, never fail the run |

## Business Rules
- Chart data comes from the executed result rows only (≤200), never re-queried or invented.
- Not every answer gets a chart — single numbers and wide tables stay text/table.

## Success Criteria
- [ ] A month-trend fixture question yields a line chart spec whose points equal the SQL result.
- [ ] A "top N by X" question yields a bar chart; a single-number question yields none.
- [ ] Chart renders in the UI (E2E) with axes labelled.
