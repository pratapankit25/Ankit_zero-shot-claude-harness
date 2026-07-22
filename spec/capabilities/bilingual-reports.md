# Capability: Bilingual reports *(Phase 4)*

## What It Does
Turns any answer, conversation, or scheduled summary into a formatted briefing PDF in Hindi, English, or both side-by-side (Devanagari rendered correctly).

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| run/conversation/summary id + language mode | request | UI button / API | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| PDF (header, date, Q&A sections, tables, charts, freshness + caveats footer) | download + stored | client + app DB |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM | translate/adapt the existing answer (numbers copied verbatim, never re-derived) | fall back to source-language-only PDF with a notice |

## Business Rules
- Numbers, SQL, and tables are carried from the audited run — translation touches prose only.
- A Devanagari-capable font ships with the app (no system-font dependence).

## Success Criteria
- [ ] Bilingual PDF shows identical numbers in both language columns (fixture-asserted extraction).
- [ ] Devanagari renders (no tofu) in the generated PDF.
