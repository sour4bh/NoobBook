"""
Database Analyzer Agent - AI agent for answering questions using live DB data.

Educational Note: This agent is triggered by main chat via the analyze_database_agent tool.
It uses tool-calling to:
1) Inspect schema via schema_fetcher
2) Run read-only SQL via query_runner
3) Return a final answer via return_database_result (termination tool)
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config.prompt import render_prompt
from app.config.tool import tool_loader
from app.sources.analysis.database.tool import DatabaseExecutor
from app.agents.runtime import (
    RunLimits,
    RunMessage,
    RunRequest,
    TextPart,
    ToolChoice,
    run_with_provider,
)
from app.sources.analysis.database.tools.binding import bind_database_tools

logger = logging.getLogger(__name__)


class DatabaseAnalyzerAgent:
    """
    Agent for answering questions about DATABASE sources (Postgres/MySQL) using SQL.
    """

    AGENT_NAME = "database_analyzer_agent"
    MAX_ITERATIONS = 40
    TERMINATION_TOOL = "return_database_result"

    def __init__(self) -> None:
        self._tools: List[Dict[str, Any]] | None = None

    def _load_tools(self) -> List[Dict[str, Any]]:
        if self._tools is None:
            self._tools = list(tool_loader.load_tool_specs_for_agent("database_agent"))
        return self._tools or []

    def run(self, project_id: str, source_id: str, query: str, chat_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        tools = self._load_tools()

        execution_id = str(uuid.uuid4())
        started_at = datetime.now().isoformat()

        # Ground the agent in today's date so "yesterday", "last 7 days", etc.
        # in the user's question map to concrete YYYY-MM-DD values.
        from datetime import date
        today_line = f"Today's date: {date.today().isoformat()}"
        prompt = render_prompt(
            "database_analyzer_agent",
            {"source_id": source_id, "query": query},
            project_id=project_id,
        )
        system_prompt = f"{today_line}\n\n{prompt.system_prompt}"
        user_message = (
            prompt.user_message
            or f"Database source ID: {source_id}\n\nUser question: {query}"
        )

        messages: List[Dict[str, Any]] = [{"role": "user", "content": user_message}]

        executed_queries: List[str] = []

        executor = DatabaseExecutor()

        # Pre-flight check: verify the database connection is resolvable
        # BEFORE entering the expensive agent loop. This prevents wasting
        # API calls when the connection is missing or inaccessible.
        try:
            resolved = executor.validate_connection(project_id, source_id)
            logger.info(
                "DB agent pre-flight OK: connection_id=%s, db_type=%s, source_id=%s",
                resolved.connection_id, resolved.db_type, source_id,
            )
        except Exception as e:
            logger.error(
                "DB agent pre-flight FAILED for source_id=%s: %s",
                source_id, e,
            )
            error_result = {
                "success": False,
                "error": (
                    f"Cannot connect to database: {e}. "
                    f"Please verify the connection in Settings → Databases is still active "
                    f"and accessible from the server."
                ),
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
            self._save_execution(
                project_id=project_id,
                execution_id=execution_id,
                query=query,
                messages=messages,
                result=error_result,
                started_at=started_at,
                source_id=source_id,
            )
            return error_result

        try:
            run_result = run_with_provider(
                RunRequest(
                    provider=prompt.provider,
                    model=prompt.model,
                    purpose=self.AGENT_NAME,
                    system_prompt=system_prompt,
                    messages=[
                        RunMessage(role="user", content=[TextPart(text=user_message)])
                    ],
                    tools=bind_database_tools(
                        tools,
                        executor=executor,
                        project_id=project_id,
                        source_id=source_id,
                        executed_queries=executed_queries,
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
                    metadata={
                        "tags": ["query"],
                        "extra_headers": {"anthropic-beta": "context-1m-2025-08-07"},
                    },
                )
            )
            final_payload = self._terminating_tool_result(run_result)
            if final_payload is not None:
                final_result = self._build_result(
                    final_payload,
                    self._iteration_count(run_result),
                    run_result.usage.input_tokens,
                    run_result.usage.output_tokens,
                )
                self._save_execution(
                    project_id=project_id,
                    execution_id=execution_id,
                    query=query,
                    messages=self._execution_messages(run_result, user_message),
                    result=final_result,
                    started_at=started_at,
                    source_id=source_id,
                )
                return final_result

            error_result = {
                "success": False,
                "error": "Analysis completed without returning a final answer",
                "usage": run_result.usage.model_dump(mode="json"),
            }
            self._save_execution(
                project_id=project_id,
                execution_id=execution_id,
                query=query,
                messages=self._execution_messages(run_result, user_message),
                result=error_result,
                started_at=started_at,
                source_id=source_id,
            )
            return error_result

        finally:
            executor.close_connections()

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

    @staticmethod
    def _build_result(
        termination_input: Dict[str, Any],
        iterations: int,
        input_tokens: int,
        output_tokens: int,
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "summary": termination_input.get("summary", ""),
            "findings": termination_input.get("findings") or [],
            "sql_queries": termination_input.get("sql_queries") or [],
            "iterations": iterations,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            "generated_at": datetime.now().isoformat(),
        }

    def _save_execution(
        self,
        project_id: str,
        execution_id: str,
        query: str,
        messages: List[Dict[str, Any]],
        result: Dict[str, Any],
        started_at: str,
        source_id: str,
    ) -> None:
        from app.chat.message import message_service

        message_service.save_agent_execution(
            project_id=project_id,
            agent_name=self.AGENT_NAME,
            execution_id=execution_id,
            task=f"Analyze DB: {query}",
            messages=messages,
            result=result,
            started_at=started_at,
            metadata={"source_id": source_id, "query": query},
        )


database_analyzer_agent = DatabaseAnalyzerAgent()
