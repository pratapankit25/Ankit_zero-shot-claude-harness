# Capability: Auth & district roles *(Phase 4)*

## What It Does
Admin-created accounts with roles (admin / analyst / district-scoped viewer); district-scoped users see only datasets and conversations tagged to their district.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| users (username, password, role, district?) | admin UI | admin | yes |
| dataset district tags | edit UI | admin/analyst | for scoping |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| session cookie auth; scoped API responses | all endpoints | client |

## External Calls
None (local credential store, salted+hashed).

## Business Rules
- Passwords hashed (argon2/bcrypt); no self-registration; admin resets only.
- Scoping enforced server-side on datasets, questions (a scoped user's SQL can only touch permitted `ds_` tables — enforced by table allow-list in the validator), conversations, and audit.
- Audit rows gain user_id; SSO via portal is a later version (out of scope v0.1), the session layer is designed so an SSO header/OIDC login can replace the password check without rework.

## Success Criteria
- [ ] District user cannot list, query, or export another district's dataset (validator blocks even hand-crafted SQL naming it).
- [ ] Admin sees the full audit with user attribution.
- [ ] Unauthenticated requests to any data endpoint are 401 (except /health).
