import pytest
from pydantic import ValidationError

from app.auth.contracts import AssetTokenPayload, MeResponse
from app.background.contracts import ActiveTask, ActiveTasksResponse
from app.chat.contracts import ChatStreamEvent, MessageContent
from app.projects.contracts import ProjectCostsResponse
from app.sources.contracts import CitationResponse, FileInfo
from app.sources.file_contract import get_file_info
from app.studio.contracts import StudioEventPayload, StudioJob


def test_auth_me_contract_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        MeResponse(
            auth_required=True,
            asset_token=None,
            user={
                "id": "user-1",
                "email": "user@example.com",
                "global_role": "user",
                "is_global_admin": False,
                "role": "owner",
                "is_admin": False,
                "is_authenticated": True,
            },
            workspace={
                "available_workspaces": [],
                "selected_workspace": None,
                "selected_workspace_id": None,
                "workspace_role": None,
                "can_manage_workspace": False,
                "can_create_project": False,
            },
        )


def test_asset_token_contract_rejects_wrong_scope() -> None:
    with pytest.raises(ValidationError):
        AssetTokenPayload(scope="session", version=1, user_id="user-1")


def test_chat_stream_contract_requires_event_payload_discriminants() -> None:
    assert ChatStreamEvent(event="ping", data={}).model_dump(mode="json") == {
        "event": "ping",
        "data": {},
    }

    with pytest.raises(ValidationError):
        ChatStreamEvent(event="assistant_delta", data={})

    with pytest.raises(ValidationError):
        ChatStreamEvent(event="ping", data={"delta": "not allowed"})


def test_message_content_contract_names_tool_block_discriminants() -> None:
    MessageContent.model_validate([
        {"type": "text", "text": "Let me search."},
        {
            "type": "tool_call",
            "call_id": "toolu_1",
            "name": "search_sources",
            "arguments": {"source_id": "src-1"},
            "provider_call_id": "toolu_1",
        },
        {
            "type": "tool_result",
            "call_id": "toolu_1",
            "name": "search_sources",
            "content": "result",
            "is_error": False,
        },
    ])

    with pytest.raises(ValidationError):
        MessageContent.model_validate([{"type": "unknown", "text": "x"}])


def test_citation_lookup_contract_shape_is_named() -> None:
    response = CitationResponse(
        chunk={
            "content": "Revenue grew.",
            "chunk_id": "src-1_page_5_chunk_2",
            "source_id": "src-1",
            "source_name": "Q3.pdf",
            "page_number": 5,
            "chunk_index": 2,
        },
    )

    assert response.model_dump(mode="json")["chunk"]["page_number"] == 5


def test_active_tasks_contract_rejects_unknown_task_type() -> None:
    ActiveTasksResponse(
        tasks=[
            ActiveTask(
                id="task-1",
                type="source",
                label="Q3.pdf",
                detail="Processing...",
                status="processing",
                created_at="2026-04-27T10:00:00Z",
            )
        ],
        count=1,
    )

    with pytest.raises(ValidationError):
        ActiveTask(
            id="task-2",
            type="worker",
            label="Job",
            detail="Processing...",
            status="running",
        )


def test_project_costs_contract_requires_stable_bucket_shape() -> None:
    response = ProjectCostsResponse(
        costs={
            "total_cost": 1.25,
            "by_model": {
                "anthropic:claude-sonnet-4-6": {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-6",
                    "input_tokens": 3,
                    "output_tokens": 4,
                    "cost": 0.2,
                },
                "openai:gpt-5-mini": {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "input_tokens": 5,
                    "output_tokens": 6,
                    "cost": 0.3,
                },
            },
        },
    )

    assert set(response.costs.by_model) == {
        "anthropic:claude-sonnet-4-6",
        "openai:gpt-5-mini",
    }

    with pytest.raises(ValidationError):
        ProjectCostsResponse(
            costs={"total_cost": 1.25, "by_model": {"openai:gpt-5-mini": {"input_tokens": 1}}},
        )


def test_source_file_info_contract_matches_file_contract() -> None:
    extension, category, mime_type = get_file_info("deck.pptx")
    assert FileInfo(
        extension=extension,
        category=category,
        mime_type=mime_type,
    ).model_dump(mode="json") == {
        "extension": ".pptx",
        "category": "document",
        "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }


def test_studio_contracts_reject_unknown_status() -> None:
    StudioJob(
        id="job-1",
        project_id="project-1",
        job_type="audio",
        status="processing",
        progress="Generating script...",
    )
    StudioEventPayload(studio_item="audio_overview", source_ids=["src-1"])

    with pytest.raises(ValidationError):
        StudioJob(id="job-2", status="waiting")
