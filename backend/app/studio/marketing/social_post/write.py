"""
Social Posts Service - Generates social media posts with platform-specific images and copy.

Educational Note: This service implements a two-step AI pipeline:
1. Claude generates platform-specific copy and image prompts
2. Google Gemini generates images with correct aspect ratios for each platform

Platforms:
- LinkedIn: 16:9 (professional, landscape)
- Instagram/Facebook: 1:1 (square, engaging)
- Twitter/X: 16:9 (landscape, casual)

All images are stored in Supabase Storage.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.agents.runtime import (
    LocalToolSpec,
    RunLimits,
    RunMessage,
    RunRequest,
    TextPart,
    ToolChoice,
    bind_local_tools,
    echo_input,
    require_tool_result_payload,
    run_with_provider,
)
from app.providers.google.imagen import imagen_service
from app.providers.supabase import storage_service
import app.studio.jobs.store as studio_index_service
from app.config.prompt import render_prompt
from app.config.brand import brand_context_loader


logger = logging.getLogger(__name__)


# Platform to Gemini aspect ratio mapping
PLATFORM_ASPECT_RATIOS = {
    "linkedin": "16:9",      # Professional landscape (1200x627 -> 16:9 is closest)
    "instagram": "1:1",      # Square for feed posts
    "twitter": "16:9",       # Landscape for engagement
}


class SocialPostPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    platform: str = ""
    text: str = Field(default="", alias="copy")
    hashtags: list[str] = Field(default_factory=list)
    aspect_ratio: Optional[str] = None
    image_prompt: str = ""


class SocialPostResult(BaseModel):
    posts: list[SocialPostPayload] = Field(default_factory=list)
    topic_summary: str = ""


_SOCIAL_POSTS_TOOL = LocalToolSpec(
    name="submit_social_posts",
    description="Return the final platform-specific social post copy and image prompts.",
    input_model=SocialPostResult,
)


class SocialPostWriter:
    """
    Service for generating social media posts with images.

    Educational Note: This service orchestrates the full pipeline:
    1. Claude generates platform-specific copy and image prompts
    2. Gemini generates images with appropriate aspect ratios
    """

    def __init__(self):
        """Initialize service with lazy-loaded config."""
        pass

    def generate_social_posts(
        self,
        project_id: str,
        job_id: str,
        topic: str,
        direction: str = "",
        platforms: List[str] | None = None,
        logo_image_bytes: Optional[bytes] = None,
        logo_mime_type: str = "image/png",
        user_id: Optional[str] = None,
        edit_instructions: Optional[str] = None,
        previous_posts: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Generate social media posts for selected platforms.

        Educational Note: This is the main orchestrator that:
        1. Uses Claude to generate copy + image prompts per platform
        2. Uses Gemini to generate images with correct aspect ratios
        3. Updates job status throughout

        Args:
            project_id: The project UUID
            job_id: The job ID for status tracking
            topic: The topic/content to create posts about
            direction: Additional context/direction from the user
            platforms: List of platforms to generate for (default: all 3)
            logo_image_bytes: Optional brand logo/icon bytes to incorporate in images
            logo_mime_type: MIME type of the logo image

        Returns:
            Dict with success status, posts data, and metadata
        """
        if platforms is None:
            platforms = ["linkedin", "instagram", "twitter"]
        started_at = datetime.now()

        # Update job to processing
        studio_index_service.update_social_post_job(
            project_id, job_id,
            status="processing",
            progress="Generating platform-specific content...",
            started_at=datetime.now().isoformat()
        )

        # Step 1: Generate copy and image prompts with Claude
        content_result = self._generate_content(
            project_id=project_id,
            topic=topic,
            direction=direction,
            job_id=job_id,
            platforms=platforms,
            has_logo=logo_image_bytes is not None,
            user_id=user_id,
            edit_instructions=edit_instructions,
            previous_posts=previous_posts
        )

        if not content_result.get("success"):
            studio_index_service.update_social_post_job(
                project_id, job_id,
                status="error",
                error=content_result.get("error", "Failed to generate content"),
                completed_at=datetime.now().isoformat()
            )
            return content_result

        posts_data = content_result.get("posts", [])
        topic_summary = content_result.get("topic_summary", "")

        # Safety filter: only keep posts for requested platforms
        posts_data = [p for p in posts_data if p.get("platform", "").lower() in platforms]

        # Update progress
        studio_index_service.update_social_post_job(
            project_id, job_id,
            progress="Generating images..."
        )

        # Step 2: Generate images for each platform and upload to Supabase
        all_posts = []

        for i, post_data in enumerate(posts_data):
            platform = post_data.get("platform", f"platform_{i+1}")
            image_prompt = post_data.get("image_prompt", "")
            aspect_ratio = PLATFORM_ASPECT_RATIOS.get(platform, "1:1")

            if not image_prompt:
                continue

            # Update progress
            studio_index_service.update_social_post_job(
                project_id, job_id,
                progress=f"Generating {platform} image ({i+1}/{len(posts_data)})..."
            )

            post_info = {
                "platform": platform,
                "copy": post_data.get("copy", ""),
                "hashtags": post_data.get("hashtags", []),
                "aspect_ratio": post_data.get("aspect_ratio", aspect_ratio),
                "image_prompt": image_prompt,
                "image": None,
                "image_url": None,
                "storage_path": None
            }

            # Generate image — use multimodal method if logo is available
            if logo_image_bytes:
                enhanced_prompt = (
                    "Create a social media post image that naturally incorporates "
                    "the provided brand logo/icon into the design. " + image_prompt
                )
                result = imagen_service.generate_image_with_reference(
                    prompt=enhanced_prompt,
                    reference_image_bytes=logo_image_bytes,
                    reference_mime_type=logo_mime_type,
                    filename_prefix=f"social_{job_id[:8]}_{platform}",
                    aspect_ratio=aspect_ratio,
                    project_id=project_id
                )
            else:
                result = imagen_service.generate_image_bytes(
                    prompt=image_prompt,
                    filename_prefix=f"social_{job_id[:8]}_{platform}",
                    aspect_ratio=aspect_ratio,
                    project_id=project_id
                )

            if result.get("success"):
                filename = result["filename"]
                image_bytes = result["image_bytes"]
                content_type = result["content_type"]

                # Upload to Supabase Storage
                storage_path = storage_service.upload_studio_binary(
                    project_id=project_id,
                    job_type="social_posts",
                    job_id=job_id,
                    filename=filename,
                    file_data=image_bytes,
                    content_type=content_type
                )

                if storage_path:
                    # Use backend API path instead of Supabase internal URL
                    # (Supabase runs on Docker-internal hostname, not accessible from browser)
                    api_path = f"/api/v1/projects/{project_id}/studio/social/{job_id}/{filename}"
                    post_info["image"] = {"filename": filename}
                    post_info["image_url"] = api_path
                    post_info["storage_path"] = storage_path

            all_posts.append(post_info)

        if not all_posts:
            studio_index_service.update_social_post_job(
                project_id, job_id,
                status="error",
                error="No posts were generated",
                completed_at=datetime.now().isoformat()
            )
            return {
                "success": False,
                "error": "No posts were generated"
            }

        # Count successful image generations
        posts_with_images = [p for p in all_posts if p.get("image")]

        # Step 3: Update job as complete
        duration = (datetime.now() - started_at).total_seconds()

        studio_index_service.update_social_post_job(
            project_id, job_id,
            status="ready",
            progress="Complete",
            posts=all_posts,
            topic_summary=topic_summary,
            post_count=len(all_posts),
            generation_time_seconds=duration,
            completed_at=datetime.now().isoformat()
        )

        logger.info("Generated %s/%s social posts with images in %.1fs", len(posts_with_images), len(all_posts), duration)

        return {
            "success": True,
            "job_id": job_id,
            "topic": topic,
            "posts": all_posts,
            "topic_summary": topic_summary,
            "count": len(all_posts),
            "duration_seconds": duration,
            "usage": content_result.get("usage", {})
        }

    def _generate_content(
        self,
        project_id: str,
        topic: str,
        direction: str,
        job_id: str,
        platforms: List[str] | None = None,
        has_logo: bool = False,
        user_id: Optional[str] = None,
        edit_instructions: Optional[str] = None,
        previous_posts: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Generate social media content using Claude.

        Educational Note: Claude creates platform-specific copy and image prompts
        tailored to each platform's style, tone, and image dimensions.
        When a brand logo is available, Claude is instructed to write image prompts
        that describe incorporating the logo into the design.

        When editing, the previous posts data is provided as context
        so Claude can refine copy, hashtags, and image prompts based on
        the user's edit instructions.
        """
        if platforms is None:
            platforms = ["linkedin", "instagram", "twitter"]

        # Format platform names for the prompt (e.g., "LinkedIn, Instagram, and Twitter")
        platform_display = {
            "linkedin": "LinkedIn",
            "instagram": "Instagram",
            "twitter": "Twitter",
        }
        platform_names = [platform_display.get(p, p) for p in platforms]
        if len(platform_names) > 1:
            platforms_str = ", ".join(platform_names[:-1]) + " and " + platform_names[-1]
        else:
            platforms_str = platform_names[0]

        # Logo context — tells Claude to write prompts that reference the logo
        logo_context = ""
        if has_logo:
            logo_context = (
                "\nNOTE: A brand logo/icon will be provided to the image generator. "
                "Write image prompts that describe incorporating it naturally into "
                "the design — mention logo placement (corner, centered, as part of "
                "the composition) and how design elements should complement it."
            )

        # Edit context — provides previous posts + edit instructions for refinement
        edit_context = ""
        if previous_posts and edit_instructions:
            # Serialize previous posts for Claude to reference
            previous_posts_summary = json.dumps(
                [{
                    "platform": p.get("platform"),
                    "copy": p.get("copy"),
                    "hashtags": p.get("hashtags"),
                    "image_prompt": p.get("image_prompt")
                } for p in previous_posts],
                indent=2
            )
            edit_context = (
                "\n\n=== EDIT MODE ===\n"
                "You are REFINING previously generated social posts. "
                "The user wants changes to the existing content.\n\n"
                f"PREVIOUS POSTS:\n{previous_posts_summary}\n\n"
                f"USER'S EDIT INSTRUCTIONS:\n{edit_instructions}\n\n"
                "Apply the user's requested changes while keeping the rest "
                "intact. You can modify copy, hashtags, AND/OR image prompts "
                "as needed. Return the FULL updated JSON response (not just "
                "the changes).\n"
                "=== END EDIT MODE ==="
            )

        # Load brand context so Claude knows brand name, colors, voice, etc.
        brand_context = brand_context_loader.load_brand_context(
            project_id, "social_post"
        )
        prompt = render_prompt(
            "social_posts",
            {
                "topic": topic,
                "direction": (
                    direction or "Create engaging social media posts for this topic."
                ),
                "platforms": platforms_str,
                "logo_context": logo_context,
            },
            project_id=project_id,
            extra_sections=[brand_context] if brand_context else (),
        )
        user_message = prompt.user_message or ""
        if edit_context:
            user_message += edit_context

        try:
            result = run_with_provider(
                RunRequest(
                    provider=prompt.provider,
                    model=prompt.model,
                    purpose="social_posts",
                    messages=[
                        RunMessage(role="user", content=[TextPart(text=user_message)])
                    ],
                    system_prompt=prompt.system_prompt,
                    tools=bind_local_tools(
                        [_SOCIAL_POSTS_TOOL],
                        {_SOCIAL_POSTS_TOOL.name: echo_input},
                        terminating_tools={_SOCIAL_POSTS_TOOL.name},
                    ),
                    tool_choice=ToolChoice(type="tool", name=_SOCIAL_POSTS_TOOL.name),
                    limits=RunLimits(
                        max_tool_turns=1,
                        max_output_tokens=prompt.max_tokens,
                        temperature=prompt.temperature,
                    ),
                    project_id=project_id,
                )
            )

            payload = require_tool_result_payload(
                result,
                _SOCIAL_POSTS_TOOL.name,
                dict,
            )
            parsed = SocialPostResult.model_validate(payload)

            return {
                "success": True,
                "posts": [
                    post.model_dump(mode="json", by_alias=True)
                    for post in parsed.posts
                ],
                "topic_summary": parsed.topic_summary,
                "usage": result.usage.model_dump(mode="json"),
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to generate content: {str(e)}"
            }


# Singleton instance
social_posts_service = SocialPostWriter()
