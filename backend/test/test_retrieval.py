"""Behavior tests for the unified retrieval seam."""

from __future__ import annotations

import pytest

from agent.retrieval import (
    DashScopeSearchProvider,
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
