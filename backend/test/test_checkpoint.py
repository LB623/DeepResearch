"""Tests for checkpoint configuration and resume semantics."""

from __future__ import annotations

import importlib
import operator
from typing import Annotated

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class _MiniState(TypedDict):
    events: Annotated[list[str], operator.add]
    fail_once: bool


def test_make_thread_config_requires_thread_id():
    from agent.checkpoint import make_thread_config

    with pytest.raises(ValueError):
        make_thread_config("")


def test_get_checkpointer_memory_backend(monkeypatch):
    from agent.checkpoint import get_checkpointer

    get_checkpointer.cache_clear()
    monkeypatch.setenv("CHECKPOINT_BACKEND", "memory")

    try:
        assert isinstance(get_checkpointer(), InMemorySaver)
    finally:
        get_checkpointer.cache_clear()


def test_get_checkpointer_disabled_backend(monkeypatch):
    from agent.checkpoint import get_checkpointer

    get_checkpointer.cache_clear()
    monkeypatch.setenv("CHECKPOINT_BACKEND", "none")

    try:
        assert get_checkpointer() is None
    finally:
        get_checkpointer.cache_clear()


def test_get_checkpointer_disabled_under_langgraph_api(monkeypatch):
    from agent.checkpoint import get_checkpointer

    get_checkpointer.cache_clear()
    monkeypatch.setenv("CHECKPOINT_BACKEND", "memory")
    monkeypatch.setenv("LANGSMITH_LANGGRAPH_API_VARIANT", "local_dev")

    try:
        assert get_checkpointer() is None
    finally:
        get_checkpointer.cache_clear()


def test_redis_backend_fails_closed_by_default(monkeypatch):
    """Redis Checkpoint 不可用时，默认不得伪装成持久化恢复。"""
    import langgraph.checkpoint.redis as redis_module

    from agent.checkpoint import get_checkpointer

    class BrokenRedisSaver:
        def __init__(self, **kwargs):
            raise ConnectionError("redis unavailable")

    get_checkpointer.cache_clear()
    monkeypatch.setenv("CHECKPOINT_BACKEND", "redis")
    monkeypatch.delenv("CHECKPOINT_FALLBACK_TO_MEMORY", raising=False)
    monkeypatch.delenv("LANGSMITH_LANGGRAPH_API_VARIANT", raising=False)
    monkeypatch.setattr(redis_module, "RedisSaver", BrokenRedisSaver)

    try:
        with pytest.raises(ConnectionError, match="redis unavailable"):
            get_checkpointer()
    finally:
        get_checkpointer.cache_clear()


def test_redis_backend_allows_explicit_memory_fallback(monkeypatch):
    """开发环境显式开启后，Redis 故障可以降级为内存 Checkpoint。"""
    import langgraph.checkpoint.redis as redis_module

    from agent.checkpoint import get_checkpointer

    class BrokenRedisSaver:
        def __init__(self, **kwargs):
            raise ConnectionError("redis unavailable")

    get_checkpointer.cache_clear()
    monkeypatch.setenv("CHECKPOINT_BACKEND", "redis")
    monkeypatch.setenv("CHECKPOINT_FALLBACK_TO_MEMORY", "1")
    monkeypatch.delenv("LANGSMITH_LANGGRAPH_API_VARIANT", raising=False)
    monkeypatch.setattr(redis_module, "RedisSaver", BrokenRedisSaver)

    try:
        assert isinstance(get_checkpointer(), InMemorySaver)
    finally:
        get_checkpointer.cache_clear()


def test_redis_credentials_are_not_logged(monkeypatch):
    import io

    import langgraph.checkpoint.redis as redis_module
    from loguru import logger

    from agent.checkpoint import get_checkpointer

    class ReadyRedisSaver:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def setup(self):
            return None

    get_checkpointer.cache_clear()
    monkeypatch.setenv("CHECKPOINT_BACKEND", "redis")
    monkeypatch.setenv(
        "CHECKPOINT_REDIS_URL",
        "redis://user:super-secret-password@localhost:6379/0",
    )
    monkeypatch.delenv("LANGSMITH_LANGGRAPH_API_VARIANT", raising=False)
    monkeypatch.setattr(redis_module, "RedisSaver", ReadyRedisSaver)
    sink = io.StringIO()
    handler_id = logger.add(sink, format="{message}")

    try:
        assert get_checkpointer() is not None
    finally:
        logger.remove(handler_id)
        get_checkpointer.cache_clear()

    assert "super-secret-password" not in sink.getvalue()


def test_main_graph_uses_configured_checkpointer(monkeypatch):
    import agent.graph as graph_mod
    from agent.checkpoint import get_checkpointer

    get_checkpointer.cache_clear()
    monkeypatch.setenv("CHECKPOINT_BACKEND", "memory")

    try:
        reloaded = importlib.reload(graph_mod)
        assert isinstance(reloaded.graph.checkpointer, InMemorySaver)
    finally:
        monkeypatch.setenv("CHECKPOINT_BACKEND", "none")
        get_checkpointer.cache_clear()
        importlib.reload(graph_mod)


def test_failed_node_resumes_from_last_checkpoint():
    """A transient node failure should not rerun completed upstream nodes."""
    attempts = {"search": 0}

    def generate_queries(state: _MiniState) -> dict:
        return {"events": ["generate_queries"]}

    def web_search(state: _MiniState) -> dict:
        attempts["search"] += 1
        if attempts["search"] == 1:
            raise RuntimeError("transient web search failure")
        return {"events": ["web_search"]}

    builder = StateGraph(_MiniState)
    builder.add_node("generate_queries", generate_queries)
    builder.add_node("web_search", web_search)
    builder.add_edge(START, "generate_queries")
    builder.add_edge("generate_queries", "web_search")
    builder.add_edge("web_search", END)
    graph = builder.compile(checkpointer=InMemorySaver())

    config = {"configurable": {"thread_id": "resume-smoke"}}

    with pytest.raises(RuntimeError):
        graph.invoke({"events": [], "fail_once": True}, config=config)

    snapshot = graph.get_state(config)
    assert snapshot.next == ("web_search",)
    assert snapshot.values["events"] == ["generate_queries"]

    result = graph.invoke(None, config=config)

    assert result["events"] == ["generate_queries", "web_search"]
    assert attempts["search"] == 2
