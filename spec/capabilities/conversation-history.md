# Capability: Conversation history

## What It Does
Persists every question→answer turn in named conversations so follow-ups resolve in context and past sessions reload.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| conversation_id | uuid | client | no (absent → new conversation titled from the first question) |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| conversation list / detail with full RunDetails | JSON | client |
| last ≤10 turns (question, answer≤500 chars, sql) | history | agent prompt context |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| App DB | read/write turns | surfaced API error |

## Business Rules
- History loading happens inside its own DB session and is fully detached before graph use (no lazy-load after close).
- Follow-ups like "now by month" must resolve the referent from history ("that district" → the one just discussed).
- Conversations are append-only; switching or reloading mid-conversation loses nothing.

## Success Criteria
- [ ] Two-turn test: turn 2 ("अब महीने के हिसाब से" / "now split by month") returns figures for the entity established in turn 1 — asserted against the fixture ground truth.
- [ ] State-survival: after a client reload (fresh GET /conversations/{id}), both turns render and a third turn still has context.
- [ ] Two parallel conversations don't leak context between each other.
