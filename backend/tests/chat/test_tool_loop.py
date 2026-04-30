"""
Chat tool contract tests (NBB-701).

Protect the chat tool loop's behavioral contracts after the NBB-301 / NBB-302 /
NBB-303 migration. The hard invariant pinned here is the one that, when broken
in production, corrupts every subsequent message in a chat: every persisted
`tool_call` content part in assistant turn N must be matched by a
`tool_result` content part with the same `call_id` in user turn N+1. The
Anthropic adapter turns those neutral parts into Claude `tool_use` /
`tool_result` blocks; an unmatched pair makes the provider call fail.

Coverage:

1. Tool availability — `ChatToolPolicy.select_tools` returns tools only when
   the per-source-type flag is set.
2. Permission filtering — `ToolCapabilityPolicy.is_exposable_for` gates every
   tool, with capability-aware fail-closed semantics inherited from NBB-202B.
3. Tool invocation/result shape — `chat.send` walks the agentic loop, calls
   the right executor, and persists a tool_call part followed by a matching
   tool_result.
4. Streaming behavior — `chat.stream` emits the 5-event catalog (NBB-205
   Contract 1) and the same persistence invariant holds.
5. Persistence interaction — recorded message rows survive a turn with the
   tool_call/tool_result pair colocated and one-to-one by `call_id`.
6. Hard invariant — pinned with multi-tool, single-tool, and executor-error
   paths, including parallel tool calls in one assistant turn.
7. Executor-error path — an executor exception still produces a matching
   `tool_result` content part with `is_error: True`, never a dropped pair.
8. Both public entrypoints — `chat.send` AND `chat.stream` exercise the same
   loop and pass the same invariants.
"""
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest
from pydantic import BaseModel, ConfigDict

from app.agents.runtime import (
    ProviderErrorInfo,
    ProviderRunError,
    RuntimeRunner,
    RunEvent,
    RunMessage,
    RunResult,
    ToolCallPart,
    ToolResultPart,
)
from app.agents.runtime.contract import final_event_data
from app.agents.runtime.tool import LocalToolSpec
from app.config.prompt import RenderedPrompt


PROJECT_ID = "00000000-0000-0000-0000-000000000000"
CHAT_ID = "00000000-0000-0000-0000-000000000001"
USER_ID = "00000000-0000-0000-0000-000000000099"


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        return str(tool.get("name") or "")
    return str(getattr(tool, "name", ""))


