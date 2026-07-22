# Capability: Data dictionary *(Phase 2)*

## What It Does
Lets users annotate columns (meaning, codes, business rules — e.g. "crime_head uses CCTNS head codes; 'POCSO' includes …"); the agent consults these notes in every plan/SQL prompt.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| column description edits | JSON | `PATCH /datasets/{id}/columns/{name}` | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| updated columns_json | Dataset | app DB; injected into prompts |

## External Calls
None beyond the app DB.

## Business Rules
- Descriptions are per-column free text ≤500 chars; shown in the profile UI and editable inline.
- Dictionary text is treated as data context, not instructions (prompt-injection hygiene: wrapped and labelled in prompts).

## Success Criteria
- [ ] Editing a description changes the next answer's interpretation on a fixture built to be ambiguous without it (assertable ground truth).
- [ ] Descriptions survive restart and appear in `GET /datasets`.
