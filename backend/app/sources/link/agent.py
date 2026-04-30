"""
Web Agent Service - AI agent for web content extraction and search.

Educational Note: This is a simple agentic loop pattern:
1. Send task to the model with tools (2 server tools + 2 client tools)
2. Loop until 'return_search_result' tool is called
3. Server tools (web_fetch, web_search) - Claude handles execution
4. Client tools (tavily_search) - we execute and send result back
5. Termination tool (return_search_result) - extract input as final result

Tools:
- web_fetch: Server tool - fetches URL content (Claude handles)
- web_search: Server tool - searches web (Claude handles)
- tavily_search: Client tool - Tavily AI search (we execute)
- return_search_result: Termination tool - signals completion
"""

import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.config.prompt import render_prompt
from app.config.tool import tool_loader
from app.agents.runtime import (
    RunLimits,
    RunMessage,
    RunRequest,
    TextPart,
    ToolChoice,
    run_with_provider,
    require_tool_result_payload,
)
from app.sources.link.tools.binding import bind_link_tools

logger = logging.getLogger(__name__)


class WebAgentService:
    """
    Simple web content extraction agent.

    Educational Note: Agent loops are simpler than they seem:
    - Keep calling Claude until a specific tool signals completion
    - Server tools require no action from us
    - Client tools need execution and result sent back
    """

    AGENT_NAME = "web_agent"
    MAX_ITERATIONS = 8

    def __init__(self):
        """Initialize agent with lazy-loaded config and tools."""
        self._tools = None

    def _load_tools(self) -> tuple:
        """
        Load all 4 agent tools.

        Educational Note: We load typed tool specs:
        - provider-hosted web_search
        - 1 client tool (tavily_search) - we execute
        - 1 termination tool (return_search_result) - signals completion
        """
        if self._tools is None:
            self._tools = tool_loader.load_tool_specs_for_agent(self.AGENT_NAME)
        return self._tools

    # =========================================================================
    # Agent Loop - Simple and Clean
    # =========================================================================

    def run(
        self,
        url: str,
        project_id: Optional[str] = None,
        source_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run the agent to extract content from a URL.

        Educational Note: Simple agentic loop:
        1. URL is injected into system_prompt
        2. user_message from config triggers the agent
        3. Loop until return_search_result tool is called
        4. Server tools (web_fetch, web_search) - Claude handles
        5. Client tools (tavily_search) - we execute
        """
        tools = self._load_tools()
        prompt = render_prompt("web_agent", project_id=project_id)

        execution_id = str(uuid.uuid4())
        started_at = datetime.now().isoformat()

        # Inject URL into system prompt
        system_prompt = prompt.system_prompt + f"\n\nURL to extract: {url}"
        user_message = prompt.user_message or "Please run the analysis."

        logger.info("Starting web agent %s", execution_id[:8])

        result = run_with_provider(
            RunRequest(
                provider=prompt.provider,
                model=prompt.model,
                purpose=self.AGENT_NAME,
                system_prompt=system_prompt,
                messages=[
                    RunMessage(role="user", content=[TextPart(text=user_message)])
                ],
                tools=bind_link_tools(tools, project_id=project_id),
                tool_choice=ToolChoice(type="any"),
                limits=RunLimits(
                    max_tool_turns=self.MAX_ITERATIONS,
                    max_output_tokens=prompt.max_tokens,
                    temperature=prompt.temperature,
                ),
                project_id=project_id,
                metadata={"tags": [self.AGENT_NAME]},
            )
        )

        try:
            final_payload = require_tool_result_payload(
                result,
                "return_search_result",
                dict,
            )
        except Exception as exc:
            logger.warning("Web agent completed without return_search_result")
            error_result = {
                "success": False,
                "error_message": str(exc),
                "iterations": self._iteration_count(result),
                "usage": result.usage.model_dump(mode="json"),
            }
            self._save_execution(
                project_id, execution_id, url,
                self._execution_messages(result, user_message),
                error_result, started_at, source_id
            )
            return error_result

        final_result = self._build_result(
            final_payload,
            self._iteration_count(result),
            result.usage.input_tokens,
            result.usage.output_tokens,
        )
        logger.info("Completed in %d iterations", final_result["iterations"])
        self._save_execution(
            project_id, execution_id, url,
            self._execution_messages(result, user_message),
            final_result, started_at, source_id
        )
        return final_result

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _iteration_count(self, result: Any) -> int:
        """Return how many model tool turns the shared runtime completed."""
        assistant_turns = [
            message
            for message in result.generated_messages
            if getattr(message, "role", None) == "assistant"
        ]
        return len(assistant_turns) or 1

    def _execution_messages(
        self,
        result: Any,
        user_message: str,
    ) -> List[Dict[str, Any]]:
        """Return a debug transcript from runtime-generated messages."""
        messages: List[Dict[str, Any]] = [{"role": "user", "content": user_message}]
        for message in result.generated_messages:
            messages.append(
                {
                    "role": "user" if message.role == "tool" else message.role,
                    "content": [
                        part.model_dump(mode="json")
                        for part in message.content
                    ],
                }
            )
        return messages

    def _build_result(
        self,
        tool_input: Dict[str, Any],
        iterations: int,
        input_tokens: int,
        output_tokens: int
    ) -> Dict[str, Any]:
        """
        Build the final result from return_search_result tool input.

        Educational Note: The termination tool's input IS the result.
        We just add metadata (iterations, token usage, timestamp).
        """
        return {
            "success": tool_input.get("success", False),
            "title": tool_input.get("title", ""),
            "url": tool_input.get("url", ""),
            "content": tool_input.get("content", ""),
            "summary": tool_input.get("summary", ""),
            "content_type": tool_input.get("content_type", "other"),
            "source_urls": tool_input.get("source_urls", []),
            "error_message": tool_input.get("error_message"),
            "iterations": iterations,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            "extracted_at": datetime.now().isoformat()
        }

    def _save_execution(
        self,
        project_id: Optional[str],
        execution_id: str,
        url: str,
        messages: List[Dict[str, Any]],
        result: Dict[str, Any],
        started_at: str,
        source_id: Optional[str] = None
    ) -> None:
        """Save execution log using message_service."""
        if not project_id:
            return

        from app.chat.message import message_service

        message_service.save_agent_execution(
            project_id=project_id,
            agent_name=self.AGENT_NAME,
            execution_id=execution_id,
            task=f"Extract content from: {url}",
            messages=messages,
            result=result,
            started_at=started_at,
            metadata={"source_id": source_id, "url": url}
        )


# Singleton instance
web_agent_service = WebAgentService()
