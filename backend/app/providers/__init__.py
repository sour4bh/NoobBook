"""
Providers root.

Charter (NBB-104): Low-level external API clients, SDK wrappers, auth
primitives, storage adapters, and runtime IO adapters. Providers are the
outermost edge: they speak the external protocol and expose a thin typed
surface. Boundary rules are finalized in `NBB-206`.

Allowed imports:
- `connectors/` depends on providers to build configured capabilities.
- Domains may depend on providers directly only for provider-neutral runtime
  primitives (for example HTTP clients, storage adapters, Claude API
  primitives). Product-specific integrations must pass through `connectors/`.
- Providers must not import from `api/`, domains, or `connectors/`.

Migration source: `backend/app/services/integrations/` feeds this root; Claude
and related provider utilities move under `NBB-705C`.
"""
