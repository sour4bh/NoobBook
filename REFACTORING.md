# Refactoring Guide (Historical)

> **Status: legacy / migration source.** This file was written against the previous mechanism-first backend layout. During the current structure migration, `ai_agents/`, `ai_services/`, `tool_executors/`, `services/tools/`, `utils/`, and `data/prompts/` are **legacy/migration sources, not preferred homes for new work**. New code must not default there. See [`STRUCTURE.md`](STRUCTURE.md) for the active placement rules and the reviewer placement checklist, and `docs/tickets/epics/NBB-001.md` for the migration plan.
>
> The sections below are retained as historical record of how that earlier taxonomy was organized and which services were refactored under it. Do not treat the prescriptive language below ("should contain", "move to", "refactor into") as current guidance — it describes the old shape.

## Historical Backend Service Taxonomy

Under the previous layout, backend Claude-API integrations were organized into three buckets:

```
ai_agents/          → Orchestration (the "brain")
ai_services/        → Single-purpose AI functions (the "skills")
tool_executors/     → Tool execution logic (the "hands")
```

This taxonomy is superseded. New work should live under domain-owned directories per `STRUCTURE.md`. Existing modules continue to live in these buckets until the relevant migration tickets drain them (`NBB-003` for chat, `NBB-004` for sources, `NBB-005` for studio, `NBB-705A` through `NBB-705E` for utility drains).

---

## Historical Pattern (superseded by `STRUCTURE.md`)

### ai_agents/ - Orchestration (historical)

**Purpose under the old layout:** run the agentic loop, manage messages, decide what to do next.

Contained:
- Message loop (user → Claude → tool → Claude → ...)
- Stop conditions (termination tool, max iterations)
- Message serialization
- Execution logging

Did not contain:
- Tool execution logic
- File I/O operations
- External API calls
- Business logic

```python
# GOOD under the old layout: agent delegates to executor
result = some_executor.execute_tool(tool_name, tool_input, project_id)

# BAD under the old layout: agent does the work itself
if tool_name == "create_file":
    with open(file_path, 'w') as f:
        f.write(content)
```

---

### ai_services/ - Single-Purpose AI Functions (historical)

**Purpose under the old layout:** one AI call, one job, returns a result.

Contained:
- Single Claude API call
- Prompt construction
- Response parsing
- Structured return

Did not contain:
- Loops or iterations
- Multiple API calls
- Tool handling
- State management

```python
# GOOD under the old layout: single purpose
def extract_pdf_page(page_bytes, page_num) -> Dict:
    response = claude_service.send_message(...)
    return parse_extraction(response)

# BAD under the old layout: does too much
def process_entire_pdf(pdf_path) -> Dict:
    for page in pages:
        # multiple calls, loops, state...
```

---

### tool_executors/ - Tool Execution (historical)

**Purpose under the old layout:** execute a tool, handle the messy details, return a clean result.

Contained:
- Tool-specific logic
- File operations
- External API calls
- Error handling
- Result formatting

Did not contain:
- Claude API calls
- Message management
- Loop logic

```python
# GOOD under the old layout: executor handles details
class WebsiteToolExecutor:
    def execute(self, tool_name, tool_input, context):
        if tool_name == "create_file":
            return self._create_file(tool_input, context)

    def _create_file(self, tool_input, context):
        # All the file I/O, validation, placeholder replacement...
        return {"success": True, "message": "File created"}
```

---

## Historical Refactoring Checklist (superseded)

The old within-bucket refactoring convention was:

1. Identify tool handlers (any `if tool_name == "xyz":` block with >5 lines).
2. Extract the logic into an executor under `tool_executors/{agent}_executor.py`.
3. Let the agent call the executor: `result = executor.execute_tool(name, input, context)`.
4. Executor returns a dict the agent can use.

This local cleanup is superseded by the domain-first migration. Do not author new agents/services/executors into those bucket paths; follow `STRUCTURE.md` and the owning migration ticket instead.

---

## Historical Goal (recorded)

**Before the old cleanup:** 760-line agent with everything mixed in.

**After the old cleanup:**
- 150-line agent (orchestration only)
- 200-line executor (tool logic)
- Clear separation within the old bucket taxonomy.

