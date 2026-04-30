"""Provider-neutral model usage accounting for project and chat costs."""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any, Optional

from app.agents.runtime.contract import Usage
from app.config.model import get_model_info

logger = logging.getLogger(__name__)

_lock = Lock()


def _get_project_service():
    from app.projects.store import project_service

    return project_service


def _get_chat_service():
    from app.chat.store import chat_service

    return chat_service


def _empty_bucket(provider: str, model: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "provider_units": {},
        "cost": 0.0,
    }


def _legacy_provider_model(key: str) -> tuple[str, str]:
    if key in {"opus", "sonnet", "haiku"}:
        return "anthropic", key
    if ":" in key:
        provider, model = key.split(":", 1)
        return provider, model
    info = get_model_info(key)
    if info:
        return info.provider, info.id
    return "unknown", key


def _bucket_key(provider: str, model: str) -> str:
    return f"{provider}:{model}"


def _load_costs(project_id: str, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    try:
        project_service = _get_project_service()
        owner_id = user_id or project_service.get_project_owner_id(project_id)
        if not owner_id:
            return None
        return project_service.get_project_costs(project_id, user_id=owner_id)
    except Exception as exc:
        logger.error("Error loading costs for %s: %s", project_id, exc)
        return None


def _save_costs(
    project_id: str,
    costs: dict[str, Any],
    user_id: Optional[str] = None,
) -> bool:
    try:
        project_service = _get_project_service()
        owner_id = user_id or project_service.get_project_owner_id(project_id)
        if not owner_id:
            return False
        return project_service.update_project_costs(project_id, costs, user_id=owner_id)
    except Exception as exc:
        logger.error("Error saving costs for %s: %s", project_id, exc)
        return False


def _load_chat_costs(chat_id: str) -> Optional[dict[str, Any]]:
    try:
        return _get_chat_service().get_chat_costs_raw(chat_id)
    except Exception as exc:
        logger.error("Error loading costs for chat %s: %s", chat_id, exc)
        return None


def _save_chat_costs(chat_id: str, costs: dict[str, Any]) -> bool:
    try:
        return _get_chat_service().update_chat_costs(chat_id, costs)
    except Exception as exc:
        logger.error("Error saving costs for chat %s: %s", chat_id, exc)
        return False


def get_default_costs() -> dict[str, Any]:
    return {"total_cost": 0.0, "by_model": {}}


def ensure_cost_structure(costs: Optional[dict[str, Any]]) -> dict[str, Any]:
    if costs is None:
        return get_default_costs()

    total_cost = costs.get("total_cost", costs.get("total_cost_usd", 0.0))
    try:
        normalized_total = float(total_cost or 0.0)
    except (TypeError, ValueError):
        normalized_total = 0.0

    source_by_model = costs.get("by_model")
    if not isinstance(source_by_model, dict):
        source_by_model = {}

    by_model: dict[str, dict[str, Any]] = {}
    for key, bucket in source_by_model.items():
        if not isinstance(bucket, dict):
            bucket = {}
        provider, model = _legacy_provider_model(str(key))
        normalized_key = _bucket_key(provider, model)
        provider_units = bucket.get("provider_units")
        by_model[normalized_key] = {
            "provider": str(bucket.get("provider") or provider),
            "model": str(bucket.get("model") or model),
            "input_tokens": int(bucket.get("input_tokens") or 0),
            "output_tokens": int(bucket.get("output_tokens") or 0),
            "cache_creation_input_tokens": int(
                bucket.get("cache_creation_input_tokens") or 0
            ),
            "cache_read_input_tokens": int(bucket.get("cache_read_input_tokens") or 0),
            "provider_units": provider_units if isinstance(provider_units, dict) else {},
            "cost": float(bucket.get("cost") or 0.0),
        }

    return {"total_cost": normalized_total, "by_model": by_model}


def calculate_cost(provider: str, model: str, usage: Usage) -> float:
    info = get_model_info(model)
    if not info:
        return 0.0
    pricing = info.pricing
    cached_tokens = max(0, usage.cache_read_input_tokens)
    billable_input_tokens = max(0, usage.input_tokens - cached_tokens)
    input_cost = (billable_input_tokens / 1_000_000) * pricing.input_per_mtok
    cached_rate = pricing.cached_input_per_mtok
    cached_cost = (
        (cached_tokens / 1_000_000) * cached_rate
        if cached_rate is not None
        else (cached_tokens / 1_000_000) * pricing.input_per_mtok
    )
    output_cost = (usage.output_tokens / 1_000_000) * pricing.output_per_mtok
    return input_cost + cached_cost + output_cost


def _apply_usage(
    costs: dict[str, Any],
    *,
    provider: str,
    model: str,
    usage: Usage,
) -> float:
    key = _bucket_key(provider, model)
    bucket = costs["by_model"].setdefault(key, _empty_bucket(provider, model))
    call_cost = calculate_cost(provider, model, usage)

    bucket["provider"] = provider
    bucket["model"] = model
    bucket["input_tokens"] += usage.input_tokens
    bucket["output_tokens"] += usage.output_tokens
    bucket["cache_creation_input_tokens"] += usage.cache_creation_input_tokens
    bucket["cache_read_input_tokens"] += usage.cache_read_input_tokens
    bucket["cost"] += call_cost
    provider_units = dict(bucket.get("provider_units") or {})
    for unit, value in usage.provider_units.items():
        provider_units[unit] = provider_units.get(unit, 0) + value
    bucket["provider_units"] = provider_units
    costs["total_cost"] += call_cost
    return call_cost


def add_usage(
    *,
    project_id: str,
    provider: str,
    model: str,
    usage: Usage,
    requester_user_id: Optional[str] = None,
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    if usage.input_tokens <= 0 and usage.output_tokens <= 0 and not usage.provider_units:
        return None

    spend_user_id = requester_user_id if requester_user_id is not None else user_id
    with _lock:
        project_costs = ensure_cost_structure(_load_costs(project_id, user_id=None))
        call_cost = _apply_usage(
            project_costs,
            provider=provider,
            model=model,
            usage=usage,
        )
        if not _save_costs(project_id, project_costs, user_id=None):
            logger.warning("Failed to save costs for project %s", project_id)
            project_costs = None

        if chat_id:
            chat_costs = ensure_cost_structure(_load_chat_costs(chat_id))
            _apply_usage(chat_costs, provider=provider, model=model, usage=usage)
            if not _save_chat_costs(chat_id, chat_costs):
                logger.warning("Failed to save costs for chat %s", chat_id)

        resolved_user_id = spend_user_id
        if not resolved_user_id:
            try:
                resolved_user_id = _get_project_service().get_project_owner_id(project_id)
            except Exception:
                resolved_user_id = None
        record_user_period_spend(resolved_user_id, call_cost)
        return project_costs


def record_result_usage(
    *,
    project_id: Optional[str],
    provider: str,
    model: str,
    usage: Usage,
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> None:
    if not project_id:
        return
    add_usage(
        project_id=project_id,
        provider=provider,
        model=model,
        usage=usage,
        requester_user_id=user_id,
        chat_id=chat_id,
    )


def get_project_costs(
    project_id: str,
    user_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    return ensure_cost_structure(_load_costs(project_id, user_id=user_id))


def _is_period_expired(period_start: Optional[str], frequency: Optional[str]) -> bool:
    if not period_start or not frequency:
        return False
    from datetime import datetime, timedelta

    try:
        start = datetime.fromisoformat(period_start.replace("Z", "+00:00"))
        now = datetime.now(start.tzinfo) if start.tzinfo else datetime.utcnow()
        if frequency == "daily":
            return now >= start + timedelta(days=1)
        if frequency == "weekly":
            return now >= start + timedelta(weeks=1)
        if frequency == "monthly":
            return now >= start + timedelta(days=30)
        return False
    except Exception:
        return False


def check_user_spending_limit(user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    try:
        from app.auth.user.store import get_user_service
        from datetime import datetime

        svc = get_user_service()
        settings = svc.get_user_settings_raw(user_id)
        if not settings:
            return None
        cost_limit = settings.get("cost_limit")
        if cost_limit is None:
            return None
        reset_frequency = settings.get("reset_frequency")
        if reset_frequency:
            period_start = settings.get("period_start")
            period_spend = settings.get("period_spend", 0.0)
            if _is_period_expired(period_start, reset_frequency):
                settings["period_spend"] = 0.0
                settings["period_start"] = datetime.utcnow().isoformat() + "Z"
                svc.save_user_settings(user_id, settings)
                period_spend = 0.0
            if period_spend >= cost_limit:
                return (
                    f"You've reached your {reset_frequency} spending limit of "
                    f"${cost_limit:.2f}. Current period spend: ${period_spend:.2f}. "
                    "Contact your admin to increase it."
                )
        else:
            total_spend = svc.get_user_total_spend(user_id)
            if total_spend >= cost_limit:
                return (
                    f"You've reached your spending limit of ${cost_limit:.2f}. "
                    f"Current spend: ${total_spend:.2f}. Contact your admin to increase it."
                )
        return None
    except Exception as exc:
        logger.error("Error checking spending limit for %s: %s", user_id, exc)
        return None


def record_user_period_spend(user_id: Optional[str], call_cost: float) -> None:
    if not user_id or call_cost <= 0:
        return
    try:
        from app.auth.user.store import get_user_service

        get_user_service().increment_period_spend(user_id, call_cost)
    except Exception as exc:
        logger.error("Error recording period spend for %s: %s", user_id, exc)
