"""
Business Report Agent Service - AI agent for generating data-driven business reports.

Orchestrates the business report generation workflow:
1. Agent plans the report structure (plan_business_report)
2. Agent calls csv_analyzer_agent for data analysis (analyze_csv_data)
3. Agent searches non-CSV sources for context (search_source_content)
4. Agent writes the final markdown report (write_business_report - termination)
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
import app.studio.jobs.store as studio_index_service
from app.studio.documents.business_report.tools.binding import bind_business_report_tools

logger = logging.getLogger(__name__)


class BusinessReportWriter:
    """Business report generation agent - orchestration only."""

    AGENT_NAME = "business_report_agent"
    MAX_ITERATIONS = 15

    def __init__(self):
        self._tools = None

    def _load_tools(self) -> List[Dict[str, Any]]:
        if self._tools is None:
            self._tools = list(tool_loader.load_tool_specs_for_agent(self.AGENT_NAME))
        return self._tools

    def generate_business_report(
        self,
        project_id: str,
        source_id: str,
        job_id: str,
        direction: str = "",
        report_type: str = "executive_summary",
        csv_source_ids: List[str] = None,
        context_source_ids: List[str] = None,
        focus_areas: List[str] = None,
        edit_instructions: Optional[str] = None,
        previous_markdown: Optional[str] = None,
        previous_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run the agent to generate a business report."""
        tools = self._load_tools()

        csv_source_ids = csv_source_ids or []
        context_source_ids = context_source_ids or []
        focus_areas = focus_areas or []

        execution_id = str(uuid.uuid4())
        started_at = datetime.now().isoformat()

        # Update job status
        studio_index_service.update_business_report_job(
            project_id, job_id,
            status="processing",
            status_message="Starting business report generation...",
            started_at=started_at
        )

        # Get source information and build user message
        source_info = self._get_source_info(project_id, csv_source_ids, context_source_ids)
        brand_context = brand_context_loader.load_brand_context(project_id, "business_report")
        prompt = render_prompt(
            "business_report_agent",
            self._user_message_context(
                source_info,
                report_type.replace("_", " ").title(),
                direction,
                focus_areas,
            ),
            project_id=project_id,
            extra_sections=[brand_context] if brand_context else (),
        )
        report_types = prompt.metadata.get("report_types", {})
        report_type_display = report_types.get(report_type, report_type.replace("_", " ").title())

        prompt = render_prompt(
            "business_report_agent",
            self._user_message_context(
                source_info,
                report_type_display,
                direction,
                focus_areas,
            ),
            project_id=project_id,
            extra_sections=[brand_context] if brand_context else (),
        )
        user_message = prompt.user_message or ""

        # Edit mode: append previous report and edit instructions to user message
        if edit_instructions and previous_markdown:
            edit_context = f"\n\n## EDIT MODE\n\nYou are editing a previously generated report. Apply the user's edit instructions to refine the report.\n\n### Previous Report Title: {previous_title or 'Untitled'}\n\n### Previous Report Content:\n{previous_markdown}\n\n### Edit Instructions:\n{edit_instructions}\n\nStart from the previous content as your baseline. Apply the edit instructions to refine the report. Keep elements the user didn't ask to change. Focus changes on what the edit instructions specify. You may still call analyze_csv_data if the edit requires new data analysis or charts."
            user_message += edit_context

        collected_charts = []
        collected_analyses = []

        logger.info("Starting business report agent job %s, type=%s", job_id[:8], report_type)

        context = {
            "project_id": project_id,
            "job_id": job_id,
            "source_id": source_id,
            "collected_charts": collected_charts,
            "collected_analyses": collected_analyses,
            "iterations": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "report_type": report_type,
        }
        result = run_with_provider(
            RunRequest(
                provider=prompt.provider,
                model=prompt.model,
                purpose=self.AGENT_NAME,
                system_prompt=prompt.system_prompt,
                messages=[RunMessage(role="user", content=[TextPart(text=user_message)])],
                tools=bind_business_report_tools(tools, context=context),
                tool_choice=ToolChoice(type="any"),
                limits=RunLimits(
                    max_tool_turns=self.MAX_ITERATIONS,
                    max_output_tokens=prompt.max_tokens,
                    temperature=prompt.temperature,
                ),
                project_id=project_id,
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

        logger.warning("Business report agent completed without write_business_report")
        error_result = {
            "success": False,
            "error_message": "Agent completed without writing the business report",
            "iterations": self._iteration_count(result),
            "usage": result.usage.model_dump(mode="json"),
        }

        studio_index_service.update_business_report_job(
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
            if tool_result.name == "write_business_report" and isinstance(tool_result.content, dict):
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

    def _get_source_info(
        self,
        project_id: str,
        csv_source_ids: List[str],
        context_source_ids: List[str]
    ) -> Dict[str, Any]:
        """Get information about available sources."""
        try:
            from app.sources.catalog import source_service

            csv_sources = []
            for source_id in csv_source_ids:
                source = source_service.get_source(project_id, source_id)
                if source:
                    csv_sources.append({
                        "source_id": source_id,
                        "name": source.get("name", "Unknown"),
                        "type": "csv"
                    })

            context_sources = []
            for source_id in context_source_ids:
                source = source_service.get_source(project_id, source_id)
                if source:
                    context_sources.append({
                        "source_id": source_id,
                        "name": source.get("name", "Unknown"),
                        "type": source.get("file_extension", "unknown")
                    })

            return {
                "csv_sources": csv_sources,
                "context_sources": context_sources
            }

        except Exception as e:
            logger.exception("Error getting source info")
            return {"csv_sources": [], "context_sources": []}

    def _user_message_context(
        self,
        source_info: Dict[str, Any],
        report_type_display: str,
        direction: str,
        focus_areas: List[str]
    ) -> Dict[str, Any]:
        """Build prompt render values with exact source IDs."""
        # Build CSV sources section
        csv_sources = source_info.get("csv_sources", [])
        if csv_sources:
            csv_lines = ["CSV DATA SOURCES:"]
            for src in csv_sources:
                csv_lines.append(f"- {src['name']} (source_id: {src['source_id']})")
            csv_sources_section = "\n".join(csv_lines)
        else:
            csv_sources_section = ""

        # Build context sources section
        context_sources = source_info.get("context_sources", [])
        if context_sources:
            ctx_lines = ["CONTEXT SOURCES (optional):"]
            for src in context_sources:
                ctx_lines.append(f"- {src['name']} (source_id: {src['source_id']})")
            context_sources_section = "\n".join(ctx_lines)
        else:
            context_sources_section = ""

        # Build focus areas section
        if focus_areas:
            focus_areas_section = "FOCUS ON: " + ", ".join(focus_areas)
        else:
            focus_areas_section = ""

        # Build direction section
        if direction:
            direction_section = f"NOTE: {direction}"
        else:
            direction_section = ""

        return {
            "report_type_display": report_type_display,
            "csv_sources_section": csv_sources_section,
            "context_sources_section": context_sources_section,
            "focus_areas_section": focus_areas_section,
            "direction_section": direction_section,
        }

    def _save_execution(
        self,
        project_id: str,
        execution_id: str,
        job_id: str,
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
            task=f"Generate business report (job: {job_id[:8]})",
            messages=messages,
            result=result,
            started_at=started_at,
            metadata={"source_id": source_id, "job_id": job_id}
        )


# Singleton instance
business_report_agent_service = BusinessReportWriter()
