"""
Cross-domain base root.

Charter (NBB-104, amended by NBB-812): Reserved for truly cross-domain
primitives. No file lands in `base/` without a PR note that proves:

1. Three or more domain consumers already use the same behavior.
2. No owning domain, connector, or provider is a better home.

Preemptive `base/` modules and generic helpers are forbidden. Rehome
candidates to the owning domain, a provider/client boundary, or a connector
capability. `base.paths` and `base.logging` are the NBB-812 replacements for
the final retired `app.utils` residents.

This package must not import from `api/`, any domain, `connectors/`, or
`providers/`.
"""
