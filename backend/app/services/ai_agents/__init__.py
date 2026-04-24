"""
AI Agents - Complex AI agents with agentic loops.

Educational Note: This folder contains AI agents that use tool loops
and multiple API calls to complete complex tasks. Unlike ai_services
(single API call), these agents iterate until a termination condition.

Agents:
- web_agent_service: Extracts content from URLs using web tools
  - Uses agentic loop with MAX_ITERATIONS limit
  - Tools: web_fetch, web_search, tavily_search, return_search_result
  - Saves execution logs for debugging

- email_agent_service: Generates HTML email templates
  - Uses agentic loop with MAX_ITERATIONS limit (15)
  - Tools: plan_email_template, generate_email_image, write_email_code
  - Orchestrates planning → image generation → HTML code writing

- website_agent_service: moved to app/studio/design/website/build.py (NBB-503)
- blog_agent_service: moved to app/studio/documents/blog/write.py (NBB-504)
- business_report_agent_service: moved to app/studio/documents/business_report/write.py (NBB-504)
- presentation_agent_service: moved to app/studio/documents/presentation/compose.py (NBB-504)
- prd_agent_service: moved to app/studio/documents/prd/write.py (NBB-504)

Key patterns:
- Agent loop with iteration limit
- Tool executor for routing tool calls
- Termination tool to signal completion
- Execution logging for debugging
"""

from app.services.ai_agents.web_agent_service import web_agent_service
from app.services.ai_agents.email_agent_service import email_agent_service
# website_agent_service moved to app.studio.design.website.build (NBB-503);
# blog_agent_service moved to app.studio.documents.blog.write (NBB-504);
# business_report_agent_service moved to app.studio.documents.business_report.write (NBB-504);
# presentation_agent_service moved to app.studio.documents.presentation.compose (NBB-504);
# prd_agent_service moved to app.studio.documents.prd.write (NBB-504);
# consumers import the singleton directly from the new home.
from app.services.ai_agents.wireframe_agent_service import wireframe_agent_service

__all__ = [
    "web_agent_service",
    "email_agent_service",
    "wireframe_agent_service",
]
