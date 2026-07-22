# Capability: Audit trail

## What It Does
Records every question run — question, language, final SQL, full step/attempt trace, result preview, caveats, token usage, duration, status — retrievable per run.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| completed/failed run state | AgentState | graph finalize/handle_error | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Run row (all audit fields) | Run | app DB |
| RunDetail | JSON | `GET /runs/{id}` |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| App DB | insert/update run | logged; the answer still reaches the user (audit write failure is loud in logs, not user-blocking) |

## Business Rules
- Failed and clarification runs are recorded too — the audit is complete, not success-only.
- Token usage from the provider's usage metadata (estimated only when the provider omits it, flagged as such).
- No user identity in v0.1 (single-user prototype); Phase 4 adds who-asked.

## Success Criteria
- [ ] After any answered question, its run row holds question, sql, steps (≥1 attempt), result preview, usage ints, duration_ms, status=completed.
- [ ] A failed run (unreachable LLM) is stored status=failed with error_message.
- [ ] `GET /runs/{id}` returns the full RunDetail for both.
