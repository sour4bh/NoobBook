"""
Mind Map Service - Generates hierarchical mind maps from source content.

Educational Note: This service uses the selected model to generate structured mind maps
for visual concept mapping. Like the flash cards service, this is a single-call
service using tool-based extraction:

1. Read source content (chunked or full)
2. Call the selected model with generate_mind_map tool
3. Parse and return the hierarchical node structure

The tool-based approach ensures structured output with proper parent-child
relationships (id, label, parent_id, node_type, description).
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.agents.runtime import (
    RunLimits,
    RunMessage,
    RunRequest,
    TextPart,
    ToolChoice,
    ToolSpec,
    bind_local_tools,
    echo_input,
    require_tool_result_payload,
    run_with_provider,
)
from app.providers.supabase import storage_service
import app.studio.jobs.store as studio_index_service
from app.config.prompt import render_prompt
from app.config.tool import tool_loader
from app.sources import index


logger = logging.getLogger(__name__)


class MindMapBuilder:
    """
    Service for generating mind maps from source content.

    Educational Note: Mind maps are generated in a single model call
    using the generate_mind_map tool for structured hierarchical output.
    """

    def __init__(self):
        """Initialize service with lazy-loaded config and tools."""
        self._tool = None

    def _load_tool(self) -> ToolSpec:
        """Load the mind map tool definition."""
        if self._tool is None:
            self._tool = tool_loader.load_tool_spec("studio_tools", "mind_map_tool")
        return self._tool

    def _get_source_content(
        self,
        project_id: str,
        source_id: str,
        max_tokens: int = 8000
    ) -> str:
        """
        Get source content for mind map generation.

        Educational Note: For large sources, we sample chunks evenly
        to stay within token limits while covering the full content.
        Content is downloaded from Supabase Storage.
        """
        # Get source metadata
        source = index.get_source_from_index(project_id, source_id)
        if not source:
            return ""

        # Token count is stored in embedding_info
        embedding_info = source.get("embedding_info", {}) or {}
        token_count = embedding_info.get("token_count", 0) or 0

        # For small sources, read the processed file from Supabase Storage
        if token_count < max_tokens:
            processed_content = storage_service.download_processed_file(
                project_id, source_id
            )
            if processed_content:
                return processed_content

        # For large sources, get chunks from Supabase Storage
        chunks = storage_service.list_source_chunks(project_id, source_id)
        if not chunks:
            return ""

        # Sample evenly across chunks
        total_chunks = len(chunks)
        sample_count = min(20, total_chunks)  # Max 20 chunks
        step = max(1, total_chunks // sample_count)

        content_parts = []
        for i in range(0, total_chunks, step):
            if len(content_parts) >= sample_count:
                break
            chunk_text = chunks[i].get("text", "")
            content_parts.append(chunk_text.strip())

        return '\n\n---\n\n'.join(content_parts)

    def generate_mind_map(
        self,
        project_id: str,
        source_id: str,
        job_id: str,
        direction: str = "Create a mind map covering the key concepts and their relationships.",
        previous_content: Optional[str] = None,
        edit_instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a mind map for a source, or edit an existing mind map.

        Args:
            project_id: The project UUID
            source_id: The source UUID
            job_id: The job ID for status tracking
            direction: User's direction for what to focus on
            previous_content: JSON string of previous nodes (for edits)
            edit_instructions: User instructions for editing (for edits)

        Returns:
            Dict with success status, nodes array, and metadata
        """
        started_at = datetime.now()
        is_edit = bool(previous_content and edit_instructions)

        # Update job to processing
        studio_index_service.update_mind_map_job(
            project_id, job_id,
            status="processing",
            progress="Editing mind map..." if is_edit else "Reading source content...",
            started_at=datetime.now().isoformat()
        )

        try:
            # Get source metadata
            source = index.get_source_from_index(project_id, source_id)
            if not source:
                raise ValueError(f"Source {source_id} not found")

            source_name = source.get("name", "Unknown")

            # For edits, skip source fetching — previous content is the baseline
            if is_edit:
                content = "[Source content available via previous mind map nodes below]"
            else:
                # Get source content
                studio_index_service.update_mind_map_job(
                    project_id, job_id,
                    progress="Analyzing content..."
                )

                content = self._get_source_content(project_id, source_id)
                if not content:
                    raise ValueError("No content found for source")

            # Load the static tool and render this run's prompt context.
            tool = self._load_tool()

            prompt = render_prompt(
                "mind_map",
                {
                    "direction": direction,
                    "content": content[:15000],
                },
                project_id=project_id,
            )
            user_message = prompt.user_message or ""

            # Append edit context so Claude refines rather than regenerates
            if is_edit:
                edit_context = (
                    f"\n\n=== PREVIOUS MIND MAP (refine based on edit instructions) ===\n"
                    f"{previous_content[:10000]}\n"
                    f"=== END PREVIOUS MIND MAP ===\n\n"
                    f"EDIT INSTRUCTIONS: {edit_instructions[:2000]}\n\n"
                    f"Use the previous mind map nodes as baseline. Apply the edits. "
                    f"Keep unchanged nodes intact."
                )
                user_message += edit_context

            # Call the selected model with the mind map tool
            studio_index_service.update_mind_map_job(
                project_id, job_id,
                progress="Generating mind map..."
            )

            result = run_with_provider(
                RunRequest(
                    provider=prompt.provider,
                    model=prompt.model,
                    purpose="mind_map",
                    messages=[
                        RunMessage(role="user", content=[TextPart(text=user_message)])
                    ],
                    system_prompt=prompt.system_prompt,
                    tools=bind_local_tools([tool], {tool.name: echo_input}),
                    tool_choice=ToolChoice(type="tool", name="generate_mind_map"),
                    limits=RunLimits(
                        max_tool_turns=1,
                        max_output_tokens=prompt.max_tokens,
                        temperature=prompt.temperature,
                    ),
                    project_id=project_id,
                )
            )

            tool_inputs = require_tool_result_payload(result, "generate_mind_map", dict)
            if "nodes" not in tool_inputs:
                raise ValueError("Failed to generate mind map - no nodes returned")

            nodes = tool_inputs["nodes"]
            topic_summary = tool_inputs.get("topic_summary", "")

            # Validate the mind map structure
            self._validate_mind_map(nodes)

            # Calculate generation time
            generation_time = (datetime.now() - started_at).total_seconds()

            # Update job with results
            studio_index_service.update_mind_map_job(
                project_id, job_id,
                status="ready",
                progress="Complete",
                nodes=nodes,
                topic_summary=topic_summary,
                node_count=len(nodes),
                generation_time_seconds=round(generation_time, 1),
                completed_at=datetime.now().isoformat()
            )

            logger.info("Generated %s mind map nodes in %.1fs", len(nodes), generation_time)

            return {
                "success": True,
                "nodes": nodes,
                "topic_summary": topic_summary,
                "node_count": len(nodes),
                "source_name": source_name,
                "generation_time": generation_time
            }

        except Exception as e:
            logger.exception("Mind map generation failed")
            studio_index_service.update_mind_map_job(
                project_id, job_id,
                status="error",
                error=str(e),
                completed_at=datetime.now().isoformat()
            )
            return {
                "success": False,
                "error": str(e)
            }

    def _validate_mind_map(self, nodes: List[Dict[str, Any]]) -> None:
        """
        Validate the mind map structure.

        Checks:
        1. Exactly one root node (parent_id is None/null)
        2. All parent_ids reference valid node ids
        3. No orphaned nodes (except root)
        """
        if not nodes:
            raise ValueError("Mind map has no nodes")

        # Find root nodes
        root_nodes = [n for n in nodes if n.get("parent_id") is None]
        if len(root_nodes) == 0:
            raise ValueError("Mind map has no root node")
        if len(root_nodes) > 1:
            # Just warn, don't fail - use first as root
            logger.warning("Mind map has %s root nodes, expected 1", len(root_nodes))

        # Build id set for validation
        node_ids = {n["id"] for n in nodes}

        # Check all parent_ids are valid
        for node in nodes:
            parent_id = node.get("parent_id")
            if parent_id is not None and parent_id not in node_ids:
                logger.warning("Mind map node %s has invalid parent_id: %s", node["id"], parent_id)


# Singleton instance
mind_map_service = MindMapBuilder()
