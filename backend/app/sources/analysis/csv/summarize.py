"""
CSV Service - AI service for analyzing CSV files and generating summaries.

Educational Note: This service uses a simple agentic loop pattern:
1. Claude receives the filename and available tools
2. Claude calls csv_analyzer to understand the data
3. Claude calls return_csv_summary with the final summary (termination)

The CSV content is NOT sent to the model directly (could be huge).
Instead, when Claude calls csv_analyzer, we execute it locally and
return the results to the model for analysis.

CSV files are NOT chunked or embedded - they are analyzed on-demand.
"""

import logging
from typing import Dict, Any, Optional
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
from app.sources.analysis.csv.tools.binding import bind_csv_summary_tools

logger = logging.getLogger(__name__)


class CSVService:
    """
    AI service for CSV analysis and summary generation.

    Educational Note: Uses Haiku model with csv_analyzer tool.
    Claude analyzes the tool output and generates a concise summary.
    """

    MAX_ITERATIONS = 5  # Simple analysis shouldn't need many iterations
    TERMINATION_TOOL = "return_csv_summary"

    def __init__(self):
        """Initialize with lazy-loaded config and tools."""
        self._tools: Optional[list] = None

    def _get_tools(self) -> list:
        """Load and cache tools from csv_tool category."""
        if self._tools is None:
            self._tools = tool_loader.load_tool_specs_for_agent("csv_tool")
        return self._tools

    def analyze_csv(
        self,
        project_id: str,
        source_id: str,
        csv_file_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze a CSV file and generate a summary.

        Educational Note: Simple agentic loop:
        1. Send initial message with source_id
        2. When Claude calls csv_analyzer, executor reads file and analyzes
        3. When Claude calls return_csv_summary, extract and return summary

        Args:
            project_id: Project ID (for file path and cost tracking)
            source_id: Source ID (filename is {source_id}.csv in raw folder)
            csv_file_path: Optional explicit path to the CSV file (e.g. temp directory
                           during processing). Passed through to csv_tool_executor.

        Returns:
            Dict with summary, row_count, column_count, and metadata
        """
        tools = self._get_tools()

        prompt = render_prompt(
            "csv_processor",
            {"filename": f"{source_id}.csv"},
            project_id=project_id,
        )
        user_message = prompt.user_message or "Analyze this CSV file."

        logger.info("Analyzing CSV source %s", source_id[:8])

        result = run_with_provider(
            RunRequest(
                provider=prompt.provider,
                model=prompt.model,
                purpose="csv_processor",
                system_prompt=prompt.system_prompt,
                messages=[RunMessage(role="user", content=[TextPart(text=user_message)])],
                tools=bind_csv_summary_tools(
                    tools,
                    project_id=project_id,
                    source_id=source_id,
                    csv_file_path=csv_file_path,
                ),
                tool_choice=ToolChoice(type="any"),
                limits=RunLimits(
                    max_tool_turns=self.MAX_ITERATIONS,
                    max_output_tokens=prompt.max_tokens,
                    temperature=prompt.temperature,
                ),
                project_id=project_id,
                metadata={"tags": ["csv_processor"]},
            )
        )
        final_payload = self._terminating_tool_result(result)
        if final_payload is not None:
            logger.info(
                "CSV analysis completed in %d iterations",
                self._iteration_count(result),
            )
            return self._build_result(
                final_payload,
                self._iteration_count(result),
                result.usage.input_tokens,
                result.usage.output_tokens,
            )

        logger.warning("CSV analysis completed without summary tool")
        return {
            "success": False,
            "error": "Analysis completed without a summary",
            "usage": result.usage.model_dump(mode="json"),
        }

    def _terminating_tool_result(self, result: Any) -> Optional[Dict[str, Any]]:
        for tool_result in reversed(result.tool_results):
            if tool_result.name == self.TERMINATION_TOOL and isinstance(tool_result.content, dict):
                return tool_result.content
        return None

    def _iteration_count(self, result: Any) -> int:
        assistant_turns = [
            message
            for message in result.generated_messages
            if getattr(message, "role", None) == "assistant"
        ]
        return len(assistant_turns) or 1

    def _build_result(
        self,
        tool_input: Dict[str, Any],
        iterations: int,
        input_tokens: int,
        output_tokens: int
    ) -> Dict[str, Any]:
        """
        Build the final result from return_csv_summary tool input.

        Educational Note: The termination tool's input IS the result.
        We just add metadata (iterations, token usage, timestamp).
        """
        return {
            "success": True,
            "summary": tool_input.get("summary", ""),
            "row_count": tool_input.get("row_count", 0),
            "column_count": tool_input.get("column_count", 0),
            "iterations": iterations,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            "generated_at": datetime.now().isoformat()
        }


# Singleton instance
csv_service = CSVService()
