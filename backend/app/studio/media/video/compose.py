"""
Video prompt generation.

Takes source content + user direction, uses the selected model to craft an optimized
prompt for video generation (Google Veo 2.0). Single API call, no loop.

Module-level form: the previous `VideoPromptService` class held no state;
NBB-706 collapses it into module functions and moves the module under
its real owner (`studio/media/video/`).
"""
import logging
from typing import Any, Dict, List, Optional

from app.agents.runtime import RunLimits, RunMessage, RunRequest, TextPart, run_with_provider
from app.config.prompt import render_prompt
from app.providers.supabase import storage_service

logger = logging.getLogger(__name__)


def generate_video_prompt(
    project_id: str,
    source_id: str,
    direction: str = "",
    edit_instructions: Optional[str] = None,
    previous_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate an optimized video prompt from source content."""
    logger.info("Generating video prompt for source %s", source_id[:8])

    prompt = render_prompt("video", project_id=project_id)
    source_content = _get_source_content(project_id, source_id)

    if edit_instructions and previous_prompt:
        user_message = f"""You previously generated this video prompt:

=== PREVIOUS PROMPT ===
{previous_prompt}
=== END PREVIOUS PROMPT ===

The user wants to edit it with these instructions: {edit_instructions}

Here is the original source content for reference:

=== SOURCE CONTENT ===
{source_content}
=== END SOURCE ===

Generate a refined video prompt (2-4 sentences) that applies the edit instructions to the previous prompt. Keep what works and change what the user asked for. Include specific visual details, camera movements, lighting, and mood. Remember: the video will be 5-8 seconds, so keep it focused on a single scene or smooth transition."""
    else:
        user_message = f"""Create a detailed video prompt based on this content:

=== SOURCE CONTENT ===
{source_content}
=== END SOURCE ===

User Direction: {direction if direction else 'Create an engaging video that captures the essence of this content.'}

Generate a clear, vivid video prompt (2-4 sentences) that describes what should be in the video. Include specific visual details, camera movements, lighting, and mood. Remember: the video will be 5-8 seconds, so keep it focused on a single scene or smooth transition."""

    try:
        result = run_with_provider(
            RunRequest(
                provider=prompt.provider,
                model=prompt.model,
                purpose="video_prompt",
                messages=[RunMessage(role="user", content=[TextPart(text=user_message)])],
                system_prompt=prompt.system_prompt,
                limits=RunLimits(
                    max_output_tokens=prompt.max_tokens,
                    temperature=prompt.temperature,
                ),
                project_id=project_id,
            )
        )
        prompt_text = result.text
        if not prompt_text:
            return {"success": False, "error": "No prompt generated from Claude"}
        prompt_text = prompt_text.strip().strip("\"").strip("'")
        return {
            "success": True,
            "prompt": prompt_text,
            "usage": result.usage.model_dump(mode="json"),
        }
    except Exception as exc:
        logger.exception("Error generating video prompt")
        return {"success": False, "error": str(exc)}


def _get_source_content(project_id: str, source_id: str) -> str:
    """Sample chunks for large sources; use full content for small ones."""
    try:
        from app.sources.catalog import source_service

        source = source_service.get_source(project_id, source_id)
        if not source:
            return "Error: Source not found"

        full_content = storage_service.download_processed_file(project_id, source_id)
        if not full_content:
            return f"Source: {source.get('name', 'Unknown')}\n(Content not yet processed)"

        if len(full_content) < 10000:
            return full_content

        chunks = storage_service.list_source_chunks(project_id, source_id)
        if not chunks:
            return full_content[:10000] + "\n\n[Content truncated...]"

        max_chunks = 6
        total_chunks = len(chunks)
        if total_chunks <= max_chunks:
            selected_indices: List[int] = list(range(total_chunks))
        else:
            step = total_chunks / max_chunks
            selected_indices = [int(i * step) for i in range(max_chunks)]

        sampled_content: List[str] = []
        for idx in selected_indices:
            if idx < total_chunks:
                chunk_text = chunks[idx].get("text", "")
                sampled_content.append(chunk_text)
        return "\n\n".join(sampled_content)
    except Exception as exc:
        logger.exception("Error getting source content")
        return f"Error loading source content: {exc}"
