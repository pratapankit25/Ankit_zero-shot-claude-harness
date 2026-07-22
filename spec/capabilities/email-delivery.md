# Capability: Email delivery *(Phase 4)*

## What It Does
Emails scheduled summaries and on-demand reports (PDF attached) to configured recipient lists over the department's SMTP.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| SMTP config | `.env` | admin | yes |
| recipient lists per schedule/report | admin UI | admin | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| sent email + delivery log (sent/failed/retried) | SMTP + app DB | recipients; admin panel |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| SMTP | send with attachment | 3 retries with backoff → marked failed, visible in panel; report remains downloadable |

## Business Rules
- Send only to admin-configured lists (no free-form recipients from non-admins).
- Attachment size guarded (>10 MB → link-style fallback text with instructions).

## Success Criteria
- [ ] Against a local SMTP fixture (mailpit): scheduled summary arrives with correct subject + PDF.
- [ ] SMTP down → delivery log shows retries then failed; UI surfaces it; no crash.
