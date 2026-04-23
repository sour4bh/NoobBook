# NoobBook Structure Migration Backlog

This backlog is organized as seven epics with embedded child tickets. Epic files are the human-readable source of truth. `tickets.csv` is the machine-readable index for planning views and validation scripts.

The previous flat ticket set has been archived under `docs/tickets/archive/legacy-flat/` before the new overlapping epic IDs were introduced.

## ID Model

| Range | Meaning |
|---|---|
| `NBB-001` through `NBB-007` | Epics |
| `NBB-101` through `NBB-108` | Foundation tasks |
| `NBB-201` through `NBB-210` | Central policy, safety, and boundary tasks |
| `NBB-301` through `NBB-304` | Chat migration tasks |
| `NBB-401` through `NBB-404` | Sources migration tasks |
| `NBB-501` through `NBB-507` | Studio migration tasks |
| `NBB-601` through `NBB-604` | Frontend tightening tasks |
| `NBB-701` through `NBB-706` | Verification and cleanup tasks |

## Core Policies

- `backend/app/api` remains the transport boundary in this migration. Route files parse HTTP, run guards, call domain public surfaces, and format responses. Route movement is tracked in `DEFERRED.md`.
- New backend code should move toward domain roots rather than mechanism buckets such as `services/`, `utils/`, `ai_agents/`, `ai_services/`, `tool_executors/`, `services/tools/`, or `data/prompts/`.
- Prompt JSON and tool JSON may not move until `NBB-207` lands loader registry/shims.
- `platform/files/` is not a dumping ground. Vendor SDK clients belong under `platform`; source format operations belong under `sources`; studio export/screenshot support belongs under `studio`.
- `base/` and every `shared/` family require narrow charters from `NBB-104`.
- Temporary shims are allowed during migration, but `NBB-706` must remove forwarding-only modules unless a documented compatibility boundary remains.

## Execution Order

Start with Foundation:

1. `NBB-101`
2. `NBB-102`
3. `NBB-103`
4. `NBB-104`
5. `NBB-105`
6. `NBB-106`
7. `NBB-107`
8. `NBB-108`

Then run Epic 002 by need, not as a serialized mega-block. Downstream work unlocks by dependency slices.

## Unlock Matrix

| Stream | May start after |
|---|---|
| Epic 003 Chat | `NBB-106`, `NBB-107`, `NBB-201`, `NBB-202`, `NBB-205`, `NBB-206`, `NBB-207`, and the chat/message store slice of `NBB-209` |
| Epic 004 Sources | `NBB-106`, `NBB-203`, `NBB-204`, `NBB-206`, `NBB-207`, and source-relevant slices of `NBB-209` |
| Epic 005 Studio | `NBB-106`, `NBB-204`, `NBB-205`, `NBB-206`, `NBB-207`, and `NBB-210` |
| Epic 006 Frontend | `NBB-105`, coordinated with `NBB-205` and `NBB-108` |
| Epic 007 Cleanup | Relevant owning migrations completed |

## Epics

| Epic | Title | File |
|---|---|---|
| `NBB-001` | Foundation and Migration Guardrails | `docs/tickets/epics/NBB-001.md` |
| `NBB-002` | Central Policy, Safety, and Shared Boundaries | `docs/tickets/epics/NBB-002.md` |
| `NBB-003` | Chat Domain Migration | `docs/tickets/epics/NBB-003.md` |
| `NBB-004` | Sources Domain Migration | `docs/tickets/epics/NBB-004.md` |
| `NBB-005` | Studio Domain Migration | `docs/tickets/epics/NBB-005.md` |
| `NBB-006` | Frontend Ownership Tightening | `docs/tickets/epics/NBB-006.md` |
| `NBB-007` | Verification, Enforcement, and Cleanup | `docs/tickets/epics/NBB-007.md` |

## Validation Expectations

Static checks should verify:

- old flat tickets are archived under `docs/tickets/archive/legacy-flat/`
- exactly seven epic files exist
- every CSV key appears in its epic file as an explicit anchor
- every dependency ID exists
- no stale `develop only` or `amitdevv/NoobBook.git` guidance remains in new ticket docs
- no old `ai_agents/ai_services/tool_executors` taxonomy is presented as current guidance
- no unqualified `platform/files/` target appears
- no `utils empty` criterion appears without approved exceptions
- no unresolved studio category placeholder remains
- no `base/` or `shared/` proposal appears without a linked charter
- no prompt/tool JSON move appears before `NBB-207`
- no permanent forwarding-only wrapper is accepted

See `TRACEABILITY.md` for old-ticket and finding mappings. See `DEFERRED.md` for tracked work intentionally outside this rewrite.
