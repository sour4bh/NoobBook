# NoobBook Frontend Structure

This file is the canonical frontend structure and ownership guide. It is scoped to `frontend/` and sits beneath the repo-root `STRUCTURE.md`. Placement rules here override older guidance that lives in `AGENTS.md`, `CLAUDE.md`, and `CONTRIBUTING.md` while the migration is in progress.

Ticket provenance: `NBB-105` creates this document. `NBB-601` through `NBB-604` tighten ownership below the frontend shell without moving the shell itself.

## Direction

The frontend stays a conventional React + Vite + shadcn/ui + Tailwind application. The frontend shell - the four top-level directories under `frontend/src/` - keeps its familiar shape. Feature-local code (hooks, helpers, tests, local components) lives under the feature subtree that owns it, not under the shell buckets.

This document does not move any source files. It names what the shell means today and where new feature-local code must land.

## Shell Contract

The frontend shell is the set of top-level directories directly under `frontend/src/`. Each has a strict meaning. Feature-local code does not belong here.

| Shell | Meaning | Allowed |
|---|---|---|
| `frontend/src/components/` | App-level shared components and feature shell mounts only. | Shell frames, shared cross-feature components, the mount points that load a feature's root component from its feature subtree. |
| `frontend/src/components/ui/` | Shared UI primitives only. | shadcn wrappers and low-level atoms with no feature logic. |
| `frontend/src/hooks/` | App-level shared hooks only. | Hooks consumed by more than one feature with no feature-specific behavior. |
| `frontend/src/lib/` | Cross-feature utilities with no UI. | Pure helpers, formatters, and client primitives shared across features. |
| `frontend/src/contexts/` | Cross-feature React contexts only. | Contexts whose providers and consumers span multiple features. |

What is not allowed in the shell:
- Feature-specific components, hooks, helpers, or contexts.
- Anything that reads as "this belongs to chat / sources / studio / brand / etc." Those live in the owning feature subtree (for example `frontend/src/components/chat/`, `frontend/src/components/sources/`, `frontend/src/components/studio/`).
- New files under `frontend/src/components/hooks/`. See Legacy Markers below.

## Shell Charters

Each shell has one charter. If a file does not match its shell's charter, it does not belong there - reject the file in review, do not widen the charter.

- `frontend/src/components/` - app shell composition and cross-feature layouts only; the only feature reference allowed is the mount point that renders a feature subtree's root component.
- `frontend/src/components/ui/` - design-system primitives only (shadcn wrappers and low-level atoms with no feature logic and no product nouns).
- `frontend/src/hooks/` - app-wide hooks only (consumed by 2+ features, no feature-specific state, routing, or API calls).
- `frontend/src/lib/` - cross-feature utilities, shared API client primitives, and framework adapters only; no UI and no feature-owned product behavior.
- `frontend/src/contexts/` - app-wide React providers only (authentication, permissions, theming, and similarly global concerns).

### Do Not Put Feature-Owned X Here

These are reject-on-sight examples. They live in the owning feature subtree (for example `frontend/src/components/<feature>/`), not in the shell.

- Chat: do not put chat message renderers, chat composer/input controls, chat voice or transcription hooks, chat export helpers, or chat-only contexts in the shell.
- Sources: do not put source upload widgets, ingestion/citation/source-status hooks, per-source-type helpers, or source-only contexts in the shell.
- Studio: do not put studio generators, studio job/progress hooks, studio output renderers, or studio-only contexts in the shell.
- Settings: do not put settings panels, settings form hooks, API-key management helpers, or settings-only contexts in the shell.

The legacy exception is `frontend/src/components/hooks/` (see Legacy Markers); that path is frozen and no new files may land there regardless of owner.

## Feature-Local Placement

Feature-owned code lives beside the feature. A feature subtree is the unit of ownership.

- A feature's components, hooks, helpers, local contexts, and tests live inside its subtree (for example under `frontend/src/components/<feature>/`), not in the shell buckets above.
- Only the feature's top-level shell mount (the component the app renders from a route or parent screen) is referenced from outside the feature subtree.
- Moving a file from the shell into a feature subtree because it turned out to be feature-specific is a later ticket's job, not this one's. This document only sets the rule new files must follow.

## Legacy Markers

- `frontend/src/components/hooks/` is legacy. New files must not land there. Existing files remain until a later ticket (see `NBB-602`) migrates them to their owning feature subtree. The repo-root `STRUCTURE.md` lists this path in its frozen destinations; the guardrail owned by `NBB-103` enforces it in CI.

## Placement Checklist

Reviewers and authors run this checklist for every new frontend file. If any row fails, the file is in the wrong place.

1. **Ownership is identifiable.** The file has exactly one feature owner, or it is genuinely cross-feature (used by 2+ features today). "General frontend code" is not an owner.
2. **Feature-local code lives in the feature subtree.** If the file is feature-specific, it lands under the owning feature subtree - not in `frontend/src/components/`, `hooks/`, `lib/`, or `contexts/` at the shell level.
3. **Shell buckets keep their strict meaning.** `components/ui/` is shared UI primitives only; `hooks/`, `lib/`, and `contexts/` hold only cross-feature members with no feature-specific behavior.
4. **Not in a frozen destination.** The file is not added to `frontend/src/components/hooks/` or any other path listed as frozen in the repo-root `STRUCTURE.md`.
5. **Path reflects the concept, not the mechanism.** Name directories after the feature or capability (`chat`, `sources`, `studio`), not after the artifact type (`utils`, `helpers`, `services`).

If the answer to any row is "I am not sure," stop and check the owning ticket in `docs/tickets/epics/*.md` instead of guessing a path.

## Out of Scope for This Ticket

- No frontend source files are moved by `NBB-105`. This ticket is documentation only.
- Feature-owned hook and provider moves are `NBB-602`.
- `lib/`, `contexts/`, API client, citation, and logger ownership tightening is `NBB-603`.
- Domain subtree normalization and design-system guardrails are `NBB-604`.
- Frontend baseline test path selection is `NBB-108A`. Implementation, if chosen, is `NBB-108B`.
