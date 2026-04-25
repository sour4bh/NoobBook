"""
Tool Executors - Legacy migration source for chat-invoked tool executors.

Educational Note: This package was the original home for tool-call executors
that fire during Claude chat or agent loops. The contents have been migrated
to domain-owned modules; this `__init__.py` keeps a small set of compatibility
re-exports while consumers move to direct imports.

Executors:
- studio_audio_executor: Handles audio overview tools (read_source_content, write_script_section)
- email_agent_executor: Handles email template generation (background task)
- memory_executor: moved to app/chat/memory/store.py (NBB-303)
- source_search_executor: moved to app/sources/search.py (NBB-303)
- studio_signal_executor: moved to app/studio/signal.py (NBB-303)
- web_agent_executor: moved to app/sources/link/run.py (NBB-303)
- deep_research_executor: moved to app/sources/analysis/research/tool.py (NBB-403)
- csv_analyzer_agent_executor: moved to app/sources/analysis/csv/entry.py (NBB-403)
- database_analyzer_agent_executor: moved to app/sources/analysis/database/entry.py (NBB-403)
- freshdesk_analyzer_agent_executor: moved to app/sources/analysis/freshdesk/entry.py (NBB-403)
- website_agent_executor: moved to app/studio/design/website/run.py (NBB-503)
- blog_agent_executor: moved to app/studio/documents/blog/run.py (NBB-504)
- business_report_agent_executor: moved to app/studio/documents/business_report/run.py (NBB-504)
- presentation_agent_executor: moved to app/studio/documents/presentation/run.py (NBB-504)

Note: Knowledge base integrations (Jira, Notion, GitHub) are handled directly by
knowledge_base_service without separate executors.
"""
# studio_audio_executor moved to app.studio.media.audio.tool (NBB-507);
# re-export preserved as backward-compat shim. NBB-706 owns removal.
from app.studio.media.audio.tool import studio_audio_executor
from app.studio.marketing.email.run import email_agent_executor

# memory_executor moved to app.chat.memory.store (NBB-303);
# source_search_executor moved to app.sources.search (NBB-303);
# studio_signal_executor moved to app.studio.signal (NBB-303);
# web_agent_executor moved to app.sources.link.run (NBB-303);
# website_agent_executor moved to app.studio.design.website.run (NBB-503);
# blog_agent_executor moved to app.studio.documents.blog.run (NBB-504);
# business_report_agent_executor moved to app.studio.documents.business_report.run (NBB-504);
# presentation_agent_executor moved to app.studio.documents.presentation.run (NBB-504);
# component_agent_executor moved to app.studio.design.component.run (NBB-506);
# csv_analyzer_agent_executor / database_analyzer_agent_executor /
# freshdesk_analyzer_agent_executor / deep_research_executor moved to
# app/sources/analysis/<feature>/ (NBB-403);
# consumers import the singleton or entry module directly from the new home.

__all__ = [
    "studio_audio_executor",
    "email_agent_executor",
]
