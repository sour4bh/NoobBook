"""
Legacy auth services package.

NBB-201 consolidated auth ownership under `backend/app/auth/`:
- `identity.py`, `guards.py`, `permissions.py`, `access.py` live there.

Only `rbac.py` remains in this legacy location, holding the identity
resolver + its helpers until `NBB-706` removes the forwarding shim. No
re-exports from this package; import directly from `app.auth.*` or from
`app.services.auth.rbac` while the shim remains.
"""
