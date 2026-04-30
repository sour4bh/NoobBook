"""Provider-neutral runtime cost accounting tests."""

import pytest

import app.agents.runtime.cost as cost_mod
from app.agents.runtime.contract import Usage
from app.agents.runtime.cost import (
    add_usage,
    calculate_cost,
    ensure_cost_structure,
    get_default_costs,
)


def test_calculate_cost_uses_provider_model_catalog() -> None:
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)

    assert calculate_cost("anthropic", "claude-sonnet-4-6", usage) == pytest.approx(18.0)
    assert calculate_cost("openai", "gpt-5-mini", usage) == pytest.approx(2.25)


def test_calculate_cost_accounts_for_cached_input_tokens() -> None:
    usage = Usage(
        input_tokens=1_000_000,
        output_tokens=0,
        cache_read_input_tokens=500_000,
    )

    assert calculate_cost("openai", "gpt-5-mini", usage) == pytest.approx(0.1375)


def test_default_costs_start_without_fixed_vendor_buckets() -> None:
    costs = get_default_costs()

    assert costs == {"total_cost": 0.0, "by_model": {}}


def test_ensure_cost_structure_preserves_provider_model_buckets() -> None:
    result = ensure_cost_structure(
        {
            "total_cost": 0.25,
            "by_model": {
                "openai:gpt-5-mini": {
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_input_tokens": 2,
                    "provider_units": {"reasoning_tokens": 1},
                    "cost": 0.25,
                }
            },
        }
    )

    bucket = result["by_model"]["openai:gpt-5-mini"]
    assert result["total_cost"] == 0.25
    assert bucket["provider"] == "openai"
    assert bucket["model"] == "gpt-5-mini"
    assert bucket["cache_read_input_tokens"] == 2
    assert bucket["provider_units"] == {"reasoning_tokens": 1}


def test_ensure_cost_structure_normalizes_legacy_claude_buckets() -> None:
    result = ensure_cost_structure(
        {
            "total_cost_usd": 0.18,
            "by_model": {
                "sonnet": {"input_tokens": 1000, "output_tokens": 2000, "cost": 0.18}
            },
        }
    )

    bucket = result["by_model"]["anthropic:sonnet"]
    assert result["total_cost"] == 0.18
    assert bucket["provider"] == "anthropic"
    assert bucket["model"] == "sonnet"
    assert bucket["input_tokens"] == 1000


def test_project_cost_write_uses_owner_identity_for_viewer_requester(monkeypatch) -> None:
    class FakeProjectService:
        def __init__(self) -> None:
            self.load_user_ids: list[str] = []
            self.save_user_ids: list[str] = []

        def get_project_owner_id(self, project_id: str) -> str:
            return "owner-user"

        def get_project_costs(self, project_id: str, user_id: str):
            self.load_user_ids.append(user_id)
            return {"total_cost": 0.0, "by_model": {}}

        def update_project_costs(self, project_id: str, costs, user_id: str) -> bool:
            self.save_user_ids.append(user_id)
            if user_id == "viewer-user":
                raise PermissionError("Project editor role required")
            return True

    fake_project_service = FakeProjectService()
    recorded_spend: list[tuple[str | None, float]] = []
    monkeypatch.setattr(cost_mod, "_get_project_service", lambda: fake_project_service)
    monkeypatch.setattr(
        cost_mod,
        "record_user_period_spend",
        lambda user_id, call_cost: recorded_spend.append((user_id, call_cost)),
    )

    add_usage(
        project_id="project-1",
        provider="openai",
        model="gpt-5-mini",
        usage=Usage(input_tokens=1_000, output_tokens=1_000),
        requester_user_id="viewer-user",
    )

    assert fake_project_service.load_user_ids == ["owner-user"]
    assert fake_project_service.save_user_ids == ["owner-user"]
    assert recorded_spend[0][0] == "viewer-user"
