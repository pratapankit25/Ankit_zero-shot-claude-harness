# Capability: Scheduled summaries *(Phase 3)*

## What It Does
Generates recurring (daily/weekly) summary reports from saved question sets ("morning crime brief": yesterday's FIR count by district, week-over-week change…) without anyone asking.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| schedule config: name, cron-ish cadence, list of questions, language(s) | JSON | admin UI / API | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| generated report (markdown; PDF in Phase 4) with per-question answers | stored report | app DB + reports list in UI |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM + analytics store | one run per question, batched sequentially | per-question failure noted inside the report; report still produced |

## Business Rules
- Runs after the nightly sync completes (ordering guaranteed), on the in-process scheduler; missed windows (machine off) run once at next startup with a "late" note.
- Each summary run is audited like any question run.

## Success Criteria
- [ ] A configured daily brief produces a report containing correct fixture numbers for all its questions.
- [ ] One failing question doesn't sink the report; the failure is visible inline.
- [ ] Reports list shows history with timestamps.
