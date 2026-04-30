"""
Image Service - Manages image processing and content extraction using tool-based approach.

Educational Note: This service extracts comprehensive content from images using Claude's
vision capabilities. It uses a tool-based approach similar to PDF extraction:
- Images are sent as base64-encoded content blocks
- Claude analyzes the image and calls submit_image_extraction tool
- The tool returns structured data about the image content
- Results are saved as text files for use in chat context

Supported formats: JPEG, PNG, GIF, WebP (max 5MB each per API constraint)
"""
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from app.config.tool import tool_loader
from app.config.prompt import render_prompt
from app.config.provider import get_generation_config
from app.base.media import get_media_type
from app.sources.extract.rate import RateLimiter
from app.sources.extract.media import image_part
from app.sources.text import build_processed_output
from app.sources.tokens import count_tokens
from app.background.tasks import task_service
from app.agents.runtime import (
    RunLimits,
    RunMessage,
    RunRequest,
    TextPart,
    ToolChoice,
    bind_local_tools,
    echo_input,
    run_with_provider,
    require_tool_result_payload,
)

logger = logging.getLogger(__name__)


class ImageService:
    """
    Service class for extracting content from images using Claude's vision.

    Educational Note: This service handles image analysis:
    1. Reads image file and encodes to base64
    2. Sends to the model with submit_image_extraction tool
    3. Parses structured response (subject, text, visuals, data, etc.)
    4. Saves combined content as text file for chat context
    """

    def __init__(self):
        """Initialize the image service."""
        self._tool_definition = None

    def _load_tool_definition(self) -> Dict[str, Any]:
        """Load the image extraction tool definition."""
        if self._tool_definition is None:
            self._tool_definition = tool_loader.load_tool_spec("image_tools", "image_extraction")
        return self._tool_definition

    def _parse_tool_response(self, response: Any) -> Dict[str, Any]:
        """
        Parse image extraction tool response from the provider adapter.

        Educational Note: The runtime returns validated tool results;
        this method extracts image-specific fields from the first matching result.
        """
        try:
            inputs = require_tool_result_payload(
                response,
                "submit_image_extraction",
                dict,
            )
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }
        return {
            "success": True,
            "subject": inputs.get("subject", ""),
            "content_type": inputs.get("content_type", "other"),
            "text_content": inputs.get("text_content", "[NO TEXT]"),
            "visual_description": inputs.get("visual_description", ""),
            "colors_and_style": inputs.get("colors_and_style", ""),
            "data_content": inputs.get("data_content", "[NO DATA]"),
            "summary": inputs.get("summary", "")
        }

    def _format_extraction_content(
        self,
        extraction: Dict[str, Any]
    ) -> str:
        """
        Format extracted image data as page content.

        Educational Note: Returns just the content (no header). The header
        and page markers are added by build_processed_output.
        """
        lines = [
            "## Subject",
            extraction.get("subject", ""),
            "",
            "## Text Content",
            extraction.get("text_content", "[NO TEXT]"),
            "",
            "## Visual Description",
            extraction.get("visual_description", ""),
            "",
            "## Colors and Style",
            extraction.get("colors_and_style", ""),
            "",
            "## Data Content",
            extraction.get("data_content", "[NO DATA]"),
            "",
            "## Summary",
            extraction.get("summary", ""),
        ]
        return "\n".join(lines)

    def extract_content_from_image(
        self,
        project_id: str,
        source_id: str,
        image_path: Path
    ) -> Dict[str, Any]:
        """
        Extract content from a single image file.

        Educational Note: This is the main entry point for image processing.
        1. Loads image and encodes to base64
        2. Sends to the model with image content block
        3. Forces tool use for structured extraction
        4. Saves result as text file

        Args:
            project_id: The project UUID
            source_id: The source UUID
            image_path: Path to the image file

        Returns:
            Dict with extraction results
        """
        logger.info("Starting image extraction for source %s", source_id[:8])

        try:
            # Load configurations using centralized loaders
            prompt = render_prompt("image_extraction", project_id=project_id)
            tool_def = self._load_tool_definition()

            generation_config = get_generation_config(
                prompt.provider,
                project_id=project_id,
            )

            # Create rate limiter for this extraction
            requests_per_minute = generation_config["requests_per_minute"]
            rate_limiter = RateLimiter(requests_per_minute)

            media_type = get_media_type(image_path)
            messages = [
                RunMessage(
                    role="user",
                    content=[
                        image_part(
                            filename=image_path.name,
                            media_type=media_type,
                            data=image_path.read_bytes(),
                        ),
                        TextPart(text=prompt.user_message or ""),
                    ],
                )
            ]
            tools = bind_local_tools([tool_def], {tool_def.name: echo_input})

            # Apply rate limiting before API call
            rate_limiter.wait_if_needed()

            result = run_with_provider(
                RunRequest(
                    provider=prompt.provider,
                    model=prompt.model,
                    purpose="image_extraction",
                    messages=messages,
                    system_prompt=prompt.system_prompt,
                    tools=tools,
                    tool_choice=ToolChoice(type="tool", name="submit_image_extraction"),
                    limits=RunLimits(
                        max_tool_turns=1,
                        max_output_tokens=prompt.max_tokens,
                        temperature=prompt.temperature,
                    ),
                    project_id=project_id,
                )
            )

            extraction = self._parse_tool_response(result)

            if not extraction.get("success"):
                raise Exception(extraction.get("error", "Extraction failed"))

            # Build page content (images are single "pages")
            page_content = self._format_extraction_content(extraction)
            pages = [page_content]

            # Calculate character and token counts
            character_count = len(page_content)
            token_count = count_tokens(page_content)

            # Build metadata for IMAGE type
            content_type = extraction.get("content_type", "other")
            metadata = {
                "model_used": prompt.model,
                "content_type": content_type,
                "character_count": character_count,
                "token_count": token_count
            }

            # Use centralized build_processed_output for consistent format
            processed_content = build_processed_output(
                pages=pages,
                source_type="IMAGE",
                source_name=image_path.name,
                metadata=metadata
            )

            logger.info("Image extraction complete: %s", image_path.name)

            # Return processed content for processor to upload to Supabase Storage
            return {
                "success": True,
                "status": "ready",
                "processed_content": processed_content,
                "character_count": character_count,
                "token_count": token_count,
                "content_type": content_type,
                "summary": extraction.get("summary"),
                "token_usage": result.usage.model_dump(mode="json"),
                "model_used": prompt.model,
                "extracted_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.exception("Image extraction failed")
            return {
                "success": False,
                "status": "error",
                "error": str(e)
            }

    def extract_content_from_images_batch(
        self,
        project_id: str,
        source_id: str,
        image_paths: List[Path]
    ) -> Dict[str, Any]:
        """
        Extract content from multiple images in a single source.

        Educational Note: When multiple images are uploaded together,
        we process each one and combine results into a single output file.

        Args:
            project_id: The project UUID
            source_id: The source UUID
            image_paths: List of paths to image files

        Returns:
            Dict with extraction results for all images
        """
        logger.info("Starting batch image extraction for %d images", len(image_paths))

        try:
            # Load configurations using centralized loaders
            prompt = render_prompt("image_extraction", project_id=project_id)
            tool_def = self._load_tool_definition()

            generation_config = get_generation_config(
                prompt.provider,
                project_id=project_id,
            )

            # Create rate limiter for batch processing
            requests_per_minute = generation_config["requests_per_minute"]
            rate_limiter = RateLimiter(requests_per_minute)

            all_extractions = []
            total_input_tokens = 0
            total_output_tokens = 0

            for idx, image_path in enumerate(image_paths, 1):
                if task_service.is_target_cancelled(
                    source_id,
                    owner_project_id=project_id,
                ):
                    raise Exception("Processing cancelled by user")

                media_type = get_media_type(image_path)

                messages = [
                    RunMessage(
                        role="user",
                        content=[
                            image_part(
                                filename=image_path.name,
                                media_type=media_type,
                                data=image_path.read_bytes(),
                            ),
                            TextPart(text=prompt.user_message or ""),
                        ],
                    )
                ]
                tools = bind_local_tools([tool_def], {tool_def.name: echo_input})

                # Apply rate limiting before each API call
                rate_limiter.wait_if_needed()

                result = run_with_provider(
                    RunRequest(
                        provider=prompt.provider,
                        model=prompt.model,
                        purpose="image_extraction",
                        messages=messages,
                        system_prompt=prompt.system_prompt,
                        tools=tools,
                        tool_choice=ToolChoice(type="tool", name="submit_image_extraction"),
                        limits=RunLimits(
                            max_tool_turns=1,
                            max_output_tokens=prompt.max_tokens,
                            temperature=prompt.temperature,
                        ),
                        project_id=project_id,
                    )
                )

                extraction = self._parse_tool_response(result)
                extraction["image_name"] = image_path.name

                all_extractions.append(extraction)

                total_input_tokens += result.usage.input_tokens
                total_output_tokens += result.usage.output_tokens

            # Build pages list (one page per image)
            pages = []
            for extraction in all_extractions:
                page_content = self._format_extraction_content(extraction)
                # Add image name at the top of each page for context
                image_name = extraction.get("image_name", "unknown")
                full_page = f"# {image_name}\n\n{page_content}"
                pages.append(full_page)

            # Calculate character and token counts
            full_text = "\n".join(pages)
            character_count = len(full_text)
            token_count = count_tokens(full_text)

            # Build metadata for IMAGE type (batch)
            metadata = {
                "model_used": prompt.model,
                "content_type": "batch",
                "character_count": character_count,
                "token_count": token_count
            }

            # Use centralized build_processed_output for consistent format
            # Source name indicates this is a batch
            processed_content = build_processed_output(
                pages=pages,
                source_type="IMAGE",
                source_name=f"{len(image_paths)} images",
                metadata=metadata
            )

            logger.info("Batch extraction complete: %d images processed", len(image_paths))

            # Return processed content for processor to upload to Supabase Storage
            return {
                "success": True,
                "status": "ready",
                "processed_content": processed_content,
                "images_processed": len(image_paths),
                "character_count": character_count,
                "token_count": token_count,
                "token_usage": {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens
                },
                "model_used": prompt.model,
                "extracted_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.exception("Batch image extraction failed")
            return {
                "success": False,
                "status": "error",
                "error": str(e)
            }


# Singleton instance
image_service = ImageService()
