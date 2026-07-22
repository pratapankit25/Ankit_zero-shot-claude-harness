# Capability: Anomaly flags *(Phase 2)*

## What It Does
While answering, the agent surfaces data-quality/statistical anomalies it can compute (gaps in date coverage, sudden spikes/drops, duplicate-heavy keys, high-null columns touched by the query) as labelled flags on the answer.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| result + touched-column profiles | state | graph | auto |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| flags `[{kind, message, evidence}]` | RunDetail | client (distinct styling from caveats) |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Analytics store | none in v1 — checks run on the already-fetched result + stored profiles | skip flagging, never fail the run |

## Business Rules
- Flags are computed AND phrased by code (deterministic templates) — the LLM never invents or words them.
- Bounded cost: companion checks ≤2 queries, each under the standard timeout.

## Success Criteria
- [ ] A fixture with a missing month yields a coverage-gap flag on a trend question.
- [ ] A clean fixture yields zero flags (no crying wolf).