class AnyToolInput(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Recording fakes
# ---------------------------------------------------------------------------


class FakeMessageStore:
    """Capture every persistence call the chat loop makes for assertion.

    The real `MessageStore` wraps a Supabase client. We need to inspect what
    the loop *wrote* — not how Supabase serialized it — so this fake mirrors
    the four entry points the loop calls and stores the rows in a list. The
    tool_call/tool_result invariant is checked by walking the recorded rows.
    """

    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []
        self._ids = 0

    def _next_id(self) -> str:
        self._ids += 1
        return f"msg-{self._ids:03d}"

    def _normalize_content(self, content: Any) -> Any:
        if not isinstance(content, list):
            return content
        runtime_types = {"text", "tool_call", "tool_result", "provider_metadata"}
        if all(
            isinstance(part, dict) and part.get("type") in runtime_types
            for part in content
        ):
            return content

        converted: List[Dict[str, Any]] = []
        for block in content:
            block_type = getattr(block, "type", None)
            if isinstance(block, dict):
                block_type = block.get("type")
            if block_type == "text":
                text = block.get("text") if isinstance(block, dict) else block.text
                converted.append({"type": "text", "text": str(text or "")})
            elif block_type == "tool_use":
                call_id = block.get("id") if isinstance(block, dict) else block.id
                name = block.get("name") if isinstance(block, dict) else block.name
                args = block.get("input", {}) if isinstance(block, dict) else block.input
                converted.append(
                    {
                        "type": "tool_call",
                        "call_id": call_id,
                        "provider_call_id": call_id,
                        "name": name,
                        "arguments": args or {},
                    }
                )
        return converted

    def add_user_message(
        self, project_id: str, chat_id: str, content: str
    ) -> Dict[str, Any]:
        row = {
            "id": self._next_id(),
            "project_id": project_id,
            "chat_id": chat_id,
            "role": "user",
            "content": [{"type": "text", "text": content}],
        }
        self.rows.append(row)
        return row

    def add_message(
        self,
        *,
        project_id: str,
        chat_id: str,
        role: str,
        content: Any,
    ) -> Dict[str, Any]:
        row = {
            "id": self._next_id(),
            "project_id": project_id,
            "chat_id": chat_id,
            "role": role,
            "content": self._normalize_content(content),
        }
        self.rows.append(row)
        return row

    def add_tool_result_message(
        self,
        *,
        project_id: str,
        chat_id: str,
        call_id: str,
        result: Any,
        is_error: bool = False,
    ) -> Dict[str, Any]:
        content = [
            {
                "type": "tool_result",
                "call_id": call_id,
                "name": "",
                "content": str(result) if not isinstance(result, str) else result,
                "is_error": is_error,
            }
        ]
        row = {
            "id": self._next_id(),
            "project_id": project_id,
            "chat_id": chat_id,
            "role": "user",
            "content": content,
        }
        self.rows.append(row)
        return row

    def add_assistant_message(
        self,
        *,
        project_id: str,
        chat_id: str,
        content: str,
        model: Optional[str] = None,
        tokens: Optional[Dict[str, int]] = None,
        error: bool = False,
    ) -> Dict[str, Any]:
        row = {
            "id": self._next_id(),
            "project_id": project_id,
            "chat_id": chat_id,
            "role": "assistant",
            "content": [
                {"type": "text", "text": content},
                *(
                    [
                        {
                            "type": "provider_metadata",
                            "provider": "noobbook",
                            "values": {"error": True},
                        }
                    ]
                    if error
                    else []
                ),
            ],
            "model": model,
        }
        self.rows.append(row)
        return row

    def build_api_messages(
        self,
        project_id: str,
        chat_id: str,
        include_pending: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        # The loop only reads the result for forwarding to Claude (which the
        # tests mock), so the exact replay format is not load-bearing here.
        return [
            {"role": row["role"], "content": row["content"]}
            for row in self.rows
            if row["chat_id"] == chat_id
        ]

    def build_runtime_messages(
        self,
        project_id: str,
        chat_id: str,
        include_pending: Optional[Dict[str, Any]] = None,
    ) -> List[RunMessage]:
        messages = []
        for row in self.build_api_messages(project_id, chat_id, include_pending):
            content = row["content"]
            role = "tool" if self._is_tool_result_content(content) else row["role"]
            messages.append(RunMessage.model_validate({"role": role, "content": content}))
        return messages

    def _is_tool_result_content(self, content: Any) -> bool:
        return (
            isinstance(content, list)
            and bool(content)
            and all(
                isinstance(part, dict) and part.get("type") == "tool_result"
                for part in content
            )
        )


# ---------------------------------------------------------------------------
# Claude response builders
# ---------------------------------------------------------------------------


def _block(**kwargs: Any) -> SimpleNamespace:
    """Build a Claude content block with attribute-style access.

    Provider SDK objects expose attributes. The fake Anthropic adapter
    normalizer below accepts that shape so the tests stay aligned with what
    the loop actually sees.
    """
    return SimpleNamespace(**kwargs)


def _tool_use_response(
    tool_calls: List[Dict[str, Any]],
    *,
    text: str = "",
    model: str = "claude-sonnet-4-5-20250929",
) -> Dict[str, Any]:
    """A Claude response with tool_use blocks (and optional preamble text)."""
    blocks: List[SimpleNamespace] = []
    if text:
        blocks.append(_block(type="text", text=text, citations=None))
    for call in tool_calls:
        blocks.append(
            _block(
                type="tool_use",
                id=call["id"],
                name=call["name"],
                input=call.get("input", {}),
            )
        )
    return {
        "content_blocks": blocks,
        "stop_reason": "tool_use",
        "model": model,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def _final_response(
    text: str, *, model: str = "claude-sonnet-4-5-20250929"
) -> Dict[str, Any]:
    return {
        "content_blocks": [_block(type="text", text=text, citations=None)],
        "stop_reason": "end_turn",
        "model": model,
        "usage": {"input_tokens": 12, "output_tokens": 8},
    }


# ---------------------------------------------------------------------------
# Loop boundary patcher
# ---------------------------------------------------------------------------


def _patch_loop_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fake_store: FakeMessageStore,
    claude_responses: List[Dict[str, Any]],
    streamed_text_per_call: Optional[List[str]] = None,
    selected_tools: Tuple[List[Dict[str, Any]], Dict[str, Any]] = ([], {}),
    active_sources: Optional[List[Dict[str, Any]]] = None,
    tool_executor: Optional[Callable[..., str]] = None,
) -> Dict[str, List[Any]]:
    """Patch the seams the chat loop uses, returning a recording of calls.

    Patches `app.chat.loop` references (the loop holds module-local imports,
    so patching at the original module would not catch it). The model calls
    are intercepted at the provider-neutral runtime seam; the fake still uses
    the Anthropic adapter normalizer so the persisted contract is exercised
    through real runtime content parts.
    """
    from app.chat import loop as chat_loop_mod
    from app.providers.anthropic.adapter import anthropic_adapter
    from app.agents.runtime import bind_local_tools

    monkeypatch.setattr(chat_loop_mod, "message_service", fake_store)
    monkeypatch.setattr(
        chat_loop_mod.chat_service, "get_chat",
        lambda project_id, chat_id, **kwargs: {
            "id": chat_id,
            "project_id": project_id,
            "title": "test chat",
            "selected_source_ids": None,
            "message_count": 0,
        },
    )
    monkeypatch.setattr(
        chat_loop_mod,
        "get_project_custom_prompt",
        lambda project_id: "test system prompt",
    )
    monkeypatch.setattr(
        chat_loop_mod,
        "render_prompt",
        lambda *args, **kwargs: RenderedPrompt(
            name="default",
            provider="anthropic",
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            temperature=0.7,
            system_prompt="test system prompt",
        ),
    )
    monkeypatch.setattr(
        chat_loop_mod, "build_system_prompt",
        lambda *args, **kwargs: "test system prompt",
    )
    monkeypatch.setattr(
        chat_loop_mod.context_loader, "get_active_sources",
        lambda project_id, **kwargs: active_sources or [],
    )
    monkeypatch.setattr(
        chat_loop_mod.chat_tool_policy, "select_tools",
        lambda **kwargs: selected_tools,
    )
    monkeypatch.setattr(
        chat_loop_mod, "submit_naming_task",
        lambda *args, **kwargs: None,
    )
    calls: Dict[str, List[Any]] = {
        "send_message": [],
        "stream_message": [],
        "tool_executor": [],
    }

    response_iter = iter(claude_responses)
    streamed_iter = iter(streamed_text_per_call or [])
    synthetic_tools = _tool_specs_from_responses(claude_responses)
    policy_tools, policy_registry = selected_tools
    if not policy_tools and synthetic_tools:
        policy_tools = synthetic_tools
    monkeypatch.setattr(
        chat_loop_mod.chat_tool_policy,
        "select_tools",
        lambda **kwargs: (policy_tools, policy_registry),
    )

    def next_result(model: str) -> Any:
        response = next(response_iter)
        return anthropic_adapter.normalize_response(
            response,
            model_fallback=str(model or ""),
        )

    class FakeAdapter:
        def run_turn(self, request: Any) -> Any:
            calls["send_message"].append(request)
            return next_result(request.model)

        def stream_turn(self, request: Any):
            calls["stream_message"].append(request)
            result = next_result(request.model)
            try:
                text = next(streamed_iter)
            except StopIteration:
                text = ""
            if text:
                midpoint = len(text) // 2
                for chunk in (text[:midpoint], text[midpoint:]):
                    if chunk:
                        yield RunEvent(type="text_delta", data={"delta": chunk})
            yield RunEvent(type="final", data=final_event_data(result))

    def fake_run_with_provider(request: Any) -> Any:
        return RuntimeRunner().run(request, FakeAdapter())

    def fake_stream_with_provider(
        request: Any,
        *,
        on_text_delta: Optional[Callable[[str], None]] = None,
        on_event: Optional[Callable[[RunEvent], None]] = None,
    ) -> Any:
        return RuntimeRunner().stream(
            request,
            FakeAdapter(),
            on_text_delta=on_text_delta,
            on_event=on_event,
        )

    monkeypatch.setattr(chat_loop_mod, "run_with_provider", fake_run_with_provider)
    monkeypatch.setattr(chat_loop_mod, "stream_with_provider", fake_stream_with_provider)

    if tool_executor is not None:
        def fake_bind_chat_tools(
            tools: List[Any],
            *,
            project_id: str,
            chat_id: str,
            user_id: Optional[str],
            mcp_registry: Dict[str, Any],
        ) -> List[Any]:
            handlers: Dict[str, Callable[[BaseModel, Any], str]] = {}
            for tool in tools:
                tool_name = _tool_name(tool)

                def handler(
                    value: BaseModel,
                    _context: Any,
                    *,
                    name: str = tool_name,
                ) -> str:
                    tool_input = value.model_dump(mode="json")
                    calls["tool_executor"].append(
                        {
                            "project_id": project_id,
                            "chat_id": chat_id,
                            "tool_name": name,
                            "tool_input": tool_input,
                        }
                    )
                    return tool_executor(
                        None,
                        project_id,
                        chat_id,
                        name,
                        tool_input,
                        user_id=user_id,
                        mcp_registry=mcp_registry,
                    )

                handlers[tool_name] = handler

            return bind_local_tools(tools, handlers)

        monkeypatch.setattr(chat_loop_mod, "bind_chat_tools", fake_bind_chat_tools)

    return calls


def _tool_specs_from_responses(responses: List[Dict[str, Any]]) -> List[LocalToolSpec]:
    specs: List[LocalToolSpec] = []
    seen: set[str] = set()
    for response in responses:
        if response.get("stop_reason") != "tool_use":
            continue
        for block in response.get("content_blocks", []):
            if getattr(block, "type", None) != "tool_use":
                continue
            name = str(getattr(block, "name", ""))
            if not name or name in seen or name.startswith("absolutely_not_"):
                continue
            seen.add(name)
            specs.append(
                LocalToolSpec(
                    name=name,
                    description=f"Test tool {name}",
                    input_model=AnyToolInput,
                )
            )
    return specs


# ---------------------------------------------------------------------------
# Invariant helpers
# ---------------------------------------------------------------------------


def _assert_tool_pair_invariant(rows: List[Dict[str, Any]]) -> None:
    """Hard invariant: every tool_call is matched by a tool_result.

    Walks the recorded message rows in order. For each assistant row whose
    content is a list of parts, collect the `tool_call` ids. The very next
    user row must contain a `tool_result` part with the same `call_id` for
    every collected id, and no extras.
    """
    i = 0
    while i < len(rows):
        row = rows[i]
        if row["role"] != "assistant" or not isinstance(row["content"], list):
            i += 1
            continue
        tool_call_ids = [
            block["call_id"]
            for block in row["content"]
            if isinstance(block, dict) and block.get("type") == "tool_call"
        ]
        if not tool_call_ids:
            i += 1
            continue

        # Collect all subsequent user rows whose content is tool_result-only.
        # In production each tool result is one row (`add_tool_result_message`
        # takes a single call id), so multiple results live in consecutive
        # user rows after one assistant-with-tool_call row.
        result_ids: List[str] = []
        j = i + 1
        while j < len(rows):
            nxt = rows[j]
            if nxt["role"] != "user" or not isinstance(nxt["content"], list):
                break
            result_blocks = [
                block
                for block in nxt["content"]
                if isinstance(block, dict) and block.get("type") == "tool_result"
            ]
            if not result_blocks:
                break
            for block in result_blocks:
                result_ids.append(block["call_id"])
            j += 1

        assert sorted(tool_call_ids) == sorted(result_ids), (
            f"tool_call/tool_result pairing broken at row {i}: "
            f"tool_call ids={tool_call_ids}, tool_result ids={result_ids}"
        )
        i = j


# ===========================================================================
# Tool availability
# ===========================================================================


def test_select_tools_exposes_search_only_when_active_sources_present(
    monkeypatch: pytest.MonkeyPatch,
):
    """Search tool must not be sent to Claude when no active sources exist.

    Sending it anyway would prompt Claude to call a tool whose only valid
    inputs (source_ids) cannot exist; the executor would error out and the
    user would see a useless tool turn.
    """
    from app.chat.tool.policy import chat_tool_policy
    from app.auth.tool_policy import tool_capability_policy
    from app.chat.tool import policy as chat_tool_policy_mod

    # Stub out the policy decision so this unit test isolates `select_tools`.
    monkeypatch.setattr(
        tool_capability_policy, "ensure_capabilities_loaded", lambda: None
    )
    monkeypatch.setattr(
        tool_capability_policy, "is_exposable_for",
        lambda user_id, name: True,
    )
    # KB / MCP layers are out of scope for this assertion; return empty.
    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_jira_tools",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_mixpanel_tools",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_available_tools",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.mcp_tool_service, "get_available_tools",
        lambda **kwargs: ([], {}),
    )

    tools_no_sources, _ = chat_tool_policy.select_tools(
        has_active_sources=False, user_id=USER_ID
    )
    tools_with_sources, _ = chat_tool_policy.select_tools(
        has_active_sources=True, user_id=USER_ID
    )

    names_no_sources = {_tool_name(tool) for tool in tools_no_sources}
    names_with_sources = {_tool_name(tool) for tool in tools_with_sources}

    assert "search_sources" not in names_no_sources
    assert "search_sources" in names_with_sources
    # Memory and studio_signal are unconditional candidates per the policy
    # docstring; both turns must include them when permission allows.
    assert "store_memory" in names_no_sources
    assert "store_memory" in names_with_sources
    assert "studio_signal" in names_no_sources
    assert "studio_signal" in names_with_sources


def test_select_tools_exposes_csv_analyzer_only_for_csv_sources(
    monkeypatch: pytest.MonkeyPatch,
):
    """CSV analyzer is the per-source-kind gate that keeps the tool list short."""
    from app.chat.tool.policy import chat_tool_policy
    from app.auth.tool_policy import tool_capability_policy
    from app.chat.tool import policy as chat_tool_policy_mod

    monkeypatch.setattr(
        tool_capability_policy, "ensure_capabilities_loaded", lambda: None
    )
    monkeypatch.setattr(
        tool_capability_policy, "is_exposable_for",
        lambda user_id, name: True,
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_jira_tools",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_mixpanel_tools",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_available_tools",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.mcp_tool_service, "get_available_tools",
        lambda **kwargs: ([], {}),
    )

    tools_no_csv, _ = chat_tool_policy.select_tools(
        has_active_sources=True, has_csv_sources=False, user_id=USER_ID
    )
    tools_with_csv, _ = chat_tool_policy.select_tools(
        has_active_sources=False, has_csv_sources=True, user_id=USER_ID
    )

    assert "analyze_csv_agent" not in {_tool_name(tool) for tool in tools_no_csv}
    assert "analyze_csv_agent" in {_tool_name(tool) for tool in tools_with_csv}


# ===========================================================================
# Permission filtering (capability-aware exposure)
# ===========================================================================


def test_select_tools_respects_capability_policy_deny(
    monkeypatch: pytest.MonkeyPatch,
):
    """Capability-aware exposure must drop a denied tool from the per-turn list.

    Even when the per-source-kind flag says "yes," `is_exposable_for` is the
    final word — a permission that says no must keep the tool out of Claude's
    view.
    """
    from app.chat.tool.policy import chat_tool_policy
    from app.auth.tool_policy import tool_capability_policy
    from app.chat.tool import policy as chat_tool_policy_mod

    monkeypatch.setattr(
        tool_capability_policy, "ensure_capabilities_loaded", lambda: None
    )

    # Deny memory; allow everything else.
    def gate(user_id: Optional[str], name: str) -> bool:
        return name != "store_memory"

    monkeypatch.setattr(tool_capability_policy, "is_exposable_for", gate)
    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_jira_tools",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_mixpanel_tools",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_available_tools",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.mcp_tool_service, "get_available_tools",
        lambda **kwargs: ([], {}),
    )

    tools, _ = chat_tool_policy.select_tools(
        has_active_sources=True, user_id=USER_ID
    )
    names = {_tool_name(tool) for tool in tools}

    assert "store_memory" not in names
    assert "search_sources" in names  # control: other tools still pass


