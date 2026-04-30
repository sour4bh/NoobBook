"""
Deep Research Agent - AI agent for comprehensive topic research.

Educational Note: This is an agentic loop that researches a topic by:
1. Searching the web using web_search (server) and tavily_search_advance (client)
2. Writing research segments incrementally to a file
3. Terminating when is_last_segment=true in write_research_to_file

Tool execution is delegated to deep_research_executor following the
standard separation of concerns pattern.
"""

import logging
import uuid
from typing import Dict, Any, List
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
)
from app.sources.analysis.research.tools.binding import bind_research_tools

logger = logging.getLogger(__name__)


class DeepResearchAgent:
    """
    Deep research agent for comprehensive topic exploration.

    Educational Note: Uses incremental file writing pattern:
    - Agent searches for information using web_search + tavily_search_advance
    - Agent writes research in segments using write_research_to_file
    - Each segment is appended to the output file
    - Agent terminates when is_last_segment=true
    """

    AGENT_NAME = "deep_research"
    MAX_ITERATIONS = 15

    def __init__(self):
        """Initialize agent with lazy-loaded config and tools."""
        self._tools = None

    def _load_tools(self) -> tuple:
        """Load agent tools from deep_research category."""
        if self._tools is None:
            self._tools = tool_loader.load_tool_specs_for_agent(self.AGENT_NAME)
        return self._tools

    def research(
        self,
        project_id: str,
        source_id: str,
        topic: str,
        description: str,
        links: List[str] = None,
        output_path: str = ""
    ) -> Dict[str, Any]:
        """
        Run comprehensive research on a topic.

        Educational Note: The research loop:
        1. Agent searches web for information
        2. Agent writes segments to file incrementally
        3. write_research_to_file with is_last_segment=true ends the loop

        Args:
            project_id: The project UUID
            source_id: The source UUID
            topic: The main research topic
            description: Focus areas and questions to answer
            links: Optional list of reference URLs to analyze
            output_path: Path to write research output (required, must be non-empty)

        Returns:
            Dict with success status and research metadata
        """
        if not output_path:
            raise ValueError("output_path is required")

        tools = self._load_tools()

        execution_id = str(uuid.uuid4())
        started_at = datetime.now().isoformat()
        links = links or []

        links_context = "\n".join([f"- {link}" for link in links]) if links else "No specific links provided."
        prompt = render_prompt(
            "deep_research_agent",
            {
                "topic": topic,
                "description": description,
                "links_context": links_context,
            },
            project_id=project_id,
        )
        user_message = prompt.user_message or f"Research this topic: {topic}"

        segments_written = [0]

        logger.info("Starting deep research on: %s (id: %s)", topic, execution_id[:8])

        result = run_with_provider(
            RunRequest(
                provider=prompt.provider,
                model=prompt.model,
                purpose=self.AGENT_NAME,
                system_prompt=prompt.system_prompt,
                messages=[RunMessage(role="user", content=[TextPart(text=user_message)])],
                tools=bind_research_tools(
                    tools,
                    project_id=project_id,
                    output_path=output_path,
                    segments_written=segments_written,
                ),
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
        completed = "write_research_to_file" in result.terminated_by_tools
        final_result = {
            "success": completed,
            "output_path": output_path,
            "segments_written": segments_written[0],
            "iterations": self._iteration_count(result),
            "usage": result.usage.model_dump(mode="json"),
            "completed_at": datetime.now().isoformat(),
        }
        if not completed:
            final_result["error"] = "Research completed without final segment"
        self._save_execution(
            project_id,
            execution_id,
            topic,
            self._execution_messages(result, user_message),
            final_result,
            started_at,
            source_id,
        )
        return final_result

    def _iteration_count(self, result: Any) -> int:
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

    def _save_execution(
        self,
        project_id: str,
        execution_id: str,
        topic: str,
        messages: List[Dict[str, Any]],
        result: Dict[str, Any],
        started_at: str,
        source_id: str
    ) -> None:
        """Save execution log for debugging."""
        if not project_id:
            return

        try:
            from app.chat.message import message_service

            log_data = {
                "execution_id": execution_id,
                "agent": self.AGENT_NAME,
                "topic": topic,
                "source_id": source_id,
                "started_at": started_at,
                "completed_at": datetime.now().isoformat(),
                "result": result,
                "message_count": len(messages)
            }

            message_service.save_agent_log(
                project_id=project_id,
                agent_name=self.AGENT_NAME,
                execution_id=execution_id,
                log_data={**log_data, "messages": messages}
            )
        except Exception as e:
            logger.exception("Error saving execution log")


# Singleton instance
deep_research_agent = DeepResearchAgent()
