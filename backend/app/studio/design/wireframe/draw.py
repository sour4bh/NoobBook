"""
Wireframe Agent Service - AI agent for generating UI/UX wireframes.

Orchestrates the wireframe generation workflow using an agentic loop:
1. Agent plans wireframe sections (plan_wireframe tool)
2. Agent generates elements for each section incrementally (add_wireframe_section tool)
3. Agent finalizes the complete wireframe (finalize_wireframe - termination)

This agentic approach allows for larger wireframes by distributing output
across multiple iterations, avoiding token limit issues.
"""

import logging
import uuid
from typing import Dict, Any, List
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
from app.studio.design.wireframe.tools.binding import bind_wireframe_tools
from app.sources import index

logger = logging.getLogger(__name__)


class WireframeBuilder:
    """Wireframe generation agent - orchestration with agentic loop."""

    AGENT_NAME = "wireframe_agent"
    MAX_ITERATIONS = 15  # Allow enough iterations for complex wireframes

    def __init__(self):
        self._tools = None

    def _load_tools(self) -> List[Dict[str, Any]]:
        if self._tools is None:
            self._tools = list(tool_loader.load_tool_specs_for_agent(self.AGENT_NAME))
        return self._tools

    def generate_wireframe(
        self,
        project_id: str,
        source_id: str = None,
        job_id: str = "",
        direction: str = "Create a wireframe for the main page layout.",
        previous_content: str = None,
        edit_instructions: str = None,
    ) -> Dict[str, Any]:
        """
        Run the agent to generate a wireframe using an agentic loop.

        Args:
            project_id: The project UUID
            source_id: The source UUID
            job_id: The job ID for status tracking
            direction: User's direction for what to wireframe
            previous_content: Previous wireframe description (for edits)
            edit_instructions: Instructions for how to edit the previous wireframe

        Returns:
            Dict with success status, elements, and metadata
        """
        tools = self._load_tools()

        execution_id = str(uuid.uuid4())
        started_at = datetime.now()

        # Update job status
        studio_index_service.update_wireframe_job(
            project_id,
            job_id,
            status="processing",
            progress="Starting wireframe generation...",
            started_at=started_at.isoformat(),
        )

        logger.info("Starting wireframe agent job %s", job_id[:8])

        try:
            # Get source content (if source provided)
            source_content = ""
            source_name = "Direction Only"
            if source_id:
                source = index.get_source_from_index(project_id, source_id)
                if not source:
                    raise ValueError(f"Source {source_id} not found")
                source_name = source.get("name", "Unknown Source")

                studio_index_service.update_wireframe_job(
                    project_id, job_id, progress="Analyzing content..."
                )
                source_content = get_source_content(project_id, source_id, max_chars=15000)

            # Build user message
            # Guard against error messages AND unprocessed sources
            has_valid_content = (source_content
                                and not source_content.startswith("Error")
                                and "not yet processed" not in source_content)
            brand_context = brand_context_loader.load_brand_context(project_id, "infographic")
            if has_valid_content:
                prompt = render_prompt(
                    "wireframe_agent",
                    {"source_content": source_content, "direction": direction},
                    project_id=project_id,
                    extra_sections=[brand_context] if brand_context else (),
                )
                user_message = prompt.user_message or ""
            else:
                # No source — generate from direction alone
                user_message = f"Create a wireframe based on this direction:\n\nDIRECTION:\n{direction}\n\nGenerate a complete wireframe layout using the agentic workflow."
                prompt = render_prompt(
                    "wireframe_agent",
                    {"source_content": "", "direction": direction},
                    project_id=project_id,
                    extra_sections=[brand_context] if brand_context else (),
                )

            # Append edit context if editing a previous wireframe
            if previous_content and edit_instructions:
                edit_context = (
                    f"\n\n=== PREVIOUS WIREFRAME (refine based on edit instructions) ===\n"
                    f"{previous_content}\n"
                    f"=== END PREVIOUS WIREFRAME ===\n\n"
                    f"EDIT INSTRUCTIONS: {edit_instructions}\n\n"
                    f"Use the previous wireframe as baseline. Apply the edits. "
                    f"Keep unchanged elements and layout structure."
                )
                user_message += edit_context

            context: dict[str, Any] = {
                "project_id": project_id,
                "job_id": job_id,
                "source_id": source_id,
                "source_name": source_name,
                "iterations": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "accumulated_elements": [],
                "title": "Wireframe",
                "wireframe_metadata": {
                    "title": "Wireframe",
                    "description": "",
                    "canvas_width": 1200,
                    "canvas_height": 800,
                    "sections": [],
                },
            }
            result = run_with_provider(
                RunRequest(
                    provider=prompt.provider,
                    model=prompt.model,
                    purpose=self.AGENT_NAME,
                    system_prompt=prompt.system_prompt,
                    messages=[
                        RunMessage(role="user", content=[TextPart(text=user_message)])
                    ],
                    tools=bind_wireframe_tools(tools, context=context),
                    tool_choice=ToolChoice(type="any"),
                    limits=RunLimits(
                        max_tool_turns=self.MAX_ITERATIONS,
                        max_output_tokens=prompt.max_tokens,
                        temperature=prompt.temperature,
                    ),
                    project_id=project_id,
                    metadata={"job_id": job_id, "source_id": source_id},
                )
            )

            context["iterations"] = self._iteration_count(result)
            context["input_tokens"] = result.usage.input_tokens
            context["output_tokens"] = result.usage.output_tokens
            accumulated_elements = context.get("accumulated_elements", [])
            wireframe_metadata = context.get("wireframe_metadata", {})
            generation_time = (datetime.now() - started_at).total_seconds()

            if result.terminated_by_tools:
                studio_index_service.update_wireframe_job(
                    project_id,
                    job_id,
                    status="ready",
                    progress="Complete",
                    title=wireframe_metadata.get("title", "Wireframe"),
                    description=wireframe_metadata.get("description", ""),
                    elements=accumulated_elements,
                    canvas_width=wireframe_metadata.get("canvas_width", 1200),
                    canvas_height=wireframe_metadata.get("canvas_height", 800),
                    element_count=len(accumulated_elements),
                    generation_time_seconds=round(generation_time, 1),
                    completed_at=datetime.now().isoformat(),
                )

                final_result = {
                    "success": True,
                    "title": wireframe_metadata.get("title", "Wireframe"),
                    "description": wireframe_metadata.get("description", ""),
                    "elements": accumulated_elements,
                    "element_count": len(accumulated_elements),
                    "source_name": source_name,
                    "generation_time": generation_time,
                    "iterations": context["iterations"],
                    "usage": result.usage.model_dump(mode="json"),
                }

                self._save_execution(
                    project_id,
                    execution_id,
                    job_id,
                    self._execution_messages(result, user_message),
                    final_result,
                    started_at.isoformat(),
                    source_id,
                )

                return final_result

            if accumulated_elements:
                studio_index_service.update_wireframe_job(
                    project_id,
                    job_id,
                    status="ready",
                    progress="Complete (partial)",
                    title=wireframe_metadata.get("title", "Wireframe"),
                    description=wireframe_metadata.get("description", ""),
                    elements=accumulated_elements,
                    canvas_width=wireframe_metadata.get("canvas_width", 1200),
                    canvas_height=wireframe_metadata.get("canvas_height", 800),
                    element_count=len(accumulated_elements),
                    generation_time_seconds=round(generation_time, 1),
                    completed_at=datetime.now().isoformat(),
                )

                partial_result = {
                    "success": True,
                    "title": wireframe_metadata.get("title", "Wireframe"),
                    "description": wireframe_metadata.get("description", ""),
                    "elements": accumulated_elements,
                    "element_count": len(accumulated_elements),
                    "source_name": source_name,
                    "generation_time": generation_time,
                    "iterations": context["iterations"],
                    "partial": True,
                    "usage": result.usage.model_dump(mode="json"),
                }

                self._save_execution(
                    project_id,
                    execution_id,
                    job_id,
                    self._execution_messages(result, user_message),
                    partial_result,
                    started_at.isoformat(),
                    source_id,
                )

                return partial_result

            # No elements at all - error
            error_result = {
                "success": False,
                "error": f"Agent reached maximum iterations ({self.MAX_ITERATIONS}) without generating elements",
                "iterations": context["iterations"],
                "usage": result.usage.model_dump(mode="json"),
            }

            studio_index_service.update_wireframe_job(
                project_id,
                job_id,
                status="error",
                error=error_result["error"],
                completed_at=datetime.now().isoformat(),
            )

            self._save_execution(
                project_id,
                execution_id,
                job_id,
                self._execution_messages(result, user_message),
                error_result,
                started_at.isoformat(),
                source_id,
            )

            return error_result

        except Exception as e:
            logger.exception("Wireframe generation failed")
            studio_index_service.update_wireframe_job(
                project_id,
                job_id,
                status="error",
                error=str(e),
                completed_at=datetime.now().isoformat(),
            )
            return {"success": False, "error": str(e)}

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
        source_id: str,
    ) -> None:
        """Save execution log for debugging."""
        from app.chat.message import message_service

        message_service.save_agent_execution(
            project_id=project_id,
            agent_name=self.AGENT_NAME,
            execution_id=execution_id,
            task=f"Generate wireframe (job: {job_id[:8]})",
            messages=messages,
            result=result,
            started_at=started_at,
            metadata={"source_id": source_id, "job_id": job_id},
        )


# Singleton instance
wireframe_agent_service = WireframeBuilder()
