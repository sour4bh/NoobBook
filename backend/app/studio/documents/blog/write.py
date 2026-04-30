"""
Blog Agent Service - AI agent for generating comprehensive blog posts.

Orchestrates the blog generation workflow:
1. Agent plans the blog structure (plan_blog_post)
2. Agent generates images (generate_blog_image)
3. Agent writes the final markdown (write_blog_post - termination)
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
from app.studio.documents.blog.tools.binding import bind_blog_tools

logger = logging.getLogger(__name__)


class BlogWriter:
    """Blog post generation agent - orchestration only."""

    AGENT_NAME = "blog_agent"
    MAX_ITERATIONS = 20

    def __init__(self):
        self._tools = None

    def _load_tools(self) -> List[Dict[str, Any]]:
        if self._tools is None:
            self._tools = list(tool_loader.load_tool_specs_for_agent(self.AGENT_NAME))
        return self._tools

    def generate_blog_post(
        self,
        project_id: str,
        source_id: Optional[str],
        job_id: str,
        direction: str = "",
        target_keyword: str = "",
        blog_type: str = "how_to_guide",
        logo_image_bytes: Optional[bytes] = None,
        logo_mime_type: str = "image/png",
        user_id: Optional[str] = None,
        edit_instructions: Optional[str] = None,
        previous_markdown: Optional[str] = None,
        previous_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run the agent to generate a blog post."""
        tools = self._load_tools()

        execution_id = str(uuid.uuid4())
        started_at = datetime.now().isoformat()

        # Update job status
        studio_index_service.update_blog_job(
            project_id, job_id,
            status="processing",
            status_message="Starting blog post generation..."
        )

        # Get source content — skip in edit mode since previous blog already encodes it
        if previous_markdown:
            source_content = "Editing a previous blog post — see the PREVIOUS BLOG POST section below."
        else:
            source_content = get_source_content(project_id, source_id) if source_id else "No source document provided. Use the direction below as the basis for your blog post."
        brand_context = brand_context_loader.load_brand_context(
            project_id, "blog"
        )
        prompt = render_prompt(
            "blog_agent",
            {
                "source_content": source_content,
                "target_keyword": (
                    target_keyword or "Use your best judgment based on the content"
                ),
                "blog_type_display": blog_type.replace("_", " ").title(),
                "direction": (
                    direction
                    or "No specific direction provided - use your best judgment based on the content."
                ),
            },
            project_id=project_id,
            extra_sections=[brand_context] if brand_context else (),
        )
        blog_types = prompt.metadata.get("blog_types", {})
        blog_type_display = blog_types.get(blog_type, blog_type.replace("_", " ").title())

        prompt = render_prompt(
            "blog_agent",
            {
                "source_content": source_content,
                "target_keyword": (
                    target_keyword or "Use your best judgment based on the content"
                ),
                "blog_type_display": blog_type_display,
                "direction": (
                    direction
                    or "No specific direction provided - use your best judgment based on the content."
                ),
            },
            project_id=project_id,
            extra_sections=[brand_context] if brand_context else (),
        )
        user_message = prompt.user_message or ""

        # Edit mode: append previous blog content + edit instructions to user message
        if previous_markdown:
            edit_context = (
                f"\n\n=== PREVIOUS BLOG POST (refine this based on the edit instructions) ===\n"
                f"Previous Title: {previous_title or 'Untitled'}\n\n"
                f"{previous_markdown}\n"
                f"=== END PREVIOUS BLOG POST ===\n\n"
                f"EDIT INSTRUCTIONS: {edit_instructions or 'No specific edits requested — improve the post as you see fit.'}\n\n"
                f"Use the previous blog post as your baseline. Apply the edit instructions "
                f"to refine it. Keep elements the user didn't ask to change."
            )
            user_message += edit_context
        elif edit_instructions:
            # No parent content but user provided edit instructions — treat as additional guidance
            user_message += f"\n\nADDITIONAL INSTRUCTIONS: {edit_instructions}"

        # Only use logo if brand is enabled (tied to brand context being non-empty)
        effective_logo = logo_image_bytes if brand_context else None
        if effective_logo:
            logo_note = (
                "\n\nNOTE: A brand logo/icon is available and will be passed to "
                "the image generator. When calling generate_blog_image, write image "
                "prompts that describe incorporating the logo naturally into the design."
            )
            prompt = prompt.model_copy(
                update={"system_prompt": f"{prompt.system_prompt}{logo_note}"}
            )

        generated_images = []

        logger.info("Starting blog agent job %s", job_id[:8])

        context = {
            "project_id": project_id,
            "job_id": job_id,
            "source_id": source_id,
            "generated_images": generated_images,
            "iterations": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "target_keyword": target_keyword,
            "blog_type": blog_type,
            "logo_image_bytes": effective_logo,
            "logo_mime_type": logo_mime_type,
        }
        result = run_with_provider(
            RunRequest(
                provider=prompt.provider,
                model=prompt.model,
                purpose=self.AGENT_NAME,
                system_prompt=prompt.system_prompt,
                messages=[RunMessage(role="user", content=[TextPart(text=user_message)])],
                tools=bind_blog_tools(tools, context=context),
                tool_choice=ToolChoice(type="any"),
                limits=RunLimits(
                    max_tool_turns=self.MAX_ITERATIONS,
                    max_output_tokens=prompt.max_tokens,
                    temperature=prompt.temperature,
                ),
                project_id=project_id,
                user_id=user_id,
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

        logger.warning("Blog agent completed without write_blog_post")
        error_result = {
            "success": False,
            "error_message": "Agent completed without writing the blog post",
            "iterations": self._iteration_count(result),
            "usage": result.usage.model_dump(mode="json"),
        }

        studio_index_service.update_blog_job(
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
            if tool_result.name == "write_blog_post" and isinstance(tool_result.content, dict):
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
            task=f"Generate blog post (job: {job_id[:8]})",
            messages=messages,
            result=result,
            started_at=started_at,
            metadata={"source_id": source_id, "job_id": job_id}
        )


# Singleton instance
blog_agent_service = BlogWriter()
