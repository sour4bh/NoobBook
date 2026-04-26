"""
AI Services - Simple AI-powered utility services.

Educational Note: This folder contains lightweight AI services that perform
single, focused tasks. These are NOT complex agents with tool loops - they
are simple request/response AI utilities.

Modules:
- memory_service: AI-powered memory merging (max 150 tokens per memory).

Migrated out of this package by NBB-706:
- chat_naming_service -> behavior moved into app/chat/naming.py.
- video_prompt_service -> moved to app/studio/media/video/prompt.py.

Migrated out of this package by NBB-803:
- summary source behavior -> app/sources/summary.py.
- embedding source behavior -> app/sources/embedding.py.
- PDF/PPTX/image extraction -> app/sources/{pdf,pptx,image}/extract.py.

These services typically:
- Make a single API call per request (or batched calls for large documents)
- Use Haiku model for speed and cost efficiency
- Have simple input/output patterns
- Load prompts via prompt_loader.get_prompt_config()

Import Pattern:
Services are NOT imported at module level to avoid circular imports.
Import directly from the specific module:
    from app.services.ai_services.memory_service import memory_service
"""
