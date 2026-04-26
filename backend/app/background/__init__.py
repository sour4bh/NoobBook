"""
Background tasks root.

Charter (NBB-104): Task lifecycle, cancellation, active-task status, and
execution-log ownership. One owner for the background subsystem consumed by
`sources/` ingestion, `studio/` jobs, and any other domain that enqueues
asynchronous work. Final consolidation is owned by `NBB-210`.

Allowed imports:
- Domains import the background public surface to enqueue, cancel, and poll
  tasks.
- This package may depend on `providers/` for storage and scheduling
  primitives and on `auth/` for task-owner checks.
- This package must not reach into a domain's internals; domain-specific work
  is registered through the background task contract, not embedded here.

Migration source: `backend/app/services/background_services/` formerly fed this root.
"""
