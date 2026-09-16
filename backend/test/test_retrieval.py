"""Behavior tests for the unified retrieval seam."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import threading
from types import SimpleNamespace

import pytest

import agent.retrieval as retrieval_module
from agent.retrieval import (
    DashScopeSearchProvider,
    MediaAsset,
    OmniSeekProtocolError,
    OmniSeekSearchProvider,
    SearchCoordinator,
    SearchHit,
    SearchProviderUnavailable,
    load_omniseek_credentials,
)


class _FakeDashScopeAgent:
    def step(self, prompt: str, count: int):
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


def test_credentials_can_be_loaded_from_server_owned_json(monkeypatch, tmp_path):
    token_file = tmp_path / "omniseek_http.json"
    token_file.write_text('{"token": "a-secure-token-value"}', encoding="utf-8")
    token_file.chmod(0o600)
    monkeypatch.delenv("OMNISEEK_MCP_URL", raising=False)
    monkeypatch.delenv("OMNISEEK_TOKEN", raising=False)

    assert load_omniseek_credentials(default_token_file=token_file) == (
        "http://127.0.0.1:8765/mcp",
        "a-secure-token-value",
    )


def test_malformed_token_file_fails_closed(monkeypatch, tmp_path):
    token_file = tmp_path / "omniseek_http.json"
    token_file.write_text("not-json", encoding="utf-8")
    token_file.chmod(0o600)
    monkeypatch.delenv("OMNISEEK_TOKEN", raising=False)

    assert load_omniseek_credentials(default_token_file=token_file) is None


def test_unreadable_home_alias_fails_closed(monkeypatch):
    monkeypatch.setenv("OMNISEEK_TOKEN_FILE", "~definitely-no-such-user/token.json")

    assert load_omniseek_credentials() is None


@pytest.mark.asyncio
async def test_dashscope_none_is_a_provider_failure():
    class FailedAgent:
        def step(self, prompt: str, count: int):
            return None

    provider = DashScopeSearchProvider(agent_factory=FailedAgent)

    with pytest.raises(SearchProviderUnavailable):
        await provider.search("topic", 2)


@pytest.mark.asyncio
async def test_coordinator_calls_fallback_only_when_primary_has_no_hits():
    fallback_hit = SearchHit(
        title="Fallback",
        snippet="evidence",
        url="https://example.com/fallback",
        provider="fallback",
    )
    populated = _StaticProvider("primary", [fallback_hit])
    empty = _StaticProvider("empty", [])
    fallback = _StaticProvider("fallback", [fallback_hit])

    primary_batch = await SearchCoordinator(
        [populated],
        fallback_providers=[fallback],
    ).search("topic", 5)
    fallback_batch = await SearchCoordinator(
        [empty],
        fallback_providers=[fallback],
    ).search("topic", 5)

    assert primary_batch.providers_attempted == ("primary",)
    assert fallback_batch.providers_attempted == ("empty", "fallback")
    assert fallback_batch.hits == [fallback_hit]


@pytest.mark.asyncio
async def test_coordinator_bounds_a_hung_provider():
    class HungProvider:
        name = "hung"

        async def search(self, query: str, limit: int):
            await asyncio.Event().wait()

    batch = await SearchCoordinator(
        [HungProvider()],
        provider_timeout_seconds=0.01,
    ).search("topic", 5)

    assert batch.hits == []
    assert batch.failures[0].provider == "hung"
    assert batch.failures[0].error_type == "TimeoutError"


@pytest.mark.asyncio
async def test_dashscope_timeout_keeps_the_real_sync_call_in_its_capacity_slot(
    monkeypatch,
):
    started = threading.Event()
    release = threading.Event()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(retrieval_module, "_DASHSCOPE_EXECUTOR", executor)
    monkeypatch.setattr(
        retrieval_module,
        "_DASHSCOPE_SLOTS",
        threading.BoundedSemaphore(1),
    )

    class BlockingAgent:
        def step(self, prompt: str, count: int):
            del prompt, count
            started.set()
            release.wait(timeout=2)
            return []

    provider = DashScopeSearchProvider(agent_factory=BlockingAgent)
    try:
        batch = await SearchCoordinator(
            [provider],
            provider_timeout_seconds=0.01,
        ).search("topic", 5)
        assert started.is_set()
        assert batch.failures[0].error_type == "TimeoutError"

        with pytest.raises(SearchProviderUnavailable, match="concurrency limit"):
            await provider.search("another topic", 5)
    finally:
        release.set()
        executor.shutdown(wait=True)


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
                        "media": [
                            "https://cdn.example.com/figure-1.png",
                            {
                                "url": "https://cdn.example.com/demo.mp4",
                                "kind": "video",
                            },
                        ],
                        "metadata": {
                            "handles": {"transcribable": ["https://example.com/paper"]}
                        },
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
        max_results=7,
        tool_caller=call_tool,
    )

    hits = await provider.search("agent architecture", 100)

    assert calls == [
        (
            "omniseek_search",
            {
                "query": "agent architecture",
                "limit": 7,
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
            media=(
                MediaAsset(
                    url="https://cdn.example.com/figure-1.png",
                    kind="image",
                ),
                MediaAsset(
                    url="https://cdn.example.com/demo.mp4",
                    kind="video",
                ),
                MediaAsset(
                    url="https://example.com/paper",
                    kind="audio",
                ),
            ),
        )
    ]
    assert hits[0].as_page()["media"] == [
        {"url": "https://cdn.example.com/figure-1.png", "kind": "image"},
        {"url": "https://cdn.example.com/demo.mp4", "kind": "video"},
        {"url": "https://example.com/paper", "kind": "audio"},
    ]


@pytest.mark.asyncio
async def test_omniseek_adapter_marks_video_transcription_handles():
    async def call_tool(name: str, arguments: dict[str, object]):
        del name, arguments
        return SimpleNamespace(
            isError=False,
            structuredContent={
                "documents": [
                    {
                        "title": "Video evidence",
                        "content": "A source description.",
                        "url": "https://www.bilibili.com/video/BV1example",
                        "source": "bilibili",
                        "media": ["https://i.example.com/cover.jpg"],
                        "metadata": {
                            "handles": {
                                "transcribable": [
                                    "https://www.bilibili.com/video/BV1example"
                                ]
                            }
                        },
                    }
                ]
            },
            content=[],
        )

    hits = await OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    ).search("video topic", 5)

    assert hits[0].media == (
        MediaAsset(
            url="https://www.bilibili.com/video/BV1example",
            kind="video",
        ),
    )


@pytest.mark.asyncio
async def test_omniseek_adapter_routes_video_queries_to_usable_video_evidence():
    async def call_tool(name: str, arguments: dict[str, object]):
        assert name == "omniseek_search"
        routed_sources = arguments.get("sources")
        if not isinstance(routed_sources, list) or "bilibili" not in routed_sources:
            return SimpleNamespace(
                isError=False,
                structuredContent={"documents": []},
                content=[],
            )
        return SimpleNamespace(
            isError=False,
            structuredContent={
                "documents": [
                    {
                        "title": "Generic article thumbnail",
                        "content": "Related text without a playable video.",
                        "url": "https://example.com/article",
                        "source": "newsletter",
                        "media": ["https://cdn.example.com/thumbnail.jpg"],
                    },
                    {
                        "title": "Official robot demo",
                        "content": "The requested product demonstration.",
                        "url": "https://www.bilibili.com/video/BV1demo",
                        "source": "bilibili",
                        "media": ["https://cdn.example.com/cover.jpg"],
                        "metadata": {"handles": {"transcribable": True}},
                    },
                ]
            },
            content=[],
        )

    hits = await OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    ).search("Boston Dynamics official demo video", 5)

    assert [hit.title for hit in hits] == [
        "Official robot demo",
        "Generic article thumbnail",
    ]
    assert hits[0].media == (
        MediaAsset(
            url="https://www.bilibili.com/video/BV1demo",
            kind="video",
        ),
    )
    assert hits[1].media == ()


@pytest.mark.asyncio
async def test_omniseek_adapter_recognizes_video_pages_without_handles():
    async def call_tool(name: str, arguments: dict[str, object]):
        del name, arguments
        return SimpleNamespace(
            isError=False,
            structuredContent={
                "documents": [
                    {
                        "title": "Official robot demo",
                        "content": "The requested demonstration video.",
                        "url": "https://www.bilibili.com/video/BV1demo",
                        "source": "bilibili",
                        "media": ["https://cdn.example.com/cover.jpg"],
                    }
                ]
            },
            content=[],
        )

    hits = await OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    ).search("official robot demo video", 5)

    assert hits[0].media == (
        MediaAsset(
            url="https://www.bilibili.com/video/BV1demo",
            kind="video",
        ),
    )


@pytest.mark.asyncio
async def test_omniseek_adapter_does_not_treat_figure_product_name_as_image_intent():
    async def call_tool(name: str, arguments: dict[str, object]):
        del name, arguments
        return SimpleNamespace(
            isError=False,
            structuredContent={
                "documents": [
                    {
                        "title": "Figure 02 official demo",
                        "content": "A humanoid robot product demonstration.",
                        "url": "https://www.youtube.com/watch?v=figure02",
                        "source": "youtube",
                        "media": [
                            "https://cdn.example.com/thumbnail.jpg",
                            "https://cdn.example.com/demo.mp4",
                        ],
                    }
                ]
            },
            content=[],
        )

    hits = await OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    ).search("Figure 02 humanoid robot demo video", 5)

    assert hits[0].media == (
        MediaAsset(
            url="https://cdn.example.com/demo.mp4",
            kind="video",
        ),
        MediaAsset(
            url="https://www.youtube.com/watch?v=figure02",
            kind="video",
        ),
    )


@pytest.mark.asyncio
async def test_omniseek_adapter_retries_once_after_media_miss():
    calls = 0

    async def call_tool(name: str, arguments: dict[str, object]):
        nonlocal calls
        del name, arguments
        calls += 1
        documents = [
            {
                "title": "Text-only first pass",
                "content": "The source workers are still warming the cache.",
                "url": "https://example.com/first-pass",
                "source": "web",
            }
        ]
        if calls == 2:
            documents = [
                {
                    "title": "Official demo from warmed cache",
                    "content": "The requested robot demonstration.",
                    "url": "https://example.com/demo",
                    "source": "youtube",
                    "media": ["https://cdn.example.com/demo.mp4"],
                }
            ]
        return SimpleNamespace(
            isError=False,
            structuredContent={"documents": documents},
            content=[],
        )

    hits = await OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    ).search("official robot demo video", 5)

    assert calls == 2
    assert hits[0].title == "Official demo from warmed cache"
    assert hits[0].media[0].kind == "video"


@pytest.mark.asyncio
async def test_omniseek_adapter_caps_media_retry_by_total_request_timeout():
    calls = 0

    async def call_tool(name: str, arguments: dict[str, object]):
        nonlocal calls
        del name, arguments
        calls += 1
        await asyncio.sleep(1.9 if calls == 1 else 1.0)
        return SimpleNamespace(
            isError=False,
            structuredContent={
                "documents": [
                    {
                        "title": "Text evidence",
                        "content": "No media was ready before the deadline.",
                        "url": "https://example.com/text",
                        "source": "web",
                    }
                ]
            },
            content=[],
        )

    provider = OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        wait_seconds=0.1,
        request_timeout_seconds=2.1,
        tool_caller=call_tool,
    )
    started = asyncio.get_running_loop().time()

    hits = await provider.search("official robot demo video", 5)

    elapsed = asyncio.get_running_loop().time() - started
    assert calls == 2
    assert elapsed < 2.5
    assert hits[0].title == "Text evidence"


@pytest.mark.asyncio
async def test_omniseek_adapter_caps_initial_call_by_total_request_timeout():
    async def call_tool(name: str, arguments: dict[str, object]):
        del name, arguments
        await asyncio.sleep(3.0)
        return SimpleNamespace(
            isError=False,
            structuredContent={"documents": []},
            content=[],
        )

    provider = OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        wait_seconds=0.1,
        request_timeout_seconds=2.1,
        tool_caller=call_tool,
    )
    started = asyncio.get_running_loop().time()

    with pytest.raises(TimeoutError):
        await provider.search("official robot demo video", 5)

    elapsed = asyncio.get_running_loop().time() - started
    assert elapsed < 2.5


@pytest.mark.asyncio
async def test_omniseek_adapter_routes_chinese_audio_queries_to_audio_evidence():
    async def call_tool(name: str, arguments: dict[str, object]):
        assert name == "omniseek_search"
        routed_sources = arguments.get("sources")
        if not isinstance(routed_sources, list) or "xiaoyuzhou" not in routed_sources:
            return SimpleNamespace(
                isError=False,
                structuredContent={"documents": []},
                content=[],
            )
        return SimpleNamespace(
            isError=False,
            structuredContent={
                "documents": [
                    {
                        "title": "Agent 记忆访谈",
                        "content": "围绕 Agent 长期记忆的播客访谈。",
                        "url": "https://www.xiaoyuzhoufm.com/episode/example",
                        "source": "xiaoyuzhou",
                        "media": ["https://cdn.example.com/cover.jpg"],
                        "metadata": {"handles": {"transcribable": True}},
                    }
                ]
            },
            content=[],
        )

    hits = await OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    ).search("寻找 Agent 长期记忆相关的播客音频", 5)

    assert hits[0].media == (
        MediaAsset(
            url="https://www.xiaoyuzhoufm.com/episode/example",
            kind="audio",
        ),
    )


@pytest.mark.asyncio
async def test_omniseek_adapter_recognizes_audio_episode_pages_without_handles():
    async def call_tool(name: str, arguments: dict[str, object]):
        del name, arguments
        return SimpleNamespace(
            isError=False,
            structuredContent={
                "documents": [
                    {
                        "title": "Agent memory podcast",
                        "content": "An episode about long-term memory.",
                        "url": "https://www.xiaoyuzhoufm.com/episode/example",
                        "source": "xiaoyuzhou",
                        "media": ["https://cdn.example.com/cover.jpg"],
                    }
                ]
            },
            content=[],
        )

    hits = await OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    ).search("Agent memory podcast audio", 5)

    assert hits[0].media == (
        MediaAsset(
            url="https://www.xiaoyuzhoufm.com/episode/example",
            kind="audio",
        ),
    )


@pytest.mark.asyncio
async def test_omniseek_adapter_routes_image_queries_to_explicit_image_evidence():
    async def call_tool(name: str, arguments: dict[str, object]):
        assert name == "omniseek_search"
        assert arguments.get("semantic") is True
        routed_sources = arguments.get("sources")
        if not isinstance(routed_sources, list) or "qwen" not in routed_sources:
            return SimpleNamespace(
                isError=False,
                structuredContent={"documents": []},
                content=[],
            )
        return SimpleNamespace(
            isError=False,
            structuredContent={
                "documents": [
                    {
                        "title": "Official architecture figure",
                        "content": "The model architecture diagram.",
                        "url": "https://example.com/model-card",
                        "source": "qwen",
                        "media": [
                            {
                                "url": "https://cdn.example.com/asset?id=figure-1",
                                "kind": "image",
                            }
                        ],
                    },
                    {
                        "title": "Unrelated demo",
                        "content": "A video attachment.",
                        "url": "https://example.com/demo",
                        "source": "qwen",
                        "media": [
                            {
                                "url": "https://cdn.example.com/demo.mp4",
                                "kind": "video",
                            }
                        ],
                    },
                ]
            },
            content=[],
        )

    hits = await OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    ).search("Qwen model architecture diagram image", 5)

    assert [hit.title for hit in hits] == [
        "Official architecture figure",
        "Unrelated demo",
    ]
    assert hits[0].media == (
        MediaAsset(
            url="https://cdn.example.com/asset?id=figure-1",
            kind="image",
        ),
    )
    assert hits[1].media == ()


@pytest.mark.asyncio
async def test_omniseek_adapter_image_route_includes_media_rich_sources():
    async def call_tool(name: str, arguments: dict[str, object]):
        del name
        sources = arguments.get("sources")
        documents = []
        if isinstance(sources, list) and "academic_ai_labs" in sources:
            documents = [
                {
                    "title": "Research lab benchmark figure",
                    "content": "The requested benchmark chart.",
                    "url": "https://example.com/research",
                    "source": "academic_ai_labs",
                    "media": ["https://cdn.example.com/chart.png"],
                }
            ]
        return SimpleNamespace(
            isError=False,
            structuredContent={"documents": documents},
            content=[],
        )

    hits = await OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    ).search("vision benchmark chart image", 5)

    assert hits[0].source == "academic_ai_labs"
    assert hits[0].media == (
        MediaAsset(url="https://cdn.example.com/chart.png", kind="image"),
    )


@pytest.mark.asyncio
async def test_omniseek_adapter_ranks_matching_media_by_query_relevance():
    async def call_tool(name: str, arguments: dict[str, object]):
        del name, arguments
        return SimpleNamespace(
            isError=False,
            structuredContent={
                "documents": [
                    {
                        "title": "YOLO object detection chart",
                        "content": "An unrelated computer vision benchmark.",
                        "url": "https://example.com/yolo",
                        "source": "academic_ai_labs",
                        "media": ["https://cdn.example.com/yolo.png"],
                    },
                    {
                        "title": "NVIDIA Blackwell architecture diagram",
                        "content": "Official Blackwell GPU architecture overview.",
                        "url": "https://example.com/blackwell",
                        "source": "nvidia_research",
                        "media": ["https://cdn.example.com/blackwell.png"],
                    },
                ]
            },
            content=[],
        )

    hits = await OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    ).search("NVIDIA Blackwell architecture diagram image", 5)

    assert [hit.title for hit in hits] == [
        "NVIDIA Blackwell architecture diagram",
        "YOLO object detection chart",
    ]


@pytest.mark.asyncio
async def test_omniseek_adapter_does_not_invent_unknown_media_types():
    async def call_tool(name: str, arguments: dict[str, object]):
        del name, arguments
        return SimpleNamespace(
            isError=False,
            structuredContent={
                "documents": [
                    {
                        "title": "Unknown attachment",
                        "content": "The provider did not identify its media type.",
                        "url": "https://example.com/article",
                        "source": "web",
                        "media": ["https://cdn.example.com/asset?id=unknown"],
                    }
                ]
            },
            content=[],
        )

    hits = await OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    ).search("general research topic", 5)

    assert hits[0].media == ()


@pytest.mark.asyncio
async def test_omniseek_adapter_serializes_broad_searches(monkeypatch):
    monkeypatch.setenv("OMNISEEK_BROAD_MAX_CONCURRENCY", "1")
    active = 0
    max_active = 0

    async def call_tool(name: str, arguments: dict[str, object]):
        nonlocal active, max_active
        del name, arguments
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return SimpleNamespace(
            isError=False,
            structuredContent={"documents": []},
            content=[],
        )

    provider = OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    )

    await asyncio.gather(
        provider.search("general research alpha", 5),
        provider.search("general research beta", 5),
        provider.search("general research gamma", 5),
    )

    assert max_active == 1


@pytest.mark.asyncio
async def test_omniseek_adapter_bounds_targeted_media_searches(monkeypatch):
    monkeypatch.delenv("OMNISEEK_MAX_CONCURRENCY", raising=False)
    active = 0
    max_active = 0

    async def call_tool(name: str, arguments: dict[str, object]):
        nonlocal active, max_active
        del name, arguments
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return SimpleNamespace(
            isError=False,
            structuredContent={"documents": []},
            content=[],
        )

    provider = OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    )

    await asyncio.gather(
        *(provider.search(f"official demo video {index}", 5) for index in range(6))
    )

    assert max_active == 4


@pytest.mark.asyncio
async def test_omniseek_adapter_reduces_concurrency_for_wide_media_routes(
    monkeypatch,
):
    monkeypatch.delenv("OMNISEEK_WIDE_MAX_CONCURRENCY", raising=False)
    active = 0
    max_active = 0

    async def call_tool(name: str, arguments: dict[str, object]):
        nonlocal active, max_active
        del name
        sources = arguments.get("sources")
        assert isinstance(sources, list)
        assert len(sources) > 8
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return SimpleNamespace(
            isError=False,
            structuredContent={"documents": []},
            content=[],
        )

    provider = OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        sources=tuple(f"source_{index}" for index in range(9)),
        tool_caller=call_tool,
    )

    await asyncio.gather(
        *(
            provider.search(f"official architecture image {index}", 5)
            for index in range(6)
        )
    )

    assert max_active == 2


@pytest.mark.asyncio
async def test_omniseek_adapter_bounds_mixed_media_source_routes():
    async def call_tool(name: str, arguments: dict[str, object]):
        del name
        sources = arguments.get("sources")
        documents = []
        if isinstance(sources, list) and len(sources) <= 16:
            documents = [
                {
                    "title": "Mixed evidence",
                    "content": "Image, video, and audio evidence.",
                    "url": "https://example.com/evidence",
                    "source": "web",
                }
            ]
        return SimpleNamespace(
            isError=False,
            structuredContent={"documents": documents},
            content=[],
        )

    hits = await OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    ).search("architecture image, demo video, and podcast audio", 5)

    assert [hit.title for hit in hits] == ["Mixed evidence"]


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


@pytest.mark.asyncio
async def test_omniseek_adapter_bounds_fields_and_ignores_unsafe_urls():
    documents = [
        {
            "title": "x" * 900,
            "content": "y" * 9000,
            "url": "https://example.com/ok",
            "source": "z" * 500,
            "media": [
                "https://cdn.example.com/one.jpg",
                "javascript:alert(1)",
                "https://user:secret@cdn.example.com/private.png",
                "https://cdn.example.com/two.webp",
                "https://cdn.example.com/three.png",
                "https://cdn.example.com/four.png",
            ],
        },
        {
            "title": "credentials",
            "content": "must be ignored",
            "url": "https://user:secret@example.com/private",
            "source": "private",
        },
        {
            "title": "oversized URL",
            "content": "must be ignored",
            "url": "https://example.com/" + "a" * 3000,
            "source": "web",
        },
    ]

    async def call_tool(name, arguments):
        del name, arguments
        return SimpleNamespace(
            isError=False,
            structuredContent={"documents": documents},
            content=[],
        )

    hits = await OmniSeekSearchProvider(
        endpoint="http://localhost:8765/mcp",
        token="a-secure-token-value",
        tool_caller=call_tool,
    ).search("topic", 5)

    assert len(hits) == 1
    assert len(hits[0].title) == 500
    assert len(hits[0].snippet) == 4000
    assert len(hits[0].source) == 100
    assert hits[0].media == (
        MediaAsset(url="https://cdn.example.com/one.jpg", kind="image"),
        MediaAsset(url="https://cdn.example.com/two.webp", kind="image"),
        MediaAsset(url="https://cdn.example.com/three.png", kind="image"),
    )


@pytest.mark.parametrize(
    ("sources", "message"),
    [
        (["valid", "../private"], "invalid source"),
        ([f"source-{index}" for index in range(17)], "at most 16"),
    ],
)
def test_omniseek_source_allowlist_is_bounded(sources, message):
    with pytest.raises(ValueError, match=message):
        OmniSeekSearchProvider(
            endpoint="http://localhost:8765/mcp",
            token="a-secure-token-value",
            sources=sources,
        )


@pytest.mark.parametrize(
    ("endpoint", "token", "message"),
    [
        ("ftp://localhost/mcp", "a-secure-token-value", "valid HTTP URL"),
        (
            "http://user:pass@localhost/mcp",
            "a-secure-token-value",
            "must not contain credentials",
        ),
        (
            "http://localhost/mcp?token=secret",
            "a-secure-token-value",
            "query or fragment",
        ),
        ("http://example.com/mcp", "a-secure-token-value", "requires HTTPS"),
        ("http://localhost/mcp", "short", "at least 16 characters"),
    ],
)
def test_omniseek_adapter_rejects_unsafe_configuration(endpoint, token, message):
    with pytest.raises(ValueError, match=message):
        OmniSeekSearchProvider(endpoint=endpoint, token=token)
