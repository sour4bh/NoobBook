"""
Presentation Agent Service - AI agent for generating PowerPoint presentations.

Orchestrates the presentation generation workflow:
1. Agent plans the presentation structure (plan_presentation tool)
2. Agent creates base-styles.css with brand colors (create_base_styles tool)
3. Agent creates individual slides as HTML files (create_slide tool - multiple calls)
4. Agent finalizes when complete (finalize_presentation - termination tool)

After generation:
- Playwright captures screenshots of each slide (1920x1080)
- python-pptx stitches screenshots into a PPTX file
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
from app.config.brand import brand_context_loader
from app.sources.content import get_source_content
import app.studio.jobs.store as studio_index_service
from app.studio.documents.presentation.tools.binding import bind_presentation_tools

logger = logging.getLogger(__name__)


class PresentationComposer:
    """Presentation generation agent - orchestration only."""

    AGENT_NAME = "presentation_agent"
    MAX_ITERATIONS = 40  # More iterations for presentations with many slides

    def __init__(self):
        self._tools = None

    def _load_tools(self) -> List[Dict[str, Any]]:
        if self._tools is None:
            self._tools = list(tool_loader.load_tool_specs_for_agent(self.AGENT_NAME))
        return self._tools

    def generate_presentation(
        self,
        project_id: str,
        source_id: str,
        job_id: str,
        direction: str = "",
        edit_instructions: Optional[str] = None,
        previous_markdown: Optional[str] = None,
        previous_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run the agent to generate a presentation."""
        tools = self._load_tools()

        execution_id = str(uuid.uuid4())
        started_at = datetime.now().isoformat()

        # Update job status
        studio_index_service.update_presentation_job(
            project_id, job_id,
            status="processing",
            status_message="Starting presentation generation...",
            started_at=started_at
        )

        # Get source content — skip in edit mode since previous presentation already encodes it
        if previous_markdown:
            source_content = "Editing a previous presentation — see the PREVIOUS PRESENTATION section below."
        else:
            source_content = get_source_content(project_id, source_id, max_chars=20000)

        # Load brand context if configured for presentation feature
        brand_context = brand_context_loader.load_brand_context(project_id, "presentation")
        prompt = render_prompt(
            "presentation_agent",
            {"source_content": source_content, "direction": direction},
            project_id=project_id,
            extra_sections=[brand_context] if brand_context else (),
        )
        effective_direction = (
            direction
            if direction
            else str(prompt.metadata.get("default_direction") or "")
        )
        prompt = render_prompt(
            "presentation_agent",
            {"source_content": source_content, "direction": effective_direction},
            project_id=project_id,
            extra_sections=[brand_context] if brand_context else (),
        )
        user_message = prompt.user_message or ""

        # Edit mode: append previous presentation content + edit instructions to user message
        if previous_markdown:
            edit_context = (
                f"\n\n=== PREVIOUS PRESENTATION (refine this based on the edit instructions) ===\n"
                f"Previous Title: {previous_title or 'Untitled'}\n\n"
                f"{previous_markdown}\n"
                f"=== END PREVIOUS PRESENTATION ===\n\n"
                f"EDIT INSTRUCTIONS: {edit_instructions or 'No specific edits requested — improve as you see fit.'}\n\n"
                f"Use the previous presentation as your baseline. Apply the edit instructions "
                f"to refine it. Keep elements the user didn't ask to change."
            )
            user_message += edit_context
        elif edit_instructions:
            user_message += f"\n\nADDITIONAL INSTRUCTIONS: {edit_instructions}"

        created_files = []  # Track created files
        slides_info = []  # Track slide metadata

        logger.info("Starting presentation agent job %s", job_id[:8])

        result = run_with_provider(
            RunRequest(
                provider=prompt.provider,
                model=prompt.model,
                purpose=self.AGENT_NAME,
                system_prompt=prompt.system_prompt,
                messages=[RunMessage(role="user", content=[TextPart(text=user_message)])],
                tools=bind_presentation_tools(
                    tools,
                    project_id=project_id,
                    job_id=job_id,
                    source_id=source_id,
                    created_files=created_files,
                    slides_info=slides_info,
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
            final_result["usage"] = result.usage.model_dump(mode="json")
            logger.info("Completed in %d iterations", iterations)
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

        logger.warning("Presentation agent completed without finalize_presentation")
        error_result = {
            "success": False,
            "error_message": "Agent completed without finalizing the presentation",
            "iterations": self._iteration_count(result),
            "usage": result.usage.model_dump(mode="json"),
        }

        studio_index_service.update_presentation_job(
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
            if tool_result.name == "finalize_presentation" and isinstance(tool_result.content, dict):
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
        source_id: str
    ) -> None:
        """Save execution log for debugging."""
        from app.chat.message import message_service

        message_service.save_agent_execution(
            project_id=project_id,
            agent_name=self.AGENT_NAME,
            execution_id=execution_id,
            task=f"Generate presentation (job: {job_id[:8]})",
            messages=messages,
            result=result,
            started_at=started_at,
            metadata={"source_id": source_id, "job_id": job_id}
        )


# Singleton instance
presentation_agent_service = PresentationComposer()
