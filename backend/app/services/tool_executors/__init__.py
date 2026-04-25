"""
Tool Executors - Handle tool call execution for AI services.

Educational Note: This folder contains executors that handle tool calls
from Claude during chat or agent loops. Each executor is responsible for:
- Receiving tool call parameters
- Executing the appropriate action
- Returning results back to the AI

Executors:
- memory_executor: Handles store_memory tool calls (non-blocking, background task)
- source_search_executor: Handles search_sources tool calls (full content or semantic search)
- web_agent_executor: Routes tool calls for web agent (tavily_search, return_search_result)
- studio_signal_executor: Handles studio_signal tool calls (non-blocking, background task)
- studio_audio_executor: Handles audio overview tools (read_source_content, write_script_section)
- email_agent_executor: Handles email template generation (background task)
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
from app.services.tool_executors.memory_executor import memory_executor
from app.services.tool_executors.source_search_executor import source_search_executor
from app.services.tool_executors.web_agent_executor import web_agent_executor
from app.services.tool_executors.studio_signal_executor import studio_signal_executor
# studio_audio_executor moved to app.studio.media.audio.tool (NBB-507);
# re-export preserved as backward-compat shim. NBB-706 owns removal.
from app.studio.media.audio.tool import studio_audio_executor
from app.studio.marketing.email.run import email_agent_executor

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
    "memory_executor",
    "source_search_executor",
    "web_agent_executor",
    "studio_signal_executor",
    "studio_audio_executor",
    "email_agent_executor",
]
