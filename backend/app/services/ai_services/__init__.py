"""
AI Services - Simple AI-powered utility services.

Educational Note: This folder contains lightweight AI services that perform
single, focused tasks. These are NOT complex agents with tool loops - they
are simple request/response AI utilities.

Modules:
- summary_service (module): generate_summary() for source documents
  (150-200 tokens). Converted from class form in NBB-706.
- memory_service: AI-powered memory merging (max 150 tokens per memory).
- image_service: extract content from images using Claude vision.
- pdf_service: extract text from PDFs using batched tool-based approach.
- pptx_service: extract content from PowerPoint presentations using Claude vision.
- embedding_service (module): orchestrates embedding pipeline (chunk, embed,
  upsert to Pinecone). Converted from class form in NBB-706.

Migrated out of this package by NBB-706:
- chat_naming_service -> behavior moved into app/chat/naming.py.
- video_prompt_service -> moved to app/studio/media/video/prompt.py.

These services typically:
- Make a single API call per request (or batched calls for large documents)
- Use Haiku model for speed and cost efficiency
- Have simple input/output patterns
- Load prompts via prompt_loader.get_prompt_config()

Import Pattern:
Services are NOT imported at module level to avoid circular imports.
Import directly from the specific module:
    from app.services.ai_services.memory_service import memory_service
    from app.services.ai_services.image_service import image_service
    from app.services.ai_services import embedding_service, summary_service
"""
