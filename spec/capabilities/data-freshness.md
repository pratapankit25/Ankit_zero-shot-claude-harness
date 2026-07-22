# Capability: Data freshness *(Phase 3)*

## What It Does
Shows on every dataset and every answer how fresh the underlying data is ("as of last night 02:00 sync" / "uploaded 3 days ago").

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| synced_at / created_at | timestamps | app DB | auto |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| freshness line on dataset cards and under each answer | UI text + RunDetail field | client |

## External Calls
None.

## Business Rules
- Every answer that used a dataset states the oldest freshness among the datasets it touched.
- Stale sync (>36 h for a scheduled source) shows a warning badge.

## Success Criteria
- [ ] Answer over a synced dataset carries "as of <sync time>"; over an upload, "uploaded <time>".
- [ ] A missed sync window flips the badge to stale.
