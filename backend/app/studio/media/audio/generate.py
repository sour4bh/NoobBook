"""
Audio Overview Service - Generates audio overviews from source content.

Educational Note: This service implements an agentic loop pattern:
1. Claude reads source content (read_source_content tool)
2. Claude writes script sections (write_script_section tool)
3. Loop continues until is_final=True
4. Script is converted to audio via ElevenLabs TTS

For large sources, Claude reads chunks incrementally and writes script sections
as it goes. For small sources, it reads all content at once.

Tools:
- read_source_content: Reads source content (full or chunk by chunk)
- write_script_section: Writes/appends script sections, signals completion
"""
import logging
import uuid
from typing import Dict, Any, List
from datetime import datetime

from app.agents.runtime import RunLimits, RunMessage, RunRequest, TextPart, ToolChoice, run_with_provider
from app.agents.runtime.error import ToolIterationLimitError
from app.providers.elevenlabs import tts_service
import app.studio.jobs.store as studio_index_service
from app.studio.media.audio.tool import studio_audio_executor
from app.studio.media.audio.tools.binding import bind_audio_tools
from app.config.prompt import render_prompt
from app.config.tool import tool_loader
from app.providers.supabase import storage_service
from app.sources import index


logger = logging.getLogger(__name__)


class AudioGenerator:
    """
    Service for generating audio overviews from source content.

    Educational Note: This service orchestrates the full pipeline:
    1. Agentic script generation (Claude reads content, writes script)
    2. TTS conversion (ElevenLabs converts script to audio)
    """

    AGENT_NAME = "audio_overview"
    MAX_ITERATIONS = 25  # Reasonable limit - most scripts finish in 5-15 iterations

    def __init__(self):
        """Initialize service with lazy-loaded config and tools."""
        self._tools = None

    def _load_tools(self) -> List[Dict[str, Any]]:
        """Load tools for the audio agent."""
        if self._tools is None:
            # Audio uses two tools: read_source_content (sources public surface)
            # and write_script_section (audio-owned). Loaded by name so the
            # legacy `studio_tools/` category dir can disappear after NBB-507.
            specs = [
                tool_loader.load_tool_spec("studio_tools", "read_source_content"),
                tool_loader.load_tool_spec("studio_tools", "write_script_section"),
            ]
            self._tools = specs
        return self._tools

    # =========================================================================
    # Main Entry Point (for background task)
    # =========================================================================

    def generate_audio_overview(
        self,
        project_id: str,
        source_id: str,
        job_id: str,
        direction: str = "Create an engaging audio overview of this content.",
        previous_content: str = None,
        edit_instructions: str = None
    ) -> Dict[str, Any]:
        """
        Generate an audio overview for a source, or edit a previous audio script.

        Educational Note: This is the main orchestrator that:
        1. Gets source metadata
        2. Runs the agentic script generation loop
        3. Converts script to audio
        4. Updates job status throughout

        For edits, the previous script is passed to the agent as context so
        Claude can refine it based on the user's edit instructions.

        Args:
            project_id: The project UUID
            source_id: The source UUID to generate overview for
            job_id: The job ID for status tracking
            direction: User's direction for the overview style/focus
            previous_content: Previous script text to refine (for edits)
            edit_instructions: Instructions for how to edit the previous audio

        Returns:
            Dict with success status, audio file path, and metadata
        """
        started_at = datetime.now()

        # Update job to processing
        studio_index_service.update_audio_job(
            project_id, job_id,
            status="processing",
            progress="Loading source...",
            started_at=datetime.now().isoformat()
        )

        # Step 1: Get source metadata
        source = index.get_source_from_index(project_id, source_id)
        if not source:
            studio_index_service.update_audio_job(
                project_id, job_id,
                status="error",
                error=f"Source not found: {source_id}",
                completed_at=datetime.now().isoformat()
            )
            return {"success": False, "error": f"Source not found: {source_id}"}

        source_name = source.get("name", "Unknown")
        embedding_info = source.get("embedding_info", {})
        token_count = embedding_info.get("token_count", 0)
        is_large = token_count >= studio_audio_executor.SMALL_SOURCE_THRESHOLD

        # Step 2: Setup filenames for Supabase Storage
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        script_filename = "script.txt"
        audio_filename = f"audio_{source_id[:8]}_{timestamp}.mp3"

        # Update progress
        studio_index_service.update_audio_job(
            project_id, job_id,
            progress="Generating script..."
        )

        # Step 3: Generate script via agentic loop (writes to Supabase Storage)
        script_result = self._generate_script(
            project_id=project_id,
            source_id=source_id,
            source_name=source_name,
            token_count=token_count,
            is_large=is_large,
            direction=direction,
            job_id=job_id,
            previous_content=previous_content,
            edit_instructions=edit_instructions
        )

        if not script_result.get("success"):
            studio_index_service.update_audio_job(
                project_id, job_id,
                status="error",
                error=script_result.get("error", "Script generation failed"),
                completed_at=datetime.now().isoformat()
            )
            return script_result

        # Update progress
        studio_index_service.update_audio_job(
            project_id, job_id,
            progress="Converting to audio..."
        )

        # Step 4: Read script from Supabase and convert to audio bytes
        script_text = storage_service.download_studio_file(
            project_id, "audio", job_id, script_filename
        )
        if not script_text:
            studio_index_service.update_audio_job(
                project_id, job_id,
                status="error",
                error="Script file not found in storage after generation",
                completed_at=datetime.now().isoformat()
            )
            return {"success": False, "error": "Script file not found in storage"}

        audio_result = tts_service.generate_audio_bytes(
            text=script_text,
            project_id=project_id,
        )

        if not audio_result.get("success"):
            studio_index_service.update_audio_job(
                project_id, job_id,
                status="error",
                error=f"TTS conversion failed: {audio_result.get('error')}",
                completed_at=datetime.now().isoformat()
            )
            return {
                "success": False,
                "error": f"TTS conversion failed: {audio_result.get('error')}"
            }

        # Upload audio bytes to Supabase Storage
        audio_bytes = audio_result["audio_bytes"]
        storage_path = storage_service.upload_studio_binary(
            project_id, "audio", job_id, audio_filename, audio_bytes, "audio/mpeg"
        )
        if not storage_path:
            studio_index_service.update_audio_job(
                project_id, job_id,
                status="error",
                error="Failed to upload audio to storage",
                completed_at=datetime.now().isoformat()
            )
            return {"success": False, "error": "Failed to upload audio to storage"}

        # Step 5: Update job as complete
        duration = (datetime.now() - started_at).total_seconds()
        audio_url = f"/api/v1/projects/{project_id}/studio/audio/{job_id}/{audio_filename}"

        studio_index_service.update_audio_job(
            project_id, job_id,
            status="ready",
            progress="Complete",
            audio_filename=audio_filename,
            audio_url=audio_url,
            audio_info={
                "file_size_bytes": audio_result.get("file_size_bytes"),
                "estimated_duration_seconds": audio_result.get("estimated_duration_seconds"),
                "word_count": len(script_text.split()),
                "voice_id": audio_result.get("voice_id"),
                "model_id": audio_result.get("model_id")
            },
            completed_at=datetime.now().isoformat()
        )

        return {
            "success": True,
            "job_id": job_id,
            "audio_filename": audio_filename,
            "audio_url": audio_url,
            "source_id": source_id,
            "source_name": source_name,
            "direction": direction,
            "duration_seconds": duration,
            "script_iterations": script_result.get("iterations", 0),
            "script_word_count": len(script_text.split()),
            "audio_info": audio_result,
            "usage": script_result.get("usage", {})
        }

    # =========================================================================
    # Script Generation (Agentic Loop)
    # =========================================================================

    def _generate_script(
        self,
        project_id: str,
        source_id: str,
        source_name: str,
        token_count: int,
        is_large: bool,
        direction: str,
        job_id: str,
        previous_content: str = None,
        edit_instructions: str = None
    ) -> Dict[str, Any]:
        """
        Generate script using agentic loop.

        Educational Note: The agent reads source content and writes script sections
        until it signals completion with is_final=True. Script is stored in
        Supabase Storage at: {project_id}/audio/{job_id}/script.txt

        For edits, the previous script is appended to the user message so Claude
        can refine it. Source reading is skipped when previous content is available.

        Args:
            project_id: The project UUID
            source_id: The source UUID
            source_name: Name of the source
            token_count: Token count of the source
            is_large: Whether source is large (needs chunked reading)
            direction: User's direction for the script
            job_id: Job ID for progress updates and Supabase storage path
            previous_content: Previous script text to refine (for edits)
            edit_instructions: Instructions for how to edit the previous script

        Returns:
            Dict with success status, iterations, and usage stats
        """
        tools = self._load_tools()

        prompt = render_prompt(
            "audio_script",
            {
                "direction": direction,
                "source_id": source_id,
                "source_name": source_name,
            },
            project_id=project_id,
        )
        user_message = prompt.user_message or ""

        # Append edit context if editing a previous audio script
        if previous_content and edit_instructions:
            edit_context = (
                f"\n\n=== PREVIOUS SCRIPT (refine based on edit instructions) ===\n"
                f"{previous_content}\n"
                f"=== END PREVIOUS SCRIPT ===\n\n"
                f"EDIT INSTRUCTIONS: {edit_instructions}\n\n"
                f"Use the previous script as baseline. Apply the edits. "
                f"Keep unchanged sections. Write the complete revised script "
                f"using write_script_section. You do NOT need to read the source "
                f"again — the previous script already covers it."
            )
            user_message += edit_context

        # Smaller limit for small sources (should finish in 2-3 iterations)
        max_iterations = 5 if not is_large else self.MAX_ITERATIONS

        context: dict[str, Any] = {
            "last_batch_seen": False,
            "full_content_seen": False,
            "completed": False,
        }

        try:
            result = run_with_provider(
                RunRequest(
                    provider=prompt.provider,
                    model=prompt.model,
                    purpose=self.AGENT_NAME,
                    system_prompt=prompt.system_prompt,
                    messages=[
                        RunMessage(role="user", content=[TextPart(text=user_message)])
                    ],
                    tools=bind_audio_tools(
                        tools,
                        project_id=project_id,
                        job_id=job_id,
                        context=context,
                    ),
                    tool_choice=ToolChoice(type="any"),
                    limits=RunLimits(
                        max_tool_turns=max_iterations,
                        max_output_tokens=prompt.max_tokens,
                        temperature=prompt.temperature,
                    ),
                    project_id=project_id,
                    metadata={"job_id": job_id, "source_id": source_id},
                )
            )
        except ToolIterationLimitError:
            logger.warning("Audio script generation hit max iterations (%s)", max_iterations)
            if storage_service.download_studio_file(project_id, "audio", job_id, "script.txt"):
                return {
                    "success": True,
                    "iterations": max_iterations,
                    "usage": {},
                    "note": f"Script generation used all {max_iterations} iterations",
                }
            return {
                "success": False,
                "error": f"Max iterations reached ({max_iterations}) without completing script",
                "iterations": max_iterations,
            }

        iterations = self._iteration_count(result)
        if context.get("completed") or "write_script_section" in result.terminated_by_tools:
            return {
                "success": True,
                "iterations": iterations,
                "usage": result.usage.model_dump(mode="json"),
            }

        if storage_service.download_studio_file(project_id, "audio", job_id, "script.txt"):
            logger.warning("Audio script generation ended before explicit finalization")
            reason = "last batch" if context.get("last_batch_seen") else "early provider stop"
            if context.get("full_content_seen"):
                reason = "full content"
            return {
                "success": True,
                "iterations": iterations,
                "usage": result.usage.model_dump(mode="json"),
                "note": f"Script generation accepted after {reason}",
            }

        return {
            "success": False,
            "error": "Script generation ended without producing output",
            "iterations": iterations,
        }

    def _iteration_count(self, result: Any) -> int:
        assistant_turns = [
            message
            for message in result.generated_messages
            if getattr(message, "role", None) == "assistant"
        ]
        return len(assistant_turns) or 1

# Singleton instance
audio_overview_service = AudioGenerator()