def test_select_tools_skips_unclassified_tools(monkeypatch: pytest.MonkeyPatch):
    """Hard rule from NBB-202B AC#3: unclassified tools never expose."""
    from app.chat.tool.policy import chat_tool_policy
    from app.auth.tool_policy import tool_capability_policy
    from app.chat.tool import policy as chat_tool_policy_mod

    # Use the real `is_exposable_for`, which returns False for unclassified.
    # But pretend a knowledge-base layer returns a tool that has no entry.
    tool_capability_policy.ensure_capabilities_loaded()

    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_jira_tools",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_mixpanel_tools",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_available_tools",
        lambda **_kwargs: [
            {"name": "totally_unclassified_tool", "description": "x",
             "input_schema": {"type": "object", "properties": {}}}
        ],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.mcp_tool_service, "get_available_tools",
        lambda **kwargs: ([], {}),
    )

    tools, _ = chat_tool_policy.select_tools(
        has_active_sources=True, user_id=USER_ID
    )
    names = {_tool_name(tool) for tool in tools}
    assert "totally_unclassified_tool" not in names


def test_select_tools_exposes_single_mcp_proxy_before_exposing(
    monkeypatch: pytest.MonkeyPatch,
):
    """MCP tools expose through one stable Pydantic proxy tool."""
    from app.chat.tool.policy import chat_tool_policy
    from app.auth.tool_policy import tool_capability_policy
    from app.chat.tool import policy as chat_tool_policy_mod
    from app.connectors.mcp.tools import MCP_PROXY_TOOL_NAME
    from app.agents.runtime.tool import McpProxyToolSpec

    tool_capability_policy.ensure_capabilities_loaded()
    # Snapshot+restore the registry so the synthesized MCP entry does not
    # bleed into sibling test files (notably `tests/auth/` which parametrizes
    # over `tool_capability_policy.all_names()`).
    monkeypatch.setattr(
        tool_capability_policy,
        "_entries",
        dict(tool_capability_policy._entries),
    )

    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_jira_tools",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_mixpanel_tools",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.knowledge_base_service, "get_available_tools",
        lambda **_kwargs: [],
    )

    proxy_tool = McpProxyToolSpec(
        name=MCP_PROXY_TOOL_NAME,
        description="Call MCP tool",
    )
    monkeypatch.setattr(
        chat_tool_policy_mod.mcp_tool_service, "get_available_tools",
        lambda **kwargs: ([proxy_tool], {"mcp_demo_search": {}}),
    )

    # Force the MCP capability path to allow exposure (mimic granted perm).
    original_is_exposable = tool_capability_policy.is_exposable_for

    def gate(user_id: Optional[str], name: str) -> bool:
        if name == MCP_PROXY_TOOL_NAME:
            # Synthesis must have registered the proxy entry before exposure.
            assert tool_capability_policy.has(name), (
                "MCP synthesis must register the proxy entry before "
                "the policy decision runs"
            )
            return True
        return original_is_exposable(user_id, name)

    monkeypatch.setattr(tool_capability_policy, "is_exposable_for", gate)

    tools, mcp_registry = chat_tool_policy.select_tools(
        has_active_sources=False, user_id=USER_ID
    )

    assert {MCP_PROXY_TOOL_NAME} & {_tool_name(tool) for tool in tools}
    assert "mcp_demo_search" in mcp_registry


