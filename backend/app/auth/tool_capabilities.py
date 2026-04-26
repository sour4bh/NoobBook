"""
Central ToolCapability declarations for Claude-visible tools.

This module classifies every Claude-visible tool from the NBB-207C
inventory that does not have its own domain registration module.
Analysis tools register themselves under
``app.sources.analysis.tool_capabilities`` per guardrail #3 (entries
attach near tool-definition sites where the owning domain exists).
Connector entries (Jira, Notion, Mixpanel) live here for now because
``connectors/<name>/`` skeletons land in NBB-303 and per-connector
migration tickets; the ``owner`` field still records the eventual
domain path.

Source-processing tools (PDF/PPTX/image extraction, web_agent server
tools) and studio-agent internals (blog, presentation, wireframe,
component, website, etc.) are Claude-visible inside their own loops
rather than the chat tool list. Per the ticket scope they still need
classification, but enforcement at those sites is out of scope for
this ticket — only the chat caller-side gap is wired through
``tool_capability_policy.is_exposable_for`` in NBB-202B.
"""
from app.auth.tool_policy import (
    CapabilityLevel,
    RequiredPermission,
    ToolCapability,
    ToolScope,
    tool_capability_policy,
)


# ---------------------------------------------------------------------------
# Chat-orchestrator tools
# ---------------------------------------------------------------------------

# search_sources: hybrid search across project sources. Read-only over
# our own data; project-scoped because the source list is per-project.
# Permission category mirrors document-source access generically;
# individual document items are authorized inside the search executor
# when it touches a specific source.
SEARCH_SOURCES = ToolCapability(
    name="search_sources",
    owner="chat/tools/",
    required_permission=RequiredPermission(category="document_sources"),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=False,
)


# store_memory: persists user/project memory. Write-capable against
# our store; gated by the chat_features.memory permission item.
STORE_MEMORY = ToolCapability(
    name="store_memory",
    owner="chat/memory/tools/",
    required_permission=RequiredPermission(
        category="chat_features", item="memory"
    ),
    scope=ToolScope.GLOBAL,
    level=CapabilityLevel.WRITE_CAPABLE,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=True,
)


# save_memory: forced tool used by chat memory merge to persist the
# merged memory blob via the Haiku merge step. Same classification as
# ``store_memory`` — both write to ``users.memory`` / ``projects.memory``,
# both gate on ``chat_features.memory``. Distinct registry entry because
# the JSON ``name`` field is ``save_memory`` (the executor calls
# ``tool_choice={"type": "tool", "name": "save_memory"}``); registering
# both prevents an inventory hole when the merge path is exercised.
SAVE_MEMORY = ToolCapability(
    name="save_memory",
    owner="chat/memory/tools/",
    required_permission=RequiredPermission(
        category="chat_features", item="memory"
    ),
    scope=ToolScope.GLOBAL,
    level=CapabilityLevel.WRITE_CAPABLE,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=True,
)


# studio_signal: activates studio generation panels. Write-capable in
# the sense that it queues background tasks; gated by the studio
# category toggle (no specific item — the tool itself enables a
# group of items).
STUDIO_SIGNAL = ToolCapability(
    name="studio_signal",
    owner="studio/signal/tools/",
    required_permission=RequiredPermission(category="studio"),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.WRITE_CAPABLE,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=True,
)


# ---------------------------------------------------------------------------
# Connector tools (Jira, Notion, Mixpanel)
# ---------------------------------------------------------------------------

