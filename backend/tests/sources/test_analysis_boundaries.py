"""
Source-analysis boundary tests (NBB-702 + NBB-907).

NBB-907 replaces the old raw-code CSV analysis path with declarative table
operations. This file pins the structural boundaries that NBB-403 reorganized:
every analysis slice's public import path resolves, and every chat-exposed
analysis tool is classified in the ``tool_capability_policy`` registry.

The runtime behavior of the declarative executor is covered by
``test_declarative_csv_analysis.py``. The tests below assert the import and
capability-policy surface.
"""
import pytest


# ---------------------------------------------------------------------------
# Public import paths (post-NBB-403 reorganization)
# ---------------------------------------------------------------------------


class TestAnalysisModulePublicSurface:
    """Every analysis slice must be importable through its post-NBB-403 path.

    These imports are the seams downstream code (chat tools, processors,
    NBB-907 declarative-analysis tests) reaches through. If a future cleanup ticket
    accidentally moves them, the chat tool registrations and the gate
    tests both break — but those break with confusing errors. Pinning
    them here surfaces the regression at its root.
    """

    def test_csv_run_module_exposes_declarative_executor(self):
        from app.sources.analysis.csv.run import analysis_executor

        assert hasattr(analysis_executor, "dispatch")

    def test_csv_agent_singleton_is_importable(self):
        from app.sources.analysis.csv.agent import csv_analyzer_agent

        # The agent has to expose a ``run`` method — that is the seam
        # ``main_chat`` calls when it dispatches the analyze_csv_agent tool.
        assert hasattr(csv_analyzer_agent, "run")

    def test_database_agent_singleton_is_importable(self):
        from app.sources.analysis.database.agent import database_analyzer_agent

        assert hasattr(database_analyzer_agent, "run")

    def test_freshdesk_agent_singleton_is_importable(self):
        from app.sources.analysis.freshdesk.agent import freshdesk_analyzer_agent

        assert hasattr(freshdesk_analyzer_agent, "run")

    def test_research_agent_singleton_is_importable(self):
        from app.sources.analysis.research.agent import deep_research_agent

        # Deep research uses ``research(...)``, not ``run(...)``; the
        # entry-point name is part of the public surface chat dispatchers
        # and the research processor reach through.
        assert hasattr(deep_research_agent, "research")

    def test_analysis_tool_capabilities_registers_at_import(self):
        # Importing the module is the side-effect that registers analysis
        # tools with the policy. If a future move drops the import (or the
        # ``register_many`` call), every analysis tool would silently fall
        # back to the unclassified-default deny — which would break chat
        # in production. Pin that the import call still populates the
        # registry.
        import app.sources.analysis.tool_capabilities as analysis_caps  # noqa: F401
        from app.auth.tool_policy import tool_capability_policy

        # ``analyze_csv_agent`` is the public chat-list trigger; it has to
        # appear after the import.
        assert tool_capability_policy.has("analyze_csv_agent")


# ---------------------------------------------------------------------------
# Capability-policy classification of analysis tools
# ---------------------------------------------------------------------------


class TestAnalysisCapabilityClassification:
    """The capability registry is the policy surface for analysis tools."""

    def _ensure_loaded(self):
        # The chat loop normally calls this once at startup; tests call it
        # explicitly so the registry is populated regardless of test order.
        from app.auth.tool_policy import tool_capability_policy

        tool_capability_policy.ensure_capabilities_loaded()
        return tool_capability_policy

    def test_run_analysis_is_read_only_after_declarative_replacement(self):
        from app.auth.tool_policy import CapabilityLevel

        policy = self._ensure_loaded()
        cap = policy.get("run_analysis")

        assert cap is not None
        assert cap.level is CapabilityLevel.READ_ONLY
        assert cap.requires_user_confirmation is False
        assert cap.audit_log is True
        assert cap.required_permission.category == "data_sources"
        assert cap.required_permission.item == "csv"

    def test_chat_list_analyzer_triggers_are_classified(self):
        # Every analyzer the chat surface might expose has to be in the
        # registry. Unclassified tools are always denied
        # (``is_exposable_for`` returns False), so a missing entry is
        # both a security risk (no audit_log enforcement) and a feature
        # break (the agent can never run). This is the load-bearing
        # invariant the registry was designed to enforce.
        policy = self._ensure_loaded()
        for tool in (
            "analyze_csv_agent",
            "analyze_database_agent",
            "analyze_freshdesk_agent",
        ):
            assert policy.has(tool), f"chat-list trigger {tool!r} unclassified"

    def test_analysis_internal_tools_are_classified(self):
        # The agent loops dispatch these tools internally. They are not on
        # the chat trigger list, but they still flow through the same
        # capability check when an executor wants to run them.
        policy = self._ensure_loaded()
        internal = (
            # CSV
            "run_analysis",
            "return_analysis",
            "csv_analyzer",
            "return_csv_summary",
            # database
            "query_runner",
            "schema_fetcher",
            "return_database_result",
            # freshdesk
            "freshdesk_query_runner",
            "freshdesk_schema_info",
            "return_ticket_analysis",
            # deep research
            "tavily_search_advance",
            "research_web_search",
            "write_research_to_file",
        )
        missing = [name for name in internal if not policy.has(name)]
        assert missing == [], (
            f"unclassified analysis tools after NBB-403 reorg: {missing}"
        )


# ---------------------------------------------------------------------------
