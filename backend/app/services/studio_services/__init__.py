"""
Studio Services - legacy migration source.

`studio_index_service` still lives here as a real submodule and is imported
directly via `app.services.studio_services.studio_index_service` (or the
package re-import that resolves the submodule by Python's normal package
mechanics, e.g. `from app.services.studio_services import studio_index_service`).

The former `audio_overview_service` re-export shim was removed in NBB-706;
callers import it from `app.studio.media.audio.generate` directly.
"""
from app.services.studio_services import studio_index_service

__all__ = ["studio_index_service"]
