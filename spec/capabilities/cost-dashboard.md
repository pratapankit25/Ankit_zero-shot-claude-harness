# Capability: Cost dashboard *(Phase 4)*

## What It Does
Admin view of LLM spend: daily running total (₹ and tokens), per-day history, top conversations by usage — sourced from the audit trail's per-run token counts.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| runs.usage aggregates | app DB | audit trail | auto |
| price table (per-model ₹/1M tokens) | config | `.env`/settings | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| daily totals + history | admin UI panel | client (admin role only) |

## External Calls
None.

## Business Rules
- Costs are estimates from the configured price table, labelled as such; tokens are exact (provider-reported).
- Visible to admins only (per intake: hidden from regular users).

## Success Criteria
- [ ] Day total equals the sum of that day's run usage × configured prices (fixture-asserted).
- [ ] Non-admin cannot access the panel or endpoint.
