"""
Tests for DeepResearchAgent.

Covers:
- Bug 4 regression: output_path is required
- Smoke test with mocked runtime provider calls
"""
import pytest
from unittest.mock import patch, MagicMock

from app.agents.runtime.contract import RunResult, TextPart, Usage
from app.config.prompt import RenderedPrompt
from app.sources.analysis.research.agent import DeepResearchAgent


@pytest.fixture
def agent():
    return DeepResearchAgent()


class TestOutputPathRequired:

    def test_raises_when_omitted(self, agent):
        """Calling research() without output_path raises ValueError."""
        with pytest.raises(ValueError, match="output_path is required"):
            agent.research(
                project_id="p1",
                source_id="s1",
                topic="AI",
                description="Research AI",
            )

    def test_raises_when_empty_string(self, agent):
        """Empty string output_path also raises ValueError."""
        with pytest.raises(ValueError, match="output_path is required"):
            agent.research(
                project_id="p1",
                source_id="s1",
                topic="AI",
                description="Research AI",
                output_path="",
            )

    @patch("app.chat.message.message_service")
    @patch("app.sources.analysis.research.agent.run_with_provider")
    @patch("app.sources.analysis.research.agent.render_prompt")
    def test_works_with_output_path(self, render_prompt, run_provider, mock_msg, agent):
        """Smoke test: valid output_path proceeds to the provider adapter."""
        render_prompt.return_value = RenderedPrompt(
            name="deep_research_agent",
            provider="anthropic",
            model="test-model",
            max_tokens=100,
            temperature=0.5,
            system_prompt="You are a researcher.",
            user_message="Research: AI\nResearch AI\nNo specific links provided.",
        )
        agent._tools = []

        # Provider returns no terminating tool call.
        run_provider.return_value = RunResult(
            provider="anthropic",
            model="test-model",
            status="complete",
            text="Done",
            content=[TextPart(text="Done")],
            usage=Usage(input_tokens=10, output_tokens=5),
        )

        result = agent.research(
            project_id="p1",
            source_id="s1",
            topic="AI",
            description="Research AI",
            output_path="/tmp/test_output.md",
        )

        assert result["success"] is False
        assert "without final segment" in result["error"]
        run_provider.assert_called()
