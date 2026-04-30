"""
Marketing Strategy Agent Service - AI agent for generating Marketing Strategy Documents.

Orchestrates the marketing strategy generation workflow:
1. Agent plans the strategy structure (plan_marketing_strategy tool)
2. Agent writes sections incrementally (write_marketing_section tool)
3. Agent signals completion via is_last_section=true flag
"""

import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.agents.runtime import (
    RunLimits,
    RunMessage,
    RunRequest,
    TextPart,
    ToolChoice,
    run_with_provider,
)
from app.config.prompt import render_prompt
from app.config.tool import tool_loader
from app.sources.content import get_source_content
import app.studio.jobs.store as studio_index_service
from app.studio.marketing.strategy.tools.binding import bind_marketing_strategy_tools

logger = logging.getLogger(__name__)


class MarketingStrategyPlanner:
    """Marketing strategy generation agent - orchestration only."""

    AGENT_NAME = "marketing_strategy_agent"
    MAX_ITERATIONS = 10

    def __init__(self):
        self._tools = None

    def _load_tools(self) -> List[Dict[str, Any]]:
        if self._tools is None:
            self._tools = list(tool_loader.load_tool_specs_for_agent(self.AGENT_NAME))
        return self._tools

    def generate_marketing_strategy(
        self,
        project_id: str,
        source_id: Optional[str],
        job_id: str,
        direction: str = "",
        previous_document: Optional[Dict] = None,
        edit_instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run the agent to generate a marketing strategy document."""
        tools = self._load_tools()

        execution_id = str(uuid.uuid4())
        started_at = datetime.now().isoformat()

        # Update job status
        studio_index_service.update_marketing_strategy_job(
            project_id, job_id,
            status="processing",
            status_message="Starting marketing strategy generation...",
            started_at=started_at
        )

        # Get source content (if source provided)
        source_content = ""
        if source_id:
            source_content = get_source_content(project_id, source_id, max_chars=15000)

        prompt = render_prompt(
            "marketing_strategy_agent",
            {"source_content": source_content, "direction": direction},
            project_id=project_id,
        )
        # Build user message from the typed prompt or direction-only fallback.
        # Guard against error messages AND unprocessed sources (e.g., "Content not yet processed")
        effective_direction = (
            direction
            if direction
            else str(prompt.metadata.get("default_direction") or "")
        )
        has_valid_content = (source_content
                            and not source_content.startswith("Error")
                            and "not yet processed" not in source_content)
        if has_valid_content:
            prompt = render_prompt(
                "marketing_strategy_agent",
                {"source_content": source_content, "direction": effective_direction},
                project_id=project_id,
            )
            user_message = prompt.user_message or ""
        else:
            user_message = f"Create a comprehensive Marketing Strategy Document.\n\nDirection from user: {effective_direction}\n\nPlease create a complete marketing strategy following the workflow:\n1. First, plan the document structure using the plan_marketing_strategy tool\n2. Then write each section one at a time using the write_marketing_section tool\n3. Set is_last_section=true when you write the final section"

        # Edit mode: include previous document for refinement (capped to control token costs)
        if previous_document and edit_instructions:
            prev_markdown = previous_document.get('markdown_content', '')
            if len(prev_markdown) > 15000:
                prev_markdown = prev_markdown[:15000] + "\n\n[... document truncated for context limit ...]"
            edit_context = "\n\n## EDIT MODE — REFINE PREVIOUS DOCUMENT\n"
            edit_context += f"Previous document title: {previous_document.get('document_title', 'N/A')}\n"
            edit_context += f"Previous sections: {previous_document.get('sections_written', 0)}\n"
            edit_context += "\n### PREVIOUS DOCUMENT CONTENT:\n"
            edit_context += prev_markdown
            edit_context += f"\n\n### EDIT INSTRUCTIONS:\n{edit_instructions}\n"
            edit_context += "Rewrite the document applying the edit instructions. Preserve sections and content the user didn't ask to change. Focus modifications on what the edit instructions specify."
            user_message = user_message + edit_context
        elif edit_instructions:
            user_message = user_message + f"\n\nADDITIONAL INSTRUCTIONS: {edit_instructions}"

        sections_written = [0]

        logger.info("Starting marketing strategy agent job %s", job_id[:8])

        result = run_with_provider(
            RunRequest(
                provider=prompt.provider,
                model=prompt.model,
                purpose=self.AGENT_NAME,
                system_prompt=prompt.system_prompt,
                messages=[RunMessage(role="user", content=[TextPart(text=user_message)])],
                tools=bind_marketing_strategy_tools(
                    tools,
                    project_id=project_id,
                    job_id=job_id,
                    source_id=source_id,
                    sections_written=sections_written,
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
        final_result = self._terminating_tool_result(result)
        if final_result is not None:
            iterations = self._iteration_count(result)
            final_result["iterations"] = iterations
            final_result["sections_written"] = sections_written[0]
            final_result["usage"] = result.usage.model_dump(mode="json")
            logger.info(
                "Completed in %d iterations, %d sections",
                iterations,
                sections_written[0],
            )
            self._save_execution(
                project_id,
                execution_id,
                job_id,
                self._execution_messages(result, user_message),
                final_result,
                started_at,
                source_id,
            )
            return final_result

        logger.warning("Marketing strategy agent completed without final section")
        error_result = {
            "success": False,
            "error_message": "Agent completed without finalizing the marketing strategy",
            "iterations": self._iteration_count(result),
            "sections_written": sections_written[0],
            "usage": result.usage.model_dump(mode="json"),
        }

        studio_index_service.update_marketing_strategy_job(
            project_id, job_id,
            status="error",
            error_message=error_result["error_message"]
        )

        self._save_execution(
            project_id, execution_id, job_id,
            self._execution_messages(result, user_message),
            error_result, started_at, source_id
        )

        return error_result

    def _terminating_tool_result(self, result: Any) -> Optional[Dict[str, Any]]:
        for tool_result in reversed(result.tool_results):
            if tool_result.name == "write_marketing_section" and isinstance(tool_result.content, dict):
                return tool_result.content
        return None

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
        job_id: str,
        messages: List[Dict[str, Any]],
        result: Dict[str, Any],
        started_at: str,
        source_id: Optional[str]
    ) -> None:
        """Save execution log for debugging."""
        from app.chat.message import message_service

        message_service.save_agent_execution(
            project_id=project_id,
            agent_name=self.AGENT_NAME,
            execution_id=execution_id,
            task=f"Generate Marketing Strategy (job: {job_id[:8]})",
            messages=messages,
            result=result,
            started_at=started_at,
            metadata={"source_id": source_id, "job_id": job_id}
        )


# Singleton instance
marketing_strategy_agent_service = MarketingStrategyPlanner()
