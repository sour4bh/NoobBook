"""Source extraction contract tests for provider-neutral runtime cleanup."""

from pathlib import Path

from app.agents.runtime import RunResult, ToolContext, ToolResult
from app.agents.runtime.tool import ToolOutput
from app.sources.analysis.csv.raw_tools import binding as csv_binding
from app.sources.analysis.csv.raw_tools.specs import TOOL_SPECS
from app.sources.pptx.extract import PPTXService


def test_source_extraction_does_not_import_anthropic_rate_policy() -> None:
    app_root = Path(__file__).parents[2] / "app" / "sources"
    targets = [
        app_root / "pdf" / "extract.py",
        app_root / "pptx" / "extract.py",
        app_root / "image" / "extract.py",
    ]

    offenders = [
        str(path.relative_to(app_root))
        for path in targets
        if "get_anthropic_config" in path.read_text()
        or "app.providers.anthropic.rate" in path.read_text()
    ]

    assert offenders == []


def test_pptx_missing_slide_tool_results_are_marked_as_failures() -> None:
    service = PPTXService()
    result = RunResult(
        provider="fake",
        model="fake-model",
        tool_results=[
            ToolResult(
                call_id="call-1",
                name="submit_slide_extraction",
                content={
                    "slide_number": 1,
                    "slide_title": "Intro",
                    "text_content": "Welcome",
                },
            )
        ],
    )

    parsed = service._parse_tool_results(result, [1, 2])

    assert parsed[1]["slide_title"] == "Intro"
    assert parsed[2]["error"] == "No tool call received for this slide"
    assert parsed[2]["text_content"] == "[EXTRACTION FAILED - No tool call received]"


def test_csv_raw_analysis_failures_return_runtime_tool_error(monkeypatch) -> None:
    def fail_dispatch(tool_name, tool_input, project_id, source_id):
        return {"success": False, "error": "Unknown column"}, False

    monkeypatch.setattr(csv_binding.analysis_executor, "dispatch", fail_dispatch)
    tools = csv_binding.bind_csv_analysis_tools(
        TOOL_SPECS,
        project_id="project-1",
        source_id="source-1",
        generated_plots=[],
    )
    run_analysis = next(tool for tool in tools if tool.name == "run_analysis")

    output = run_analysis.execute(
        {"operation": {"kind": "inspect"}},
        ToolContext(project_id="project-1"),
    )

    assert isinstance(output, ToolOutput)
    assert output.is_error is True
    assert output.content == "Error: Unknown column"
