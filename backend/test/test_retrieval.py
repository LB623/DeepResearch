"""Behavior tests for the unified retrieval seam."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agent.retrieval import (
    DashScopeSearchProvider,
    OmniSeekProtocolError,
    OmniSeekSearchProvider,
    SearchCoordinator,
    SearchHit,
)


class _FakeDashScopeAgent:
    async def astep(self, prompt: str, count: int):
        assert prompt == "agent memory"
        assert count == 2
        return [
            {
                "title": "Memory design",
                "snippet": "A durable state design.",
                "url": "https://example.com/memory",
            },
            {"title": "missing URL", "snippet": "ignored", "url": ""},
        ]


@pytest.mark.asyncio
async def test_dashscope_adapter_normalizes_legacy_pages():
    provider = DashScopeSearchProvider(agent_factory=_FakeDashScopeAgent)

    hits = await provider.search("agent memory", 2)

    assert hits == [
        SearchHit(
            title="Memory design",
            snippet="A durable state design.",
            url="https://example.com/memory",
            provider="dashscope",
        )
    ]
    assert hits[0].as_page() == {
        "title": "Memory design",
        "snippet": "A durable state design.",
        "url": "https://example.com/memory",
    }


class _StaticProvider:
    def __init__(self, name: str, hits: list[SearchHit]):
        self.name = name
        self._hits = hits

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        return self._hits


class _FailingProvider:
    name = "broken"

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        raise RuntimeError("private upstream detail")


@pytest.mark.asyncio
async def test_coordinator_deduplicates_and_isolates_provider_failure():
    primary = _StaticProvider(
        "primary",
        [
            SearchHit(
                title="Result",
                snippet="primary",
                url="HTTPS://Example.com/item/#section",
                provider="primary",
            )
        ],
    )
    secondary = _StaticProvider(
        "secondary",
        [
            SearchHit(
                title="Duplicate",
                snippet="secondary",
                url="https://example.com/item",
                provider="secondary",
            ),
            SearchHit(
                title="Additional",
                snippet="new",
                url="https://example.com/additional",
                provider="secondary",
            ),
        ],
    )
    coordinator = SearchCoordinator([primary, secondary, _FailingProvider()])

    batch = await coordinator.search("topic", 5)

    assert [hit.title for hit in batch.hits] == ["Result", "Additional"]
    assert batch.providers_attempted == ("primary", "secondary", "broken")
    assert [(failure.provider, failure.error_type) for failure in batch.failures] == [
        ("broken", "RuntimeError")
    ]
    assert "private upstream detail" not in repr(batch.failures)


def test_coordinator_requires_a_real_adapter():
    try:
        SearchCoordinator([])
    except ValueError as exc:
        assert str(exc) == "at least one search provider is required"
    else:
        raise AssertionError("empty provider list must be rejected")


@pytest.mark.asyncio
async def test_omniseek_adapter_calls_ranked_search_with_bounded_arguments():
    calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(name: str, arguments: dict[str, object]):
        calls.append((name, arguments))
        return SimpleNamespace(
            isError=False,
            structuredContent={
                "documents": [
                    {
                        "title": "Agent paper",
                        "content": "evidence",
                        "url": "https://example.com/paper",
                        "source": "arxiv",
                    }
                ]
            },
            content=[],
        )

    provider = OmniSeekSearchProvider(
        endpoint="http://127.0.0.1:8765/mcp",
        token="a-secure-token-value",
        sources=["arxiv", "openalex"],
        wait_seconds=99,
        tool_caller=call_tool,
    )

    hits = await provider.search("agent architecture", 100)

    assert calls == [
        (
            "omniseek_search",
            {
                "query": "agent architecture",
                "limit": 50,
                "raw": False,
                "wait_s": 15.0,
                "staleness": "cached_ok",
                "sources": ["arxiv", "openalex"],
                "semantic": False,
            },
        )
    ]
    assert hits == [
        SearchHit(
            title="Agent paper",
            snippet="evidence",
            url="https://example.com/paper",
            provider="omniseek",
            source="arxiv",
        )
    ]


@pytest.mark.asyncio
async def test_omniseek_adapter_accepts_json_text_content():
    async def call_tool(name: str, arguments: dict[str, object]):
        payload = {
            "documents": [
                {
                    "title": "Forum answer",
                    "content": "full answer",
                    "url": "https://example.com/forum",
                    "source": "v2ex",
                }
            ]
        }
        return SimpleNamespace(
            isError=False,
            structuredContent=None,
            content=[SimpleNamespace(text=json.dumps(payload))],
        )

    provider = OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    )

    hits = await provider.search("forum topic", 5)

    assert hits[0].source == "v2ex"


@pytest.mark.asyncio
async def test_omniseek_adapter_returns_only_safe_protocol_errors():
    async def call_tool(name: str, arguments: dict[str, object]):
        return SimpleNamespace(
            isError=True,
            structuredContent=None,
            content=[SimpleNamespace(text="private upstream failure")],
        )

    provider = OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    )

    with pytest.raises(OmniSeekProtocolError) as captured:
        await provider.search("sensitive query", 5)

    assert str(captured.value) == "omniseek tool call failed"
    assert "private upstream failure" not in str(captured.value)


@pytest.mark.parametrize(
    ("endpoint", "token", "message"),
    [
        ("ftp://localhost/mcp", "a-secure-token-value", "valid HTTP URL"),
        ("http://user:pass@localhost/mcp", "a-secure-token-value", "must not contain credentials"),
        ("http://localhost/mcp?token=secret", "a-secure-token-value", "query or fragment"),
        ("http://localhost/mcp", "short", "at least 16 characters"),
    ],
)
def test_omniseek_adapter_rejects_unsafe_configuration(endpoint, token, message):
    with pytest.raises(ValueError, match=message):
        OmniSeekSearchProvider(endpoint=endpoint, token=token)
