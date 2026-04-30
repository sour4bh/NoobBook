"""
CSV Analyzer Agent - AI agent for answering questions about CSV data.

Educational Note: This agent uses pandas for flexible data analysis:
1. Receives a user query about a CSV file
2. Requests validated table operations through the run_analysis tool
3. Can generate visualizations with matplotlib/seaborn
4. Returns final answer via return_analysis (termination tool)

The agent is triggered by main_chat when user asks about CSV sources.
Results (including any generated plots) are returned to main_chat.

Security Note:
    `run_analysis` is declarative after NBB-907. The model can request only
    validated inspect/filter/aggregate/sort/chart operations, not arbitrary
    Python source.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional
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
from app.sources.analysis.csv.raw_tools.binding import bind_csv_analysis_tools

logger = logging.getLogger(__name__)


class CSVAnalyzerAgent:
    """
    Agent for answering user questions about CSV data using pandas.

    Educational Note: This agent asks for typed table operations instead of
    arbitrary Python, keeping CSV analysis available in auth-required mode.
    """

    AGENT_NAME = "csv_analyzer_agent"
    MAX_ITERATIONS = 20
    TERMINATION_TOOL = "return_analysis"

    def __init__(self):
        """Initialize agent with lazy-loaded config and tools."""
        self._tools = None

    def _load_tools(self) -> tuple:
        """
        Load tools for data analysis.

        Educational Note: We load tools from analysis_agent category:
        - run_analysis: Execute a validated table operation
        - return_analysis: Return final answer with optional plots
        """
        if self._tools is None:
            self._tools = tool_loader.load_tool_specs_for_agent("analysis_agent")
        return self._tools

    def run(
        self,
        project_id: str,
        source_id: str,
        query: str,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the agent to answer a question about CSV data.

        Educational Note: The agent requests validated operations to answer
        questions. It can run multiple operations and generate plots before
        returning.

        Args:
            project_id: Project ID (for file paths and cost tracking)
            source_id: Source ID of the CSV file
            query: User's question about the data

        Returns:
            Dict with success status, summary, and optional image_paths
        """
        tools = self._load_tools()

        execution_id = str(uuid.uuid4())
        started_at = datetime.now().isoformat()

        prompt = render_prompt(
            "csv_analyzer_agent",
            {"filename": f"{source_id}.csv", "query": query},
            project_id=project_id,
        )
        user_message = prompt.user_message or "Analyze this data."

        # Track generated plot paths across iterations
        generated_plots = []

        logger.info("Starting CSV analysis for: %s", query[:50])

        result = run_with_provider(
            RunRequest(
                provider=prompt.provider,
                model=prompt.model,
                purpose=self.AGENT_NAME,
                system_prompt=prompt.system_prompt,
                messages=[RunMessage(role="user", content=[TextPart(text=user_message)])],
                tools=bind_csv_analysis_tools(
                    tools,
                    project_id=project_id,
                    source_id=source_id,
                    generated_plots=generated_plots,
                ),
                tool_choice=ToolChoice(type="any"),
                limits=RunLimits(
                    max_tool_turns=self.MAX_ITERATIONS,
                    max_output_tokens=prompt.max_tokens,
                    temperature=prompt.temperature,
                ),
                project_id=project_id,
                chat_id=chat_id,
                user_id=user_id,
                metadata={"tags": ["query"]},
            )
        )

        final_tool_result = self._terminating_tool_result(result)
        if final_tool_result is not None:
            iterations = self._iteration_count(result)
            logger.info("Completed in %d iterations", iterations)
            final_result = self._build_result(
                final_tool_result,
                iterations,
                result.usage.input_tokens,
                result.usage.output_tokens,
            )
            self._save_execution(
                project_id, execution_id, query,
                self._execution_messages(result, user_message),
                final_result, started_at, source_id
            )
            return final_result

        logger.warning("CSV analysis completed without return_analysis")
        error_result = {
            "success": False,
            "error": "Analysis completed without returning a final answer",
            "usage": result.usage.model_dump(mode="json"),
        }

        self._save_execution(
            project_id, execution_id, query,
            self._execution_messages(result, user_message),
            error_result, started_at, source_id
        )
        return error_result

    def _terminating_tool_result(self, result: Any) -> Optional[Dict[str, Any]]:
        """Return the validated terminating tool payload, if present."""
        for tool_result in reversed(result.tool_results):
            if tool_result.name != self.TERMINATION_TOOL:
                continue
            if isinstance(tool_result.content, dict):
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

    def _build_result(
        self,
        tool_input: Dict[str, Any],
        iterations: int,
        input_tokens: int,
        output_tokens: int
    ) -> Dict[str, Any]:
        """
        Build the final result from return_analysis tool input.

        Educational Note: The termination tool input contains:
        - summary: Text answer to the user's question
        - data: Optional structured data
        - image_paths: Paths to generated plots
        """
        return {
            "success": True,
            "summary": tool_input.get("summary", ""),
            "data": _parse_data_json(tool_input.get("data_json")),
            "image_paths": tool_input.get("image_paths", []),
            "iterations": iterations,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            "generated_at": datetime.now().isoformat()
        }

    def _save_execution(
        self,
        project_id: str,
        execution_id: str,
        query: str,
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
            task=f"Analyze CSV: {query}",
            messages=messages,
            result=result,
            started_at=started_at,
            metadata={"source_id": source_id, "query": query}
        )


csv_analyzer_agent = CSVAnalyzerAgent()


def _parse_data_json(value: Any) -> Optional[Dict[str, Any]]:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
