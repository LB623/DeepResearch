"""Shared per-task budget accounting for every LLM-backed graph stage."""

from __future__ import annotations

import time
from typing import Any, Mapping

from langchain_core.runnables import RunnableConfig

from agent.configuration import Configuration

ELAPSED_TIME_LIMIT = "elapsed_time_limit"
TOKEN_LIMIT = "token_limit"
GLOBAL_BUDGET_STOP_REASONS = frozenset({ELAPSED_TIME_LIMIT, TOKEN_LIMIT})


def agent_total_tokens(agent: Any) -> int:
    """Return the last provider-reported token count for an Agent boundary."""
    usage = getattr(getattr(agent, "llm", None), "last_usage", {})
    total = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0
    return int(total) if isinstance(total, (int, float)) else 0


def budget_stop_reason(
    state: Mapping[str, Any],
    config: RunnableConfig,
    *,
    now: float | None = None,
) -> str:
    """Return the first exhausted persisted task budget, if any."""
    configurable = Configuration.from_runnable_config(config)
    current_time = time.time() if now is None else now
    started_at = float(state.get("run_started_at") or current_time)
    if current_time - started_at >= configurable.max_elapsed_seconds:
        return ELAPSED_TIME_LIMIT
    if int(state.get("llm_token_count", 0)) >= configurable.max_total_tokens:
        return TOKEN_LIMIT
    return ""


def is_global_budget_stop(state: Mapping[str, Any]) -> bool:
    return state.get("budget_stop_reason") in GLOBAL_BUDGET_STOP_REASONS


def usage_updates(
    state: Mapping[str, Any],
    config: RunnableConfig,
    agent: Any,
    *,
    started_at: float,
) -> dict[str, Any]:
    """Build reducer-safe state updates after one LLM call."""
    return token_usage_updates(
        state,
        config,
        agent_total_tokens(agent),
        started_at=started_at,
    )


def token_usage_updates(
    state: Mapping[str, Any],
    config: RunnableConfig,
    token_delta: int,
    *,
    started_at: float,
) -> dict[str, Any]:
    """Build reducer-safe state updates for one or more LLM calls."""
    candidate = {
        **state,
        "run_started_at": started_at,
        "llm_token_count": int(state.get("llm_token_count", 0)) + token_delta,
    }
    updates: dict[str, Any] = {
        "run_started_at": started_at,
        "llm_token_count": token_delta,
    }
    reason = budget_stop_reason(candidate, config)
    if reason:
        updates["budget_stop_reason"] = reason
    return updates
