"""
Cross-domain base root.

Charter (NBB-104): Reserved for truly cross-domain primitives. `base/` ships
empty at the end of Epic 001. No file lands in `base/` without a PR note that
proves:

1. Three or more domain consumers already use the same behavior.
2. No owning domain, connector, or provider is a better home.

Preemptive `base/` modules and generic helpers are forbidden. Rehome
candidates to the owning domain, a provider/client boundary, a connector
capability, or the approved `utils/` exceptions enumerated by `NBB-705E`.

This package must not import from `api/`, any domain, `connectors/`, or
`providers/`.
"""
