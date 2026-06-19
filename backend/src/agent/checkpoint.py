"""Checkpoint configuration for LangGraph task resume.

The production path uses Redis so a task can resume after process restarts.
Tests can set ``CHECKPOINT_BACKEND=none`` or ``memory`` to avoid external
dependencies.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from loguru import logger


def _enabled(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "off", "no"}


@lru_cache(maxsize=1)
def get_checkpointer() -> Any | None:
    """Create the configured LangGraph checkpointer.

    Supported backends:
    - ``redis``: durable checkpointing via ``langgraph-checkpoint-redis``.
    - ``memory``: process-local checkpointing for tests and local smoke runs.
    - ``none``: disables checkpointing.
    """
    if os.getenv("LANGSMITH_LANGGRAPH_API_VARIANT"):
        logger.info("[Checkpoint] disabled under LangGraph API runtime")
        return None

    backend = os.getenv("CHECKPOINT_BACKEND", "redis").strip().lower()

    if backend in {"", "none", "off", "disabled", "false", "0"}:
        logger.info("[Checkpoint] disabled")
        return None

    if backend == "memory":
        logger.info("[Checkpoint] using in-memory checkpointer")
        return InMemorySaver()

    if backend != "redis":
        raise ValueError(f"Unsupported CHECKPOINT_BACKEND={backend!r}")

    redis_url = os.getenv("CHECKPOINT_REDIS_URL") or os.getenv(
        "REDIS_URL",
        "redis://localhost:6379/0",
    )
    checkpoint_prefix = os.getenv("CHECKPOINT_PREFIX", "checkpoint")
    checkpoint_write_prefix = os.getenv("CHECKPOINT_WRITE_PREFIX", "checkpoint_write")

    try:
        from langgraph.checkpoint.redis import RedisSaver

        saver = RedisSaver(
            redis_url=redis_url,
            checkpoint_prefix=checkpoint_prefix,
            checkpoint_write_prefix=checkpoint_write_prefix,
        )
        saver.setup()
        logger.info(f"[Checkpoint] Redis checkpointer ready: {redis_url}")
        return saver
    except Exception as exc:
        if _enabled(os.getenv("CHECKPOINT_FALLBACK_TO_MEMORY"), default=True):
            logger.warning(
                "[Checkpoint] Redis unavailable "
                f"({type(exc).__name__}: {exc}); falling back to memory"
            )
            return InMemorySaver()
        raise


def make_thread_config(thread_id: str, **configurable: Any) -> dict:
    """Build a LangGraph config with a stable task/thread id."""
    if not thread_id or not thread_id.strip():
        raise ValueError("thread_id is required for checkpoint resume")
    return {
        "configurable": {
            "thread_id": thread_id.strip(),
            **configurable,
        }
    }
