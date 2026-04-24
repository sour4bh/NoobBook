"""
Studio domain root.

Charter (NBB-104): Studio generation items and the studio job/tool/run layer.
Owns category-owned slices (documents, marketing, design, learning media) and
the status/progress contract consumed by the studio UI.

Allowed imports:
- `api/` route modules import this package's public surface.
- This package may depend on `sources/` (content consumption), `brand/`,
  `projects/`, `auth/`, `background/` (job lifecycle), `connectors/`, and
  `providers/`.
- This package must not reach into another domain's internals.

Migration source: `backend/app/services/studio_services/` feeds this domain;
the taxonomy, registry, and slice migrations are owned by `NBB-501A` through
`NBB-507`.
"""