# Jira: read-only project/issue queries. Project-scoped because Jira
# tools are gated by an active .jira source; permission item maps to
# the data_sources.jira toggle so admins can disable Jira access
# without touching credentials.
JIRA_LIST_PROJECTS = ToolCapability(
    name="jira_list_projects",
    owner="connectors/jira/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="jira"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

JIRA_SEARCH_ISSUES = ToolCapability(
    name="jira_search_issues",
    owner="connectors/jira/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="jira"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

JIRA_GET_ISSUE = ToolCapability(
    name="jira_get_issue",
    owner="connectors/jira/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="jira"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

JIRA_GET_PROJECT = ToolCapability(
    name="jira_get_project",
    owner="connectors/jira/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="jira"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)


# Notion: read-only search/page/database queries. Global-scoped
# because Notion tools are added unconditionally when the integration
# is configured (no per-project source flag).
NOTION_SEARCH = ToolCapability(
    name="notion_search",
    owner="connectors/notion/tools/",
    required_permission=RequiredPermission(
        category="integrations", item="notion"
    ),
    scope=ToolScope.GLOBAL,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

NOTION_READ_PAGE = ToolCapability(
    name="notion_read_page",
    owner="connectors/notion/tools/",
    required_permission=RequiredPermission(
        category="integrations", item="notion"
    ),
    scope=ToolScope.GLOBAL,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

NOTION_GET_DATABASE_SCHEMA = ToolCapability(
    name="notion_get_database_schema",
    owner="connectors/notion/tools/",
    required_permission=RequiredPermission(
        category="integrations", item="notion"
    ),
    scope=ToolScope.GLOBAL,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

NOTION_QUERY_DATABASE = ToolCapability(
    name="notion_query_database",
    owner="connectors/notion/tools/",
    required_permission=RequiredPermission(
        category="integrations", item="notion"
    ),
    scope=ToolScope.GLOBAL,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)


# Mixpanel: analytics queries. Read-only against external API,
# project-scoped via the .mixpanel source flag. Permission item maps
# to data_sources.mixpanel.
MIXPANEL_LIST_EVENTS = ToolCapability(
    name="mixpanel_list_events",
    owner="connectors/mixpanel/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="mixpanel"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

MIXPANEL_QUERY_EVENTS = ToolCapability(
    name="mixpanel_query_events",
    owner="connectors/mixpanel/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="mixpanel"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

MIXPANEL_SEGMENTATION = ToolCapability(
    name="mixpanel_segmentation",
    owner="connectors/mixpanel/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="mixpanel"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

MIXPANEL_LIST_FUNNELS = ToolCapability(
    name="mixpanel_list_funnels",
    owner="connectors/mixpanel/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="mixpanel"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

MIXPANEL_QUERY_FUNNEL = ToolCapability(
    name="mixpanel_query_funnel",
    owner="connectors/mixpanel/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="mixpanel"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

MIXPANEL_RETENTION = ToolCapability(
    name="mixpanel_retention",
    owner="connectors/mixpanel/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="mixpanel"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)

MIXPANEL_JQL = ToolCapability(
    name="mixpanel_jql",
    owner="connectors/mixpanel/tools/",
    required_permission=RequiredPermission(
        category="data_sources", item="mixpanel"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)


# MCP: dynamic per-server tools. Each MCP connection registers its
# own tools at runtime; the policy uses a single sentinel entry that
# is consulted before exposing any MCP-sourced tool. Per-server tool
# names are matched at the call site through ``mcp_capability_for``
# below.
MCP_GENERIC = ToolCapability(
    name="mcp",
    owner="connectors/mcp/tools/",
    required_permission=RequiredPermission(
        category="integrations", item="mcp"
    ),
    scope=ToolScope.GLOBAL,
    level=CapabilityLevel.WRITE_CAPABLE,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=True,
)


def mcp_capability_for(tool_name: str) -> ToolCapability:
    """Return an MCP-tool capability synthesized from the generic entry.

    MCP tools are dynamic — every server's tool catalog differs — so we
    do not pre-register each one. The policy still must answer
    ``is_exposable_for`` for them, so this helper produces a per-name
    entry that mirrors the generic MCP classification. Callers register
    the synthesized entry just before exposing the tool.
    """
    return ToolCapability(
        name=tool_name,
        owner=MCP_GENERIC.owner,
        required_permission=MCP_GENERIC.required_permission,
        scope=MCP_GENERIC.scope,
        level=MCP_GENERIC.level,
        external_side_effects=MCP_GENERIC.external_side_effects,
        requires_user_confirmation=MCP_GENERIC.requires_user_confirmation,
        audit_log=MCP_GENERIC.audit_log,
    )


# ---------------------------------------------------------------------------
# Source-processing tools (Claude-visible inside source-processing loops)
# ---------------------------------------------------------------------------

# These tools are sent to Claude inside per-source extraction agents;
# they are not exposed by the chat ``_get_tools`` selection. They are
# classified here so the AC#1 inventory test passes; wiring enforcement
# into the source extractor loops is out of scope for NBB-202B.

PDF_EXTRACTION = ToolCapability(
    name="submit_page_extraction",
    owner="sources/pdf/tools/",
    required_permission=RequiredPermission(
        category="document_sources", item="pdf"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.WRITE_CAPABLE,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=False,
)

PPTX_EXTRACTION = ToolCapability(
    name="submit_slide_extraction",
    owner="sources/pptx/tools/",
    required_permission=RequiredPermission(
        category="document_sources", item="pptx"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.WRITE_CAPABLE,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=False,
)

IMAGE_EXTRACTION = ToolCapability(
    name="submit_image_extraction",
    owner="sources/image/tools/",
    required_permission=RequiredPermission(
        category="document_sources", item="image"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.WRITE_CAPABLE,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=False,
)


# Web agent (URL ingestion). ``web_search`` and ``web_fetch`` are
# Anthropic server-side tools; ``tavily_search`` is a client-executed
# fallback; ``return_search_result`` is the termination tool.
WEB_SEARCH = ToolCapability(
    name="web_search",
    owner="sources/link/tools/",
    required_permission=RequiredPermission(
        category="document_sources", item="url_youtube"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=False,
)

WEB_FETCH = ToolCapability(
    name="web_fetch",
    owner="sources/link/tools/",
    required_permission=RequiredPermission(
        category="document_sources", item="url_youtube"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=False,
)

TAVILY_SEARCH = ToolCapability(
    name="tavily_search",
    owner="sources/link/tools/",
    required_permission=RequiredPermission(
        category="document_sources", item="url_youtube"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=True,
    requires_user_confirmation=False,
    audit_log=False,
)

RETURN_SEARCH_RESULT = ToolCapability(
    name="return_search_result",
    owner="sources/link/tools/",
    required_permission=RequiredPermission(
        category="document_sources", item="url_youtube"
    ),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=False,
)


# ---------------------------------------------------------------------------
# Studio-agent internal tools
# ---------------------------------------------------------------------------

# Each studio agent runs its own Claude loop with its own tool set.
# These tools are not in the chat ``_get_tools`` list; classification
# satisfies AC#1 (inventory completeness). All studio tools share the
# studio category permission. The owning-domain path matches the
# NBB-207C decision map; per-item permission keys map to the studio
# taxonomy items declared in NBB-202A.

def _studio(name: str, owner: str, item: str) -> ToolCapability:
    """Internal helper for the dense studio classification block.

    Studio writes generated content into our store and produces files
    served to the user, so default to write-capable with audit logging
    disabled (per-item audit lives in the studio job tracker).
    """
    return ToolCapability(
        name=name,
        owner=owner,
        required_permission=RequiredPermission(
            category="studio", item=item
        ),
        scope=ToolScope.PROJECT,
        level=CapabilityLevel.WRITE_CAPABLE,
        external_side_effects=False,
        requires_user_confirmation=False,
        audit_log=False,
    )


# Documents (NBB-504)
PLAN_BLOG_POST = _studio(
    "plan_blog_post", "studio/documents/blog/tools/", "blogs"
)
WRITE_BLOG_POST = _studio(
    "write_blog_post", "studio/documents/blog/tools/", "blogs"
)
GENERATE_BLOG_IMAGE = _studio(
    "generate_blog_image", "studio/documents/blog/tools/", "blogs"
)
PLAN_BUSINESS_REPORT = _studio(
    "plan_business_report",
    "studio/documents/business_report/tools/",
    "business_reports",
)
WRITE_BUSINESS_REPORT = _studio(
    "write_business_report",
    "studio/documents/business_report/tools/",
    "business_reports",
)
ANALYZE_CSV_DATA = _studio(
    "analyze_csv_data",
    "studio/documents/business_report/tools/",
    "business_reports",
)
SEARCH_SOURCE_CONTENT = _studio(
    "search_source_content",
    "studio/documents/business_report/tools/",
    "business_reports",
)
PLAN_PRD = _studio(
    "plan_prd", "studio/documents/prd/tools/", "prds"
)
WRITE_PRD_SECTION = _studio(
    "write_prd_section", "studio/documents/prd/tools/", "prds"
)
PLAN_PRESENTATION = _studio(
    "plan_presentation",
    "studio/documents/presentation/tools/",
    "presentations",
)
CREATE_BASE_STYLES = _studio(
    "create_base_styles",
    "studio/documents/presentation/tools/",
    "presentations",
)
CREATE_SLIDE = _studio(
    "create_slide",
    "studio/documents/presentation/tools/",
    "presentations",
)
FINALIZE_PRESENTATION = _studio(
    "finalize_presentation",
    "studio/documents/presentation/tools/",
    "presentations",
)


# Marketing (NBB-505)
PLAN_EMAIL_TEMPLATE = _studio(
    "plan_email_template",
    "studio/marketing/email/tools/",
    "emails",
)
WRITE_EMAIL_CODE = _studio(
    "write_email_code",
    "studio/marketing/email/tools/",
    "emails",
)
GENERATE_EMAIL_IMAGE = _studio(
    "generate_email_image",
    "studio/marketing/email/tools/",
    "emails",
)
PLAN_MARKETING_STRATEGY = _studio(
    "plan_marketing_strategy",
    "studio/marketing/strategy/tools/",
    "marketing_strategies",
)
WRITE_MARKETING_SECTION = _studio(
    "write_marketing_section",
    "studio/marketing/strategy/tools/",
    "marketing_strategies",
)


# Design (NBB-506)
PLAN_COMPONENTS = _studio(
    "plan_components",
    "studio/design/component/tools/",
    "components",
)
WRITE_COMPONENT_CODE = _studio(
    "write_component_code",
    "studio/design/component/tools/",
    "components",
)
FLOW_DIAGRAM_TOOL = _studio(
    "generate_flow_diagram",
    "studio/design/flow_diagram/tools/",
    "flow_diagrams",
)
PLAN_WIREFRAME = _studio(
    "plan_wireframe",
    "studio/design/wireframe/tools/",
    "wireframes",
)
ADD_WIREFRAME_SECTION = _studio(
    "add_wireframe_section",
    "studio/design/wireframe/tools/",
    "wireframes",
)
FINALIZE_WIREFRAME = _studio(
    "finalize_wireframe",
    "studio/design/wireframe/tools/",
    "wireframes",
)
WIREFRAME_TOOL = _studio(
    "generate_wireframe",
    "studio/design/wireframe/tools/",
    "wireframes",
)
PLAN_WEBSITE = _studio(
    "plan_website",
    "studio/design/website/tools/",
    "websites",
)
CREATE_FILE = _studio(
    "create_file",
    "studio/design/website/tools/",
    "websites",
)
READ_FILE = _studio(
    "read_file",
    "studio/design/website/tools/",
    "websites",
)
INSERT_CODE = _studio(
    "insert_code",
    "studio/design/website/tools/",
    "websites",
)
UPDATE_FILE_LINES = _studio(
    "update_file_lines",
    "studio/design/website/tools/",
    "websites",
)
GENERATE_WEBSITE_IMAGE = _studio(
    "generate_website_image",
    "studio/design/website/tools/",
    "websites",
)
FINALIZE_WEBSITE = _studio(
    "finalize_website",
    "studio/design/website/tools/",
    "websites",
)


# Learning + media (NBB-507).
# Names follow the JSON ``name`` field (the value Claude actually sees
# in ``tool_choice``), not the file name. The learning JSONs are
# ``flash_cards_tool.json`` / ``mind_map_tool.json`` / ``quiz_tool.json``
# but their declared names are ``generate_*``.
FLASH_CARDS = _studio(
    "generate_flash_cards",
    "studio/learning/flash_card/tools/",
    "flash_cards",
)
MIND_MAP = _studio(
    "generate_mind_map",
    "studio/learning/mind_map/tools/",
    "mind_maps",
)
QUIZ = _studio(
    "generate_quiz",
    "studio/learning/quiz/tools/",
    "quizzes",
)
WRITE_SCRIPT_SECTION = _studio(
    "write_script_section",
    "studio/media/audio/tools/",
    "audio_overview",
)
READ_SOURCE_CONTENT = ToolCapability(
    # Studio invokes sources/content/tools/ via the sources public
    # surface; permission gate is document_sources at the category
    # level since the underlying source could be any type.
    name="read_source_content",
    owner="sources/content/tools/",
    required_permission=RequiredPermission(category="document_sources"),
    scope=ToolScope.PROJECT,
    level=CapabilityLevel.READ_ONLY,
    external_side_effects=False,
    requires_user_confirmation=False,
    audit_log=False,
)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

# Listed explicitly so adding a new entry forces an edit here. A
# silent collection-walk would let a new constant in this module slip
# through unregistered.
_CENTRAL_CAPABILITIES = (
    # chat orchestration
    SEARCH_SOURCES,
    STORE_MEMORY,
    SAVE_MEMORY,
    STUDIO_SIGNAL,
    # connectors
    JIRA_LIST_PROJECTS,
    JIRA_SEARCH_ISSUES,
    JIRA_GET_ISSUE,
    JIRA_GET_PROJECT,
    NOTION_SEARCH,
    NOTION_READ_PAGE,
    NOTION_GET_DATABASE_SCHEMA,
    NOTION_QUERY_DATABASE,
    MIXPANEL_LIST_EVENTS,
    MIXPANEL_QUERY_EVENTS,
    MIXPANEL_SEGMENTATION,
    MIXPANEL_LIST_FUNNELS,
    MIXPANEL_QUERY_FUNNEL,
    MIXPANEL_RETENTION,
    MIXPANEL_JQL,
    MCP_GENERIC,
    # sources processing (Claude-visible in agent loops)
    PDF_EXTRACTION,
    PPTX_EXTRACTION,
    IMAGE_EXTRACTION,
    WEB_SEARCH,
    WEB_FETCH,
    TAVILY_SEARCH,
    RETURN_SEARCH_RESULT,
    # studio agents
    PLAN_BLOG_POST,
    WRITE_BLOG_POST,
    GENERATE_BLOG_IMAGE,
    PLAN_BUSINESS_REPORT,
    WRITE_BUSINESS_REPORT,
    ANALYZE_CSV_DATA,
    SEARCH_SOURCE_CONTENT,
    PLAN_PRD,
    WRITE_PRD_SECTION,
    PLAN_PRESENTATION,
    CREATE_BASE_STYLES,
    CREATE_SLIDE,
    FINALIZE_PRESENTATION,
    PLAN_EMAIL_TEMPLATE,
    WRITE_EMAIL_CODE,
    GENERATE_EMAIL_IMAGE,
    PLAN_MARKETING_STRATEGY,
    WRITE_MARKETING_SECTION,
    PLAN_COMPONENTS,
    WRITE_COMPONENT_CODE,
    FLOW_DIAGRAM_TOOL,
    PLAN_WIREFRAME,
    ADD_WIREFRAME_SECTION,
    FINALIZE_WIREFRAME,
    WIREFRAME_TOOL,
    PLAN_WEBSITE,
    CREATE_FILE,
    READ_FILE,
    INSERT_CODE,
    UPDATE_FILE_LINES,
    GENERATE_WEBSITE_IMAGE,
    FINALIZE_WEBSITE,
    FLASH_CARDS,
    MIND_MAP,
    QUIZ,
    WRITE_SCRIPT_SECTION,
    READ_SOURCE_CONTENT,
)


tool_capability_policy.register_many(_CENTRAL_CAPABILITIES)
