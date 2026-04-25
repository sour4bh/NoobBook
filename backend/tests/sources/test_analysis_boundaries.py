"""
Source-analysis boundary tests (NBB-702).

NBB-203 already pins the env-gate behavior (``test_raw_analysis_gate.py``,
20 cases, all green). This file pins the *structural* boundaries that
NBB-403 reorganized: every analysis slice's public import path resolves,
and every chat-exposed analysis tool is classified in the
``tool_capability_policy`` registry.

The "tool_capabilities.py" docstring states the design intent verbatim:

    "the policy must still refuse to expose them without the matching
    permission so a regression in NBB-203 is caught at the policy layer
    too."

That is what these tests pin. They are deliberately not duplicating the
env-gate matrix already covered by NBB-203 — adding more env cases here
would only delay regression detection because the gate file runs first
in CI.

D-002 permanent raw-code replacement is explicitly out of scope per the
NBB-702 ticket spec; the tests below assert today's quarantine surface
only.
"""
import pytest


# ---------------------------------------------------------------------------
# Public import paths (post-NBB-403 reorganization)
# ---------------------------------------------------------------------------


class TestAnalysisModulePublicSurface:
    """Every analysis slice must be importable through its post-NBB-403 path.

    These imports are the seams downstream code (chat tools, processors,
    NBB-203 gate tests) reaches through. If a future cleanup ticket
    accidentally moves them, the chat tool registrations and the gate
    tests both break — but those break with confusing errors. Pinning
    them here surfaces the regression at its root.
    """

    def test_csv_run_module_exposes_gate_helpers(self):
        from app.sources.analysis.csv.run import (
            analysis_executor,
            raw_analysis_enabled,
            RAW_ANALYSIS_DISABLED_MESSAGE,
        )

        assert callable(raw_analysis_enabled)
        # The disabled message has to be a non-empty string and name both
        # NBB-203 and DEFERRED.md D-002 so an operator searching the logs
        # for either reference finds it.
        assert isinstance(RAW_ANALYSIS_DISABLED_MESSAGE, str)
        assert "NBB-203" in RAW_ANALYSIS_DISABLED_MESSAGE
        assert "D-002" in RAW_ANALYSIS_DISABLED_MESSAGE
        # The dispatcher entry point used by the chat loop.
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
    """The capability registry is the policy-layer backstop for NBB-203.

    The CSV analyzer's ``run_analysis`` tool runs model-written Python via
    ``exec()``. Two layers refuse to expose it without explicit opt-in:

    1. The env gate (NBB-203, covered by ``test_raw_analysis_gate.py``).
    2. The capability classification (this file): ``run_analysis`` is
       ``DESTRUCTIVE`` and ``requires_user_confirmation=True``.

    Either layer alone is fragile — pinning both makes a NBB-203
    regression visible at the policy boundary even if the env-gate code
    accidentally returns True.
    """

    def _ensure_loaded(self):
        # The chat loop normally calls this once at startup; tests call it
        # explicitly so the registry is populated regardless of test order.
        from app.auth.tool_policy import tool_capability_policy

        tool_capability_policy.ensure_capabilities_loaded()
        return tool_capability_policy

    def test_run_analysis_is_destructive_and_requires_confirmation(self):
        from app.auth.tool_policy import CapabilityLevel

        policy = self._ensure_loaded()
        cap = policy.get("run_analysis")

        assert cap is not None
        # Pin the classification fields the NBB-203 mitigation depends on.
        # If a future cleanup ticket downgrades the level or relaxes the
        # confirmation flag without updating NBB-702, this test breaks
        # before the change can ship.
        assert cap.level is CapabilityLevel.DESTRUCTIVE
        assert cap.requires_user_confirmation is True
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
# Boundary regression: NBB-203 quarantine survives NBB-403 reorganization
# ---------------------------------------------------------------------------


class TestQuarantineStructuralIntegrity:
    """Cross-check the env-gate's import contract.

    ``test_raw_analysis_gate.py`` already exercises the env-gate matrix
    (20 cases). This pinning covers a different failure mode: the env
    gate stays in place, but a future move splits the module so the
    agent and the executor disagree on the disabled message.
    """

    def test_agent_and_executor_share_the_disabled_message(self):
        # ``test_raw_analysis_gate.py`` already pins this for the existing
        # import paths. After NBB-403 the import path is
        # ``app.sources.analysis.csv.run`` (not the legacy executor path);
        # this test pins that the post-403 path still wires the message
        # constant identity — not just the value — between the agent and
        # the executor module.
        from app.sources.analysis.csv import run as run_module
        from app.sources.analysis.csv.agent import RAW_ANALYSIS_DISABLED_MESSAGE

        assert run_module.RAW_ANALYSIS_DISABLED_MESSAGE is RAW_ANALYSIS_DISABLED_MESSAGE
