"""
Studio Services - legacy migration source.

`studio_index_service` still lives here as a real submodule while the studio
job index remains a studio-level service. Import it explicitly from
`app.services.studio_services.studio_index_service`; this package no longer
re-exports shims.
"""
