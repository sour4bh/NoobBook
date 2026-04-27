# `workspaces/` charter (NBB-010)

**Owner:** Workspace identity, workspace membership, invite/session context, and
workspace-scoped capability checks. Global instance administration remains
auth/bootstrap-owned; project-private access remains project-owned.

**Validation approach:** every durable table below points at the workspace
membership migration. Every runtime access claim points at the store or API
surface that enforces it.

## Tables owned by `workspaces/`

| Table | Defined in | Access enforcement | Notes |
|---|---|---|---|
| `workspaces` | `backend/supabase/migrations/00023_workspace_membership.sql` | Hosted: RLS through `user_has_workspace_access`. Backend: `workspace_store.session_context(...)` and workspace APIs. | Public signup gets a personal workspace where that user is `owner`. |
| `workspace_members` | `00023_workspace_membership.sql` | Hosted: members can see their memberships; owners/admins manage membership. Backend: workspace APIs. | Roles are `owner`, `admin`, and `member`. |
| `workspace_invites` | `00023_workspace_membership.sql` | Owner/admin write; signed-token acceptance path verifies token and expiry before membership creation. | Normal team onboarding uses invites, not generated passwords or global admin. |
| `workspace_provider_secrets` | `00023_workspace_membership.sql` | Owner/admin write; provider/client loading resolves workspace-scoped secrets for project actions. | Provider secrets are workspace-scoped; `.env` remains bootstrap/default fallback only. |

## Boundary rules

- Workspace membership alone is not project access. Project visibility and
  mutation are governed by `projects.project_members`.
- `global_role` is instance/bootstrap policy from `auth/`; public signup users
  receive `global_role=user`.
- Session DTOs expose workspace context through `workspace_store.session_context`
  so frontend gates use capability booleans rather than `global_role`.

## Cross-reference

- Project-private access: `backend/app/projects/CHARTER.md`.
- Schema/RLS inventory: `backend/supabase/migrations/OWNERS.md`.
- Storage contracts: `backend/supabase/STORAGE_CONTRACTS.md`.
