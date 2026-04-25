"""
Studio Services - Services for studio features (audio overview, deep dive, etc.).

Educational Note: This folder contains services that handle studio features
like audio overview generation, deep dive conversations, and other interactive
content creation features.

Current Services:
- audio_overview_service: Generates audio overviews from source content
  Uses agentic loop to read content and generate TTS-optimized scripts
- studio_index_service: Tracks studio generation jobs (status, progress)

Planned Services:
- Deep dive conversation mode
- Interactive Q&A features
"""
from app.services.studio_services import studio_index_service
# audio_overview_service moved to app.studio.media.audio.generate (NBB-507);
# re-export preserved as backward-compat shim. NBB-706 owns removal.
from app.studio.media.audio.generate import audio_overview_service

__all__ = ["audio_overview_service", "studio_index_service"]
