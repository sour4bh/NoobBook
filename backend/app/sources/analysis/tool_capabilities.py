"""
ToolCapability declarations for source-analysis tools.

Analysis tools fan into the chat tool list (CSV/database/Freshdesk
analyzers) plus internal agent loops (research deep-dive, CSV table
analysis). They live next to their owning domain so movement tickets keep
tool classification with the code that actually implements them.

The ``run_analysis``/``return_analysis`` pair from the ``analysis_agent/``
family is read-only after NBB-907: the executor accepts only validated
declarative table operations, not arbitrary Python source.
"""
from app.auth.tool_policy import (
    CapabilityLevel,
    RequiredPermission,
    ToolCapability,
    ToolScope,
    tool_capability_policy,
)


# ---------------------------------------------------------------------------
# Chat-list analyzer triggers (entry points)
# ---------------------------------------------------------------------------

ANALYZE_CSV_AGENT = ToolCapability(
    name="analyze_csv_agent",
    owner="sources/analysis/csv/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="csv"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=True,
)

ANALYZE_DATABASE_AGENT = ToolCapability(
    name="analyze_database_agent",
    owner="sources/analysis/database/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="database"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

ANALYZE_FRESHDESK_AGENT = ToolCapability(
    name="analyze_freshdesk_agent",
    owner="sources/analysis/freshdesk/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="freshdesk"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)


# ---------------------------------------------------------------------------
# CSV agent internal tools
# ---------------------------------------------------------------------------

RUN_ANALYSIS = ToolCapability(
    name="run_analysis",
    owner="sources/analysis/csv/raw_tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="csv"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=True,
)

RETURN_ANALYSIS = ToolCapability(
    name="return_analysis",
    owner="sources/analysis/csv/raw_tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="csv"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=False,
)


# CSV summary helpers (csv_tool/) used by deterministic CSV processing.
# Filename is ``csv_analyser.json`` (British spelling) but the JSON
# ``name`` field is ``csv_analyzer`` (American spelling); the executor
# at ``csv_service.py:149`` dispatches on the JSON ``name``, so the
# registry key has to match.
CSV_ANALYZER = ToolCapability(
    name="csv_analyzer",
    owner="sources/analysis/csv/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="csv"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=False,
)

RETURN_CSV_SUMMARY = ToolCapability(
    name="return_csv_summary",
    owner="sources/analysis/csv/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="csv"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=False,
)


# ---------------------------------------------------------------------------
# Database agent internal tools
# ---------------------------------------------------------------------------

DB_QUERY_RUNNER = ToolCapability(
    name="query_runner",
    owner="sources/analysis/database/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="database"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

DB_SCHEMA_FETCHER = ToolCapability(
    name="schema_fetcher",
    owner="sources/analysis/database/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="database"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=False,
)

DB_RETURN_RESULT = ToolCapability(
    name="return_database_result",
    owner="sources/analysis/database/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="database"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=False,
)


# ---------------------------------------------------------------------------
# Freshdesk agent internal tools
# ---------------------------------------------------------------------------

# Freshdesk uses the same query-runner/schema-info pattern as the
# database agent. Tool names happen to overlap with database tools at
# the JSON level (different files, different categories), so we expose
# Freshdesk-suffixed names through registration. The agent calls the
# tools by their JSON ``name`` field, which we treat as the registry
# key. Inspect the JSONs for actual names — the agent loop loads them
# via ``tool_loader.load_tool``.

# Each Freshdesk tool JSON has a unique ``name`` (different from the
# database equivalents); register them as separate entries. We pick
# descriptive identifiers that match the JSON ``name`` keys.
FD_QUERY_RUNNER = ToolCapability(
    name="freshdesk_query_runner",
    owner="sources/analysis/freshdesk/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="freshdesk"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

FD_SCHEMA_INFO = ToolCapability(
    name="freshdesk_schema_info",
    owner="sources/analysis/freshdesk/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="freshdesk"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=False,
)

FD_RETURN_TICKET_ANALYSIS = ToolCapability(
    name="return_ticket_analysis",
    owner="sources/analysis/freshdesk/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="freshdesk"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=False,
)


# ---------------------------------------------------------------------------
# Deep research agent (analysis/research)
# ---------------------------------------------------------------------------

RESEARCH_TAVILY_SEARCH_ADVANCE = ToolCapability(
    name="tavily_search_advance",
    owner="sources/analysis/research/tools/",
    required_permission=RequiredPermission(
        category="document_sources", item="url_youtube"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=False,
)

RESEARCH_WEB_SEARCH = ToolCapability(
    name="research_web_search",
    owner="sources/analysis/research/tools/",
    required_permission=RequiredPermission(
        category="document_sources", item="url_youtube"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=False,
)

WRITE_RESEARCH_TO_FILE = ToolCapability(
    name="write_research_to_file",
    owner="sources/analysis/research/tools/",
    required_permission=RequiredPermission(
        category="document_sources", item="url_youtube"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.WRITE_CAPABLE,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=True,
)


_ANALYSIS_CAPABILITIES = (
    # chat-list triggers
    ANALYZE_CSV_AGENT,
    ANALYZE_DATABASE_AGENT,
    ANALYZE_FRESHDESK_AGENT,
    # csv agent
    RUN_ANALYSIS,
    RETURN_ANALYSIS,
    CSV_ANALYZER,
    RETURN_CSV_SUMMARY,
    # database agent
    DB_QUERY_RUNNER,
    DB_SCHEMA_FETCHER,
    DB_RETURN_RESULT,
    # freshdesk agent
    FD_QUERY_RUNNER,
    FD_SCHEMA_INFO,
    FD_RETURN_TICKET_ANALYSIS,
    # deep research
    RESEARCH_TAVILY_SEARCH_ADVANCE,
    RESEARCH_WEB_SEARCH,
    WRITE_RESEARCH_TO_FILE,
)


tool_capability_policy.register_many(_ANALYSIS_CAPABILITIES)
