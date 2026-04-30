"""Executable chat tool bindings for one runtime run."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from app.agents.runtime import bind_local_tools
from app.agents.runtime.tool import ToolContext, ToolOutput, ToolSpec
from app.chat import memory as chat_memory
from app.connectors.knowledge import knowledge_base_service
from app.sources.analysis.csv import entry as csv_entry
from app.sources.analysis.database import entry as database_entry
from app.sources.analysis.freshdesk import entry as freshdesk_entry
from app.sources.search import source_search_executor
from app.studio.signal.tools.binding import bind_studio_signal_tools


def bind_chat_tools(
    tools: list[ToolSpec],
    *,
    project_id: str,
    chat_id: str,
    user_id: Optional[str],
    mcp_registry: dict[str, Any],
) -> list[ToolSpec]:
    """Attach chat-owned handlers to static tool contracts for one run."""

    def input_data(value: BaseModel) -> dict[str, Any]:
        return value.model_dump(mode="json")

    def search_sources(value: BaseModel, context: ToolContext) -> str:
        tool_input = input_data(value)
        result = source_search_executor.search(
            project_id=project_id,
            source_id=tool_input.get("source_id", ""),
            keywords=tool_input.get("keywords"),
            query=tool_input.get("query"),
        )
        if result.get("success"):
            return result.get("content", "No content found")
        return ToolOutput(
            content=result.get("error", "Unknown error"),
            is_error=True,
        )

    def store_memory(value: BaseModel, context: ToolContext) -> str:
        tool_input = input_data(value)
        result = chat_memory.store(
            project_id=project_id,
            user_memory=tool_input.get("user_memory"),
            project_memory=tool_input.get("project_memory"),
            why_generated=tool_input.get("why_generated", ""),
            user_id=user_id,
        )
        if result.get("success"):
            return result.get("message", "Memory stored successfully")
        return ToolOutput(
            content=result.get("message", "Unknown error"),
            is_error=True,
        )

    def analyze_csv_agent(value: BaseModel, context: ToolContext) -> str:
        tool_input = input_data(value)
        result = csv_entry.execute(
            project_id=project_id,
            source_id=tool_input.get("source_id", ""),
            query=tool_input.get("query", ""),
            chat_id=chat_id,
            user_id=user_id,
        )
        if not result.get("success"):
            return ToolOutput(
                content=result.get("error", "Analysis failed"),
                is_error=True,
            )
        content = result.get("content", "No analysis result")
        if result.get("image_paths"):
            content += "\n\nGenerated visualizations (use these exact filenames):\n"
            for filename in result["image_paths"]:
                content += f"- [[image:{filename}]]\n"
        return content

    def analyze_database_agent(value: BaseModel, context: ToolContext) -> str:
        tool_input = input_data(value)
        result = database_entry.execute(
            project_id=project_id,
            source_id=tool_input.get("source_id", ""),
            query=tool_input.get("query", ""),
            chat_id=chat_id,
            user_id=user_id,
        )
        if result.get("success"):
            return result.get("content", "No analysis result")
        return ToolOutput(
            content=result.get("error", "Analysis failed"),
            is_error=True,
        )

    def analyze_freshdesk_agent(value: BaseModel, context: ToolContext) -> str:
        tool_input = input_data(value)
        result = freshdesk_entry.execute(
            project_id=project_id,
            source_id=tool_input.get("source_id", ""),
            query=tool_input.get("query", ""),
            chat_id=chat_id,
            user_id=user_id,
        )
        if result.get("success"):
            return result.get("content", "No analysis result")
        return ToolOutput(
            content=result.get("error", "Analysis failed"),
            is_error=True,
        )

    def knowledge_tool(tool_name: str):
        def handler(value: BaseModel, context: ToolContext) -> str | ToolOutput:
            result = knowledge_base_service.execute(
                project_id=project_id,
                chat_id=chat_id,
                tool_name=tool_name,
                tool_input=input_data(value),
            )
            if result.startswith("Error:"):
                return ToolOutput(content=result.removeprefix("Error:").strip(), is_error=True)
            return result

        return handler

    handlers = {
        "search_sources": search_sources,
        "store_memory": store_memory,
        "analyze_csv_agent": analyze_csv_agent,
        "analyze_database_agent": analyze_database_agent,
        "analyze_freshdesk_agent": analyze_freshdesk_agent,
    }
    for tool in tools:
        if knowledge_base_service.can_handle(tool.name):
            handlers[tool.name] = knowledge_tool(tool.name)

    bound = bind_local_tools(tools, handlers)
    return bind_studio_signal_tools(
        bound,
        project_id=project_id,
        chat_id=chat_id,
    )