# ===========================================================================
# Tool invocation/result shape — non-streaming (chat.send)
# ===========================================================================


def test_send_persists_matching_tool_call_and_tool_result(
    monkeypatch: pytest.MonkeyPatch,
):
    """The hard invariant on the non-streaming entrypoint.

    Drives `chat.send` through one tool round-trip: Claude requests
    `search_sources`, the executor returns a string, Claude follows up with
    end_turn text. After the turn, the persisted rows must contain a tool_call
    part followed by a matching tool_result part with the same id.
    """
    from app import chat as chat_pkg

    fake_store = FakeMessageStore()
    tool_call = {
        "id": "toolu_01AB",
        "name": "search_sources",
        "input": {"source_id": "src-1", "query": "what is x"},
    }
    responses = [
        _tool_use_response([tool_call], text="Let me look that up."),
        _final_response("The answer is x."),
    ]

    _patch_loop_boundaries(
        monkeypatch,
        fake_store=fake_store,
        claude_responses=responses,
        tool_executor=lambda *args, **kwargs: "search result body",
    )

    result = chat_pkg.send(PROJECT_ID, CHAT_ID, "what is x?", identity=None)

    assert result["user_message"]["content"] == [{"type": "text", "text": "what is x?"}]
    assert "answer is x" in result["assistant_message"]["content"][0]["text"]
    _assert_tool_pair_invariant(fake_store.rows)

    # The tool_call part is persisted as part of the assistant turn before the
    # tool_result. Walk the rows and check the exact ordering and shape.
    assistant_with_tool = next(
        row for row in fake_store.rows
        if row["role"] == "assistant" and isinstance(row["content"], list)
    )
    tool_call_part = next(
        block for block in assistant_with_tool["content"]
        if block.get("type") == "tool_call"
    )
    assert tool_call_part["call_id"] == "toolu_01AB"
    assert tool_call_part["name"] == "search_sources"
    assert tool_call_part["arguments"] == {"source_id": "src-1", "query": "what is x"}

    tool_result_row = next(
        row for row in fake_store.rows
        if row["role"] == "user" and isinstance(row["content"], list)
        and any(
            isinstance(b, dict) and b.get("type") == "tool_result"
            for b in row["content"]
        )
    )
    tool_result_block = tool_result_row["content"][0]
    assert tool_result_block["call_id"] == "toolu_01AB"
    assert tool_result_block["content"] == "search result body"
    assert tool_result_block["is_error"] is False


