"""
Freshdesk Analyzer Agent - Agentic loop for analyzing Freshdesk ticket data.

Educational Note: Follows the same pattern as database_analyzer_agent.py.
Claude iterates with tools (schema_info, query_runner) until it calls
return_ticket_analysis to terminate with structured output.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.config.prompt import render_prompt
from app.config.tool import tool_loader
from app.agents.runtime import (
    RunLimits,
    RunMessage,
    RunRequest,
    TextPart,
    ToolChoice,
    run_with_provider,
)
from app.sources.analysis.freshdesk.tools.binding import bind_freshdesk_tools
from app.sources.analysis.freshdesk.tool import freshdesk_executor

logger = logging.getLogger(__name__)


class FreshdeskAnalyzerAgent:
    AGENT_NAME = "freshdesk_analyzer_agent"
    MAX_ITERATIONS = 15
    TERMINATION_TOOL = "return_ticket_analysis"

    def __init__(self):
        self._tools = None

    def _load_tools(self) -> List[Dict[str, Any]]:
        if self._tools is None:
            self._tools = list(tool_loader.load_tool_specs_for_agent("freshdesk_agent"))
        return self._tools

    def run(self, project_id: str, source_id: str, query: str, chat_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Run the Freshdesk analysis agentic loop.
        Always closes the DB connection on exit to prevent leaks."""
        execution_id = str(uuid.uuid4())[:8]
        logger.info("[FreshdeskAgent:%s] Starting analysis for source %s", execution_id, source_id)

        # Pre-flight: verify DB connection
        if not freshdesk_executor.validate_connection():
            return {"success": False, "error": "Cannot connect to database"}

        prompt = render_prompt(self.AGENT_NAME, project_id=project_id)
        tools = self._load_tools()

        # Ground the agent in today's date so "yesterday", "last 7 days", etc.
        # map to concrete timestamp filters on ticket_created_at.
        from datetime import date
        today_line = f"Today's date: {date.today().isoformat()}"
        system_prompt = f"{today_line}\n\n{prompt.system_prompt}"

        user_message = f"Freshdesk source ID: {source_id}\n\nUser question: {query}"
        all_queries: List[str] = []

        try:
            result = run_with_provider(
                RunRequest(
                    provider=prompt.provider,
                    model=prompt.model,
                    purpose=self.AGENT_NAME,
                    system_prompt=system_prompt,
                    messages=[RunMessage(role="user", content=[TextPart(text=user_message)])],
                    tools=bind_freshdesk_tools(
                        tools,
                        project_id=project_id,
                        source_id=source_id,
                        executed_queries=all_queries,
                    ),
                    tool_choice=ToolChoice(type="any"),
                    limits=RunLimits(
                        max_tool_turns=self.MAX_ITERATIONS,
                        max_output_tokens=prompt.max_tokens,
                        temperature=prompt.temperature,
                    ),
                    project_id=project_id,
                    chat_id=chat_id,
                    user_id=user_id,
                    metadata={"tags": ["query"]},
                )
            )
            termination_result = self._terminating_tool_result(result)
            iterations = self._iteration_count(result)
            if termination_result is not None:
                return {
                    "success": True,
                    "content": termination_result.get("summary", ""),
                    "summary": termination_result.get("summary", ""),
                    "findings": termination_result.get("findings", []),
                    "recommendations": termination_result.get("recommendations", []),
                    "sql_queries": all_queries,
                    "iterations": iterations,
                    "usage": result.usage.model_dump(mode="json"),
                }
            text = result.text
            return {
                "success": bool(text),
                "content": text,
                "summary": text,
                "findings": [],
                "recommendations": [],
                "sql_queries": all_queries,
                "iterations": iterations,
                "usage": result.usage.model_dump(mode="json"),
            }
        finally:
            freshdesk_executor.close()

    def _terminating_tool_result(self, result: Any) -> Optional[Dict[str, Any]]:
        for tool_result in reversed(result.tool_results):
            if tool_result.name == self.TERMINATION_TOOL and isinstance(tool_result.content, dict):
                return tool_result.content
        return None

    def _iteration_count(self, result: Any) -> int:
        assistant_turns = [
            message
            for message in result.generated_messages
            if getattr(message, "role", None) == "assistant"
        ]
        return len(assistant_turns) or 1


freshdesk_analyzer_agent = FreshdeskAnalyzerAgent()
