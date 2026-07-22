# Capability: Ask a question

## What It Does
Answers a natural-language question (English / Hindi / Hinglish) about the library by planning, generating and executing read-only SQL over the full data, self-checking, and composing a streamed answer in the question's language.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| question | text (any script) | user | yes |
| conversation_id | uuid | client (optional → new) | no |
| dataset registry + profiles + history | records | app DB | auto |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| streamed step events + answer deltas | SSE | client |
| answer (markdown, question's language), sql, steps, result table ≤200 rows, caveats, follow-ups, usage | RunDetail | client + audit |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM (plan / write_sql / compose) | JSON + streaming generations | run fails with plain-language error; one transient retry in client |
| Analytics store (read-only) | validated SELECT | error fed back to write_sql, ≤4 iterations |

## Business Rules
- Adaptive depth: simple question → 1 plan step + 1 SQL; complex → up to 4 plan steps / SQL iterations. Retries feed the SQL error or empty-result signal back to the generator.
- The LLM never sees raw rows: schemas, profiles (incl. top values), and ≤50-row computed results only.
- SQL guardrails: single SELECT, read-only connection + authorizer, 8 s timeout, 200-row fetch cap with truncation flag.
- Ambiguous question (or empty library) → clarification turn instead of a guess; otherwise answer with assumptions stated in caveats.
- Joins across datasets are allowed and encouraged when the question spans them.
- Answer language mirrors question language; numbers come verbatim from the SQL result (no LLM arithmetic on the tested path).

## Success Criteria
- [ ] Known-answer fixture questions (EN and HI) return the exact pre-computed number in the answer text, with the executed SQL exposed.
- [ ] A cross-dataset join question (FIRs vs personnel by station) returns the pre-computed ranking.
- [ ] A question whose first SQL errors still succeeds via retry (trace shows >1 attempt) on a crafted trap fixture.
- [ ] An ambiguous question yields status=clarification with a question, not a guess.
- [ ] A Hindi question is answered in Hindi (Devanagari present in answer).
- [ ] With an unreachable LLM, the run fails with a message naming `.env`/network — never a silent hang or stack trace.
