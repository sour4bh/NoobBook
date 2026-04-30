"""
Providers root.

Charter (NBB-104): Low-level external API clients, SDK wrappers, auth
primitives, storage adapters, and runtime IO adapters. Providers are the
outermost edge: they speak the external protocol and expose a thin typed
surface. Boundary rules are finalized in `NBB-206`.

Allowed imports:
- `connectors/` depends on providers to build configured capabilities.
- Domains may depend on providers directly only for provider-neutral runtime
  primitives (for example HTTP clients and storage adapters) or through
  `app.agents.runtime` provider adapters. Product-specific integrations must
  pass through `connectors/`.
- Providers must not import from `api/`, domains, or `connectors/`.

Migration source: `backend/app/services/integrations/` fed this root; `NBB-705C`
and `NBB-806` moved provider utilities and raw provider clients here.

See `CHARTER.md` in this directory for the NBB-206 boundary overlay.
"""