This shape is preserved by existing modules but is not the target architecture going forward. The target architecture is defined in `STRUCTURE.md` and `NBB-104`.

---

## Refactored Agents (historical record)

| Agent | Before | After | Executor | Status |
|-------|--------|-------|----------|--------|
| `blog_agent_service.py` | 534 lines | 202 lines | `blog_tool_executor.py` (232 lines) | Done |
| `website_agent_service.py` | 760 lines | 197 lines | `website_tool_executor.py` (338 lines) | Done |
| `business_report_agent_service.py` | 619 lines | 299 lines | `business_report_tool_executor.py` (280 lines) | Done |
| `marketing_strategy_agent_service.py` | 489 lines | 202 lines | `marketing_strategy_tool_executor.py` (230 lines) | Done |
| `component_agent_service.py` | 420 lines | 193 lines | `component_tool_executor.py` (175 lines) | Done |
| `email_agent_service.py` | 498 lines | 200 lines | `email_tool_executor.py` (260 lines) | Done |
| `prd_agent_service.py` | 489 lines | 205 lines | `prd_tool_executor.py` (250 lines) | Done |
| `presentation_agent_service.py` | 543 lines | 210 lines | `presentation_tool_executor.py` (300 lines) | Done |

---

## Refactored Services — Single AI Call (historical record)

| Service | Before | After | Moved To | Utils Extracted | Status |
|---------|--------|-------|----------|-----------------|--------|
| `wireframe_service.py` | 359 lines (studio_services/) | 173 lines | `ai_services/` | `excalidraw_utils.py` (120 lines) | Done |

---

## Shared Utilities (historical record)

| Utility | Location | Purpose | Used By |
|---------|----------|---------|---------|
| `get_source_content()` | `app/utils/source_content_utils.py` | Load source content with smart sampling for large sources | blog_agent, website_agent, wireframe_service, marketing_strategy_agent, component_agent, email_agent, prd_agent, presentation_agent |
| `get_source_name()` | `app/utils/source_content_utils.py` | Get source name by ID | (available) |
| `convert_to_excalidraw_elements()` | `app/utils/excalidraw_utils.py` | Convert simplified elements to Excalidraw format | wireframe_service |

Locations in the table reflect current on-disk paths during the migration. `app/utils/` is a frozen destination per `STRUCTURE.md`; these helpers will be drained to owning domains by `NBB-705A` through `NBB-705E`.

---

## Prompt Config Pattern (current project fact)

Prompt user messages and mappings live in prompt JSON configs rather than being hardcoded in agents. This is a useful pattern and remains accurate. Note that `data/prompts/` is frozen pending `NBB-207A` loader shims — do not add or move prompt JSON until those shims land, after which ownership follows `NBB-207B`.

```json
// data/prompts/{agent}_prompt.json
{
  "model": "claude-sonnet-4-5-20250929",
  "temperature": 0.6,
  "max_tokens": 16000,
  "user_message": "Create content based on:\n{source_content}\n\nDirection: {direction}",
  "some_types": {
    "type_a": "Display Name A",
    "type_b": "Display Name B"
  },
  "system_prompt": "..."
}
```

Agent usage (current mechanism):
```python
config = prompt_loader.get_prompt_config("agent_name")
user_message = config.get("user_message", "").format(
    source_content=source_content,
    direction=direction
)
```

---

## Historical Refactoring Steps (superseded)

The old per-service refactor recipe was:

1. Identify service type (agentic loop → `ai_agents/`, single AI call → `ai_services/`, non-AI → keep in place).
2. Replace duplicated utilities with shared helpers in `app/utils/`.
3. Externalize user messages and type mappings to prompt JSON.
4. Extract tool handlers into `tool_executors/{name}_executor.py` (agents only).
5. Update this file's tables.

This recipe is superseded. New refactors should follow the structure-migration tickets (`NBB-3xx`, `NBB-4xx`, `NBB-5xx`, `NBB-7xxx`) and the placement checklist in `STRUCTURE.md`. Do not create new files in `ai_agents/`, `ai_services/`, `tool_executors/`, or `utils/`.