def test_send_handles_parallel_tool_calls_with_one_result_per_id(
    monkeypatch: pytest.MonkeyPatch,
):
    """Claude can request multiple tools in one assistant turn.

    Each `tool_call` id must end up paired with exactly one `tool_result`
    sharing that id. The pair count must be exact — duplicates or drops
    both break the API contract.
    """
    from app import chat as chat_pkg

    fake_store = FakeMessageStore()
    tool_calls = [
        {"id": "toolu_A", "name": "search_sources",
         "input": {"source_id": "s1", "query": "q1"}},
        {"id": "toolu_B", "name": "store_memory",
         "input": {"user_memory": "remember x", "why_generated": "user asked"}},
    ]
    responses = [
        _tool_use_response(tool_calls, text="Calling two tools."),
        _final_response("Done."),
    ]

    def fake_executor(self, project_id, chat_id, tool_name, tool_input,
                      user_id=None, mcp_registry=None):
        return f"{tool_name} ok"

    _patch_loop_boundaries(
        monkeypatch,
        fake_store=fake_store,
        claude_responses=responses,
        tool_executor=fake_executor,
    )

    chat_pkg.send(PROJECT_ID, CHAT_ID, "do two things", identity=None)

    _assert_tool_pair_invariant(fake_store.rows)

    # Exactly two tool_result rows, each with one of the two ids.
    result_blocks = [
        block
        for row in fake_store.rows
        if row["role"] == "user" and isinstance(row["content"], list)
        for block in row["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert sorted(b["call_id"] for b in result_blocks) == ["toolu_A", "toolu_B"]


def test_send_executor_error_persists_matching_tool_result_with_is_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """Executor exceptions must NOT drop the tool_call/tool_result pair.

    This is the regression that made an entire chat unrecoverable in
    production: a tool executor raised, the loop caught it, but the
    tool_result was never written, so every subsequent turn hit a provider
    400 error. The fix in `loop.py` wraps `_execute_tool` in try/except and
    always emits a tool_result with `is_error: True`. Pin that behavior.
    """
    from app import chat as chat_pkg

    fake_store = FakeMessageStore()
    tool_call = {
        "id": "toolu_ERR",
        "name": "search_sources",
        "input": {"source_id": "broken", "query": "q"},
    }
    responses = [
        _tool_use_response([tool_call], text="Trying."),
        _final_response("Could not retrieve."),
    ]

    def boom(self, *args, **kwargs):
        raise RuntimeError("simulated executor failure")

    _patch_loop_boundaries(
        monkeypatch,
        fake_store=fake_store,
        claude_responses=responses,
        tool_executor=boom,
    )

    chat_pkg.send(PROJECT_ID, CHAT_ID, "ask", identity=None)

    _assert_tool_pair_invariant(fake_store.rows)

    # The matching tool_result must carry `is_error: True` and the failure
    # text from the loop's catch handler, not a missing row.
    tool_result_blocks = [
        block
        for row in fake_store.rows
        if row["role"] == "user" and isinstance(row["content"], list)
        for block in row["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert len(tool_result_blocks) == 1
    err_block = tool_result_blocks[0]
    assert err_block["call_id"] == "toolu_ERR"
    assert err_block.get("is_error") is True
    assert "simulated executor failure" in err_block["content"]


def test_send_routes_search_sources_to_search_executor(
    monkeypatch: pytest.MonkeyPatch,
):
    """Without mocking the chat binding, drive a real route through the loop
    so the domain binding dispatch is exercised. The executor itself is mocked
    at its source module, which is the legitimate boundary.
    """
    from app import chat as chat_pkg
    from app.chat.tools import binding as chat_binding_mod

    fake_store = FakeMessageStore()
    captured: Dict[str, Any] = {}

    def fake_search(project_id, source_id, keywords=None, query=None):
        captured.update(
            project_id=project_id, source_id=source_id,
            keywords=keywords, query=query,
        )
        return {"success": True, "content": "from search executor"}

    monkeypatch.setattr(
        chat_binding_mod.source_search_executor, "search", fake_search
    )

    tool_call = {
        "id": "toolu_route",
        "name": "search_sources",
        "input": {"source_id": "s-9", "query": "q"},
    }
    responses = [
        _tool_use_response([tool_call]),
        _final_response("ok"),
    ]
    _patch_loop_boundaries(
        monkeypatch,
        fake_store=fake_store,
        claude_responses=responses,
        # tool_executor=None: do NOT replace the binding; we want the real
        # dispatch path to forward to `source_search_executor.search`.
    )

    chat_pkg.send(PROJECT_ID, CHAT_ID, "go", identity=None)

    assert captured == {
        "project_id": PROJECT_ID, "source_id": "s-9",
        "keywords": None, "query": "q",
    }
    _assert_tool_pair_invariant(fake_store.rows)
    # The forwarded result string must land in the persisted tool_result.
    result_block = next(
        block
        for row in fake_store.rows
        if row["role"] == "user" and isinstance(row["content"], list)
        for block in row["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    )
    assert result_block["content"] == "from search executor"


def test_send_routes_unknown_tool_to_unknown_message_without_dropping_pair(
    monkeypatch: pytest.MonkeyPatch,
):
    """Routing falls through to a string response for an unknown tool name.

    The loop must not raise — it must persist the unknown-tool message as
    the tool_result so the chat does not stall.
    """
    from app import chat as chat_pkg

    fake_store = FakeMessageStore()
    tool_call = {
        "id": "toolu_unknown",
        "name": "absolutely_not_a_real_tool",
        "input": {},
    }
    responses = [
        _tool_use_response([tool_call]),
        _final_response("Acknowledged."),
    ]
    _patch_loop_boundaries(
        monkeypatch,
        fake_store=fake_store,
        claude_responses=responses,
    )

    chat_pkg.send(PROJECT_ID, CHAT_ID, "ask", identity=None)

    _assert_tool_pair_invariant(fake_store.rows)
    result_block = next(
        block
        for row in fake_store.rows
        if row["role"] == "user" and isinstance(row["content"], list)
        for block in row["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    )
    assert "Unknown tool" in result_block["content"]
    assert result_block["call_id"] == "toolu_unknown"


# ===========================================================================
# Streaming behavior — chat.stream
# ===========================================================================


def test_stream_emits_five_event_catalog_with_tool_round_trip(
    monkeypatch: pytest.MonkeyPatch,
):
    """`chat.stream` must yield only the five frozen event names in order.

    Sequence on the success path: `user_message`, then a setup `ping`,
    ≥1 `assistant_delta`, finally `assistant_done`. The same
    tool_call/tool_result invariant holds on the streaming path.
    """
    from app import chat as chat_pkg
    from app.chat.schemas import CHAT_EVENT_NAMES

    fake_store = FakeMessageStore()
    tool_call = {
        "id": "toolu_stream",
        "name": "search_sources",
        "input": {"source_id": "s-1", "query": "q"},
    }
    responses = [
        _tool_use_response([tool_call]),
        _final_response("final answer"),
    ]
    streamed_text = ["", "final answer"]  # second turn streams text

    _patch_loop_boundaries(
        monkeypatch,
        fake_store=fake_store,
        claude_responses=responses,
        streamed_text_per_call=streamed_text,
        tool_executor=lambda *a, **kw: "stream search result",
    )

    events = list(chat_pkg.stream(PROJECT_ID, CHAT_ID, "ask", identity=None))
    event_names = [e["event"] for e in events]

    # Every emitted name must be in the frozen catalog.
    for name in event_names:
        assert name in CHAT_EVENT_NAMES, (
            f"event {name!r} not in frozen catalog {CHAT_EVENT_NAMES!r}"
        )

    # Required ordering: user_message first, ≥1 assistant_delta, then
    # assistant_done last. No `error` on the success path.
    assert event_names[0] == "user_message"
    assert "assistant_delta" in event_names
    assert event_names[-1] == "assistant_done"
    assert "error" not in event_names
    # Provider turn progress is owned by the runtime; chat emits one setup ping.
    assert event_names.count("ping") == 1

    # Streaming path must still pin the invariant.
    _assert_tool_pair_invariant(fake_store.rows)


def test_stream_tool_executor_error_emits_tool_result_and_assistant_done(
    monkeypatch: pytest.MonkeyPatch,
):
    """Executor exception on the streaming path must not drop the pair."""
    from app import chat as chat_pkg

    fake_store = FakeMessageStore()
    tool_call = {
        "id": "toolu_stream_err",
        "name": "search_sources",
        "input": {"source_id": "x", "query": "y"},
    }
    responses = [
        _tool_use_response([tool_call]),
        _final_response("Could not retrieve."),
    ]
    streamed_text = ["", "Could not retrieve."]

    def boom(self, *args, **kwargs):
        raise RuntimeError("stream-side simulated failure")

    _patch_loop_boundaries(
        monkeypatch,
        fake_store=fake_store,
        claude_responses=responses,
        streamed_text_per_call=streamed_text,
        tool_executor=boom,
    )

    events = list(chat_pkg.stream(PROJECT_ID, CHAT_ID, "ask", identity=None))
    event_names = [e["event"] for e in events]

    # Streaming finishes cleanly even though the tool raised — the loop
    # converts the exception into a tool_result and continues.
    assert event_names[-1] == "assistant_done"
    assert "error" not in event_names

    _assert_tool_pair_invariant(fake_store.rows)
    err_blocks = [
        block
        for row in fake_store.rows
        if row["role"] == "user" and isinstance(row["content"], list)
        for block in row["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert len(err_blocks) == 1
    assert err_blocks[0]["call_id"] == "toolu_stream_err"
    assert err_blocks[0].get("is_error") is True


def test_stream_emits_error_event_on_unknown_chat(
    monkeypatch: pytest.MonkeyPatch,
):
    """Streaming converts a `ValueError` from the loop into an `error` event.

    The `iter_chat_events` thread catches `ValueError` and pushes a final
    `error` event so the SSE consumer always sees a terminal frame even on
    a setup failure.
    """
    from app import chat as chat_pkg
    from app.chat import loop as chat_loop_mod
    from app.chat.schemas import CHAT_EVENT_NAMES

    monkeypatch.setattr(
        chat_loop_mod.chat_service, "get_chat",
        lambda project_id, chat_id, **kwargs: None,
    )

    events = list(chat_pkg.stream(PROJECT_ID, CHAT_ID, "ask", identity=None))
    assert len(events) == 1
    assert events[0]["event"] == "error"
    assert "error" in CHAT_EVENT_NAMES
    assert "Chat not found" in events[0]["data"]["message"]


# ===========================================================================
# Persistence interaction — recorded sequence shape
# ===========================================================================


def test_send_writes_user_then_assistant_tool_then_tool_result_then_assistant(
    monkeypatch: pytest.MonkeyPatch,
):
    """Pin the row ordering the loop produces.

    The required sequence per NBB-302's locked contract is:
    1. user (message text)
    2. assistant (tool_call, possibly with text)
    3. user (tool_result)
    4. assistant (final text)

    Regressions here would break provider replay because Anthropic enforces
    user/assistant alternation around tool blocks and OpenAI needs paired
    function-call output correlation.
    """
    from app import chat as chat_pkg

    fake_store = FakeMessageStore()
    tool_call = {
        "id": "toolu_order",
        "name": "search_sources",
        "input": {"source_id": "s", "query": "q"},
    }
    responses = [
        _tool_use_response([tool_call], text="Searching."),
        _final_response("Done."),
    ]

    _patch_loop_boundaries(
        monkeypatch,
        fake_store=fake_store,
        claude_responses=responses,
        tool_executor=lambda *a, **kw: "ok",
    )

    chat_pkg.send(PROJECT_ID, CHAT_ID, "ask", identity=None)

    role_seq = [row["role"] for row in fake_store.rows]
    assert role_seq == ["user", "assistant", "user", "assistant"], role_seq

    # The middle assistant row must contain a tool_call part; the middle user
    # row must contain a tool_result part.
    assert any(
        isinstance(b, dict) and b.get("type") == "tool_call"
        for b in fake_store.rows[1]["content"]
    )
    assert any(
        isinstance(b, dict) and b.get("type") == "tool_result"
        for b in fake_store.rows[2]["content"]
    )


def test_send_without_tool_use_writes_user_then_assistant_only(
    monkeypatch: pytest.MonkeyPatch,
):
    """Sanity: a turn with no tool calls writes exactly two rows.

    Asserts the loop does not invent tool_call/tool_result rounds when Claude
    returned a plain end_turn response.
    """
    from app import chat as chat_pkg

    fake_store = FakeMessageStore()
    responses = [_final_response("hello, plain answer")]

    _patch_loop_boundaries(
        monkeypatch,
        fake_store=fake_store,
        claude_responses=responses,
    )

    chat_pkg.send(PROJECT_ID, CHAT_ID, "hi", identity=None)

    role_seq = [row["role"] for row in fake_store.rows]
    assert role_seq == ["user", "assistant"]
    # No tool_call/tool_result parts anywhere.
    for row in fake_store.rows:
        if isinstance(row["content"], list):
            for block in row["content"]:
                assert block.get("type") not in ("tool_call", "tool_result")


def test_send_provider_error_persists_error_message_not_success_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    from app import chat as chat_pkg
    from app.chat import loop as chat_loop_mod

    fake_store = FakeMessageStore()
    _patch_loop_boundaries(
        monkeypatch,
        fake_store=fake_store,
        claude_responses=[],
    )
    monkeypatch.setattr(
        chat_loop_mod,
        "run_with_provider",
        lambda request: (_ for _ in ()).throw(RuntimeError("quota exceeded")),
    )

    response = chat_pkg.send(PROJECT_ID, CHAT_ID, "ask", identity=None)

    content = response["assistant_message"]["content"]
    assert content[0]["text"] == "Sorry, I encountered an error: quota exceeded"
    assert "I've processed your request." not in content[0]["text"]
    assert content[1]["values"] == {"error": True}


def test_send_provider_error_after_tools_persists_generated_transcript(
    monkeypatch: pytest.MonkeyPatch,
):
    from app import chat as chat_pkg
    from app.chat import loop as chat_loop_mod

    fake_store = FakeMessageStore()
    _patch_loop_boundaries(
        monkeypatch,
        fake_store=fake_store,
        claude_responses=[],
    )
    failed_result = RunResult(
        provider="openai",
        model="gpt-5.1",
        status="error",
        error="provider failed",
        error_info=ProviderErrorInfo(
            provider="openai",
            model="gpt-5.1",
            kind="server",
            message="provider failed",
            retryable=True,
        ),
        generated_messages=[
            RunMessage(
                role="assistant",
                content=[
                    ToolCallPart(
                        call_id="call-1",
                        name="search_sources",
                        arguments={"query": "x"},
                    )
                ],
            ),
            RunMessage(
                role="tool",
                content=[
                    ToolResultPart(
                        call_id="call-1",
                        name="search_sources",
                        content={"result": "x"},
                    )
                ],
            ),
        ],
    )
    error = ProviderRunError.from_result(failed_result)
    monkeypatch.setattr(
        chat_loop_mod,
        "run_with_provider",
        lambda request: (_ for _ in ()).throw(error),
    )

    response = chat_pkg.send(PROJECT_ID, CHAT_ID, "ask", identity=None)

    assert [row["role"] for row in fake_store.rows] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert fake_store.rows[1]["content"][0]["type"] == "tool_call"
    assert fake_store.rows[2]["content"][0]["type"] == "tool_result"
    assert response["assistant_message"]["content"][0]["text"] == (
        "OpenAI is having trouble. Please try again shortly."
    )
    assert response["assistant_message"]["content"][1]["values"] == {"error": True}


def test_stream_provider_error_emits_error_not_assistant_done(
    monkeypatch: pytest.MonkeyPatch,
):
    from app import chat as chat_pkg
    from app.chat import loop as chat_loop_mod

    fake_store = FakeMessageStore()
    _patch_loop_boundaries(
        monkeypatch,
        fake_store=fake_store,
        claude_responses=[],
    )
    monkeypatch.setattr(
        chat_loop_mod,
        "stream_with_provider",
        lambda request, **kwargs: (_ for _ in ()).throw(RuntimeError("quota exceeded")),
    )

    events = list(chat_pkg.stream(PROJECT_ID, CHAT_ID, "ask", identity=None))
    event_names = [event["event"] for event in events]

    assert event_names[-1] == "error"
    assert "assistant_done" not in event_names
    assert events[-1]["data"]["message"] == "quota exceeded"


def test_stream_provider_error_persists_already_emitted_partial_text(
    monkeypatch: pytest.MonkeyPatch,
):
    from app import chat as chat_pkg
    from app.chat import loop as chat_loop_mod

    fake_store = FakeMessageStore()
    _patch_loop_boundaries(
        monkeypatch,
        fake_store=fake_store,
        claude_responses=[],
    )

    def fail_after_delta(request, *, on_text_delta=None, **kwargs):
        if on_text_delta is not None:
            on_text_delta("partial answer")
        raise RuntimeError("connection dropped")

    monkeypatch.setattr(chat_loop_mod, "stream_with_provider", fail_after_delta)

    events = list(chat_pkg.stream(PROJECT_ID, CHAT_ID, "ask", identity=None))

    deltas = [event for event in events if event["event"] == "assistant_delta"]
    assert deltas[0]["data"]["delta"] == "partial answer"
    assert events[-1]["event"] == "error"
    error_message = fake_store.rows[-1]["content"][0]["text"]
    assert error_message.startswith("partial answer\n\nSorry, I encountered an error")
