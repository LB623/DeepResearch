"""Unified retrieval seam for search providers.

Providers translate their transport-specific payloads into :class:`SearchHit`.
The coordinator owns concurrency, failure isolation, and cross-provider dedupe so
LangGraph nodes do not need to understand individual provider contracts.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import ipaddress
import json
import math
import os
import re
import threading
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit
from weakref import WeakKeyDictionary

import httpx
from loguru import logger
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

from agent.base_agent import WebSearchAgent

_OMNISEEK_BROAD_SEMAPHORES: WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    asyncio.Semaphore,
] = WeakKeyDictionary()
_OMNISEEK_TARGETED_SEMAPHORES: WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    asyncio.Semaphore,
] = WeakKeyDictionary()
_OMNISEEK_WIDE_TARGETED_SEMAPHORES: WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    asyncio.Semaphore,
] = WeakKeyDictionary()
_DASHSCOPE_RUNTIME_LOCK = threading.Lock()
_DASHSCOPE_EXECUTOR: concurrent.futures.ThreadPoolExecutor | None = None
_DASHSCOPE_SLOTS: threading.BoundedSemaphore | None = None
_SOURCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_IMAGE_EXTENSIONS = (".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp")
_VIDEO_EXTENSIONS = (".m4v", ".mkv", ".mov", ".mp4", ".webm")
_AUDIO_EXTENSIONS = (".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav")
_VIDEO_HOSTS = ("bilibili.com", "youtu.be", "youtube.com")
_AUDIO_PAGE_SOURCES = {
    "apple_podcasts",
    "chinese_podcasts",
    "podcast_index",
    "xiaoyuzhou",
}
_VIDEO_PAGE_SOURCES = {"bilibili", "youtube"}
_VIDEO_QUERY_PATTERN = re.compile(
    r"(?:\bvideo\b|\byoutube\b|\bbilibili\b|视频|演示)",
    re.IGNORECASE,
)
_AUDIO_QUERY_PATTERN = re.compile(
    r"(?:\baudio\b|\bpodcast\b|播客|音频|有声)",
    re.IGNORECASE,
)
_IMAGE_QUERY_PATTERN = re.compile(
    r"(?:\bimage\b|\bdiagram\b|\bchart\b|\bphoto\b|"
    r"图片|图像|架构图|示意图|图表|截图)",
    re.IGNORECASE,
)
_RELEVANCE_TERM_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.+-]*|[\u4e00-\u9fff]{2,}")
_MEDIA_QUERY_STOPWORDS = {
    "audio",
    "bilibili",
    "chart",
    "demo",
    "diagram",
    "image",
    "images",
    "official",
    "photo",
    "podcast",
    "video",
    "youtube",
    "图片",
    "图像",
    "图表",
    "截图",
    "播客",
    "演示",
    "视频",
    "音频",
}
_DEFAULT_VIDEO_SOURCES = (
    "bilibili",
    "youtube",
    "youtube_channels",
    "slideslive_talks",
    "underline_talks",
    "douyin",
)
_DEFAULT_AUDIO_SOURCES = (
    "podcast_index",
    "apple_podcasts",
    "chinese_podcasts",
    "xiaoyuzhou",
)
_DEFAULT_IMAGE_SOURCES = (
    "cvf_openaccess",
    "qwen",
    "xiaohongshu_search",
    "academic_ai_labs",
    "frontier_labs",
    "ai_newsletters",
    "substack_matrix",
    "youtube_channels",
)


@dataclass(frozen=True, slots=True)
class MediaAsset:
    """One bounded, externally hosted media item attached to a search hit."""

    url: str
    kind: str

    def as_dict(self) -> dict[str, str]:
        return {"url": self.url, "kind": self.kind}


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One normalized search result with explicit provenance."""

    title: str
    snippet: str
    url: str
    provider: str
    source: str = ""
    media: tuple[MediaAsset, ...] = ()

    def as_page(self) -> dict[str, object]:
        """Return the legacy page shape consumed by the research summarizer."""
        page: dict[str, object] = {
            "title": self.title,
            "snippet": self.snippet,
            "url": self.url,
        }
        if self.media:
            page["media"] = [asset.as_dict() for asset in self.media]
        return page


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    """Log-safe provider failure metadata; never carries exception text."""

    provider: str
    error_type: str


@dataclass(slots=True)
class SearchBatch:
    """Observable outcome of one logical query across one or more providers."""

    hits: list[SearchHit] = field(default_factory=list)
    providers_attempted: tuple[str, ...] = ()
    failures: tuple[ProviderFailure, ...] = ()


class SearchProvider(Protocol):
    """Adapter interface at the external-search seam."""

    name: str

    async def search(self, query: str, limit: int) -> list[SearchHit]: ...


def load_omniseek_credentials(
    *,
    default_token_file: Path | None = None,
) -> tuple[str, str] | None:
    """Read server-owned credentials without exposing them to graph config/state."""
    endpoint = os.getenv("OMNISEEK_MCP_URL", "").strip()
    token = os.getenv("OMNISEEK_TOKEN", "").strip()
    try:
        configured_file = os.getenv("OMNISEEK_TOKEN_FILE", "").strip()
        token_file = (
            Path(configured_file).expanduser()
            if configured_file
            else default_token_file
        )
        if not token and token_file and token_file.is_file():
            file_stat = token_file.stat()
            if os.name == "posix" and file_stat.st_mode & 0o077:
                return None
            payload = json.loads(token_file.read_text(encoding="utf-8"))
            candidate = payload.get("token") if isinstance(payload, dict) else None
            token = candidate.strip() if isinstance(candidate, str) else ""
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError):
        return None

    if not token:
        return None
    return endpoint or "http://127.0.0.1:8765/mcp", token


class DashScopeSearchProvider:
    """Adapter for the existing DashScope-hosted web-search application."""

    name = "dashscope"

    def __init__(
        self,
        agent_factory: Callable[[], WebSearchAgent] = WebSearchAgent,
    ) -> None:
        self._agent_factory = agent_factory

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        executor, slots = _dashscope_runtime()
        if not slots.acquire(blocking=False):
            raise SearchProviderUnavailable("dashscope concurrency limit reached")
        try:
            future = executor.submit(
                self._agent_factory().step,
                prompt=query,
                count=limit,
            )
        except BaseException:
            slots.release()
            raise
        future.add_done_callback(lambda _: slots.release())
        response = await asyncio.wrap_future(future)
        if response is None:
            raise SearchProviderUnavailable("dashscope search unavailable")
        if not response:
            return []

        hits: list[SearchHit] = []
        for page in response:
            if not isinstance(page, dict):
                continue
            url = _safe_result_url(page.get("url"))
            if not url:
                continue
            hits.append(
                SearchHit(
                    title=_bounded_text(page.get("title"), 500),
                    snippet=_bounded_text(page.get("snippet"), 4000),
                    url=url,
                    provider=self.name,
                )
            )
        return hits[: max(0, limit)]


class OmniSeekProtocolError(RuntimeError):
    """Safe, transport-independent failure at the OmniSeek seam."""


class SearchProviderUnavailable(RuntimeError):
    """A provider failed without carrying upstream response details."""


OmniSeekToolCaller = Callable[
    [str, dict[str, object]],
    Awaitable[CallToolResult],
]


class OmniSeekSearchProvider:
    """Bounded MCP adapter for OmniSeek's normalized ranked search."""

    name = "omniseek"

    def __init__(
        self,
        *,
        endpoint: str,
        token: str,
        wait_seconds: float = 3.0,
        request_timeout_seconds: float = 12.0,
        sources: Sequence[str] = (),
        staleness: str = "cached_ok",
        semantic: bool | None = None,
        max_results: int = 10,
        tool_caller: OmniSeekToolCaller | None = None,
    ) -> None:
        self._endpoint = _validated_endpoint(endpoint)
        self._token = _validated_token(token)
        self._wait_seconds = _bounded_seconds(
            wait_seconds,
            name="wait_seconds",
            lower=0.1,
            upper=15.0,
        )
        self._request_timeout_seconds = _bounded_seconds(
            request_timeout_seconds,
            name="request_timeout_seconds",
            lower=self._wait_seconds + 2.0,
            upper=120.0,
        )
        self._sources = _validated_sources(sources)
        self._staleness = (
            staleness
            if staleness in {"fresh", "cached_ok", "cache_only"}
            else "cached_ok"
        )
        self._semantic = semantic
        self._max_results = min(max(int(max_results), 1), 50)
        self._tool_caller = tool_caller or self._call_tool

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        bounded_limit = min(max(int(limit), 0), self._max_results, 50)
        if bounded_limit == 0:
            return []
        deadline = asyncio.get_running_loop().time() + self._request_timeout_seconds

        requested_media = _requested_media_kinds(query)
        effective_sources = self._sources or _routed_media_sources(requested_media)
        arguments: dict[str, object] = {
            "query": query,
            "limit": bounded_limit,
            "raw": False,
            "wait_s": self._wait_seconds,
            "staleness": self._staleness,
        }
        if effective_sources:
            arguments["sources"] = list(effective_sources)
        arguments["semantic"] = (
            self._semantic if self._semantic is not None else bool(requested_media)
        )

        source_count = len(effective_sources)
        initial_budget = max(0.0, deadline - asyncio.get_running_loop().time())
        async with asyncio.timeout(initial_budget):
            documents = await self._request_documents(
                arguments,
                source_count=source_count,
            )
        hits = _omniseek_hits(documents, provider=self.name, limit=bounded_limit)
        if requested_media and not any(
            asset.kind in requested_media for hit in hits for asset in hit.media
        ):
            remaining_seconds = deadline - asyncio.get_running_loop().time()
            retry_documents: list[object] = []
            if remaining_seconds > 0:
                try:
                    async with asyncio.timeout(remaining_seconds):
                        retry_documents = await self._request_documents(
                            arguments,
                            source_count=source_count,
                        )
                except TimeoutError:
                    pass
            retry_hits = _omniseek_hits(
                retry_documents,
                provider=self.name,
                limit=bounded_limit,
            )
            hits = list({hit.url: hit for hit in (*hits, *retry_hits)}.values())
        if requested_media:
            hits = _prioritize_requested_media(hits, requested_media, query=query)
        return hits[:bounded_limit]

    async def _request_documents(
        self,
        arguments: dict[str, object],
        *,
        source_count: int,
    ) -> list[object]:
        async with _omniseek_semaphore(source_count=source_count):
            result = await self._tool_caller("omniseek_search", arguments)
        payload = _omniseek_payload(result)
        documents = payload.get("documents")
        if not isinstance(documents, list):
            raise OmniSeekProtocolError("omniseek response has no document list")
        return documents

    async def _call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> CallToolResult:
        timeout = httpx.Timeout(
            self._request_timeout_seconds,
            connect=min(self._request_timeout_seconds, 5.0),
        )
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            trust_env=False,
        ) as http_client:
            async with streamable_http_client(
                self._endpoint,
                http_client=http_client,
                terminate_on_close=False,
            ) as (read_stream, write_stream, _):
                async with ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(
                        seconds=self._request_timeout_seconds
                    ),
                ) as session:
                    await session.initialize()
                    return await session.call_tool(name, arguments=arguments)


class SearchCoordinator:
    """Run primary providers, then optional fallbacks, and deduplicate results."""

    def __init__(
        self,
        providers: Sequence[SearchProvider],
        *,
        fallback_providers: Sequence[SearchProvider] = (),
        provider_timeout_seconds: float = 30.0,
    ) -> None:
        if not providers and not fallback_providers:
            raise ValueError("at least one search provider is required")
        self._providers = tuple(providers)
        self._fallback_providers = tuple(fallback_providers)
        self._provider_timeout_seconds = _bounded_seconds(
            provider_timeout_seconds,
            name="provider_timeout_seconds",
            lower=0.01,
            upper=120.0,
        )

    async def search(self, query: str, limit: int) -> SearchBatch:
        bounded_limit = max(0, int(limit))
        hits, attempted, failures = await self._run_providers(
            self._providers,
            query,
            bounded_limit,
        )
        if not hits and self._fallback_providers:
            (
                fallback_hits,
                fallback_attempted,
                fallback_failures,
            ) = await self._run_providers(
                self._fallback_providers,
                query,
                bounded_limit,
            )
            hits.extend(fallback_hits)
            attempted.extend(fallback_attempted)
            failures.extend(fallback_failures)

        return SearchBatch(
            hits=_dedupe_hits(hits),
            providers_attempted=tuple(attempted),
            failures=tuple(failures),
        )

    async def _run_providers(
        self,
        providers: Sequence[SearchProvider],
        query: str,
        limit: int,
    ) -> tuple[list[SearchHit], list[str], list[ProviderFailure]]:
        tasks = [
            asyncio.wait_for(
                provider.search(query, limit),
                timeout=self._provider_timeout_seconds,
            )
            for provider in providers
        ]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        hits: list[SearchHit] = []
        failures: list[ProviderFailure] = []
        for provider, outcome in zip(providers, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                if not isinstance(outcome, Exception):
                    raise outcome
                error_type = type(outcome).__name__
                failures.append(ProviderFailure(provider.name, error_type))
                logger.warning(
                    "[Retrieval] provider failed provider={} error_type={}",
                    provider.name,
                    error_type,
                )
                continue
            hits.extend(outcome)

        return hits, [provider.name for provider in providers], failures


def _dedupe_hits(hits: Sequence[SearchHit]) -> list[SearchHit]:
    seen: set[str] = set()
    unique: list[SearchHit] = []
    for hit in hits:
        key = _result_key(hit)
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
    return unique


def _result_key(hit: SearchHit) -> str:
    try:
        parts = urlsplit(hit.url.strip())
        if parts.scheme and parts.netloc:
            normalized = urlunsplit(
                (
                    parts.scheme.lower(),
                    parts.netloc.lower(),
                    parts.path.rstrip("/") or "/",
                    parts.query,
                    "",
                )
            )
            return f"url:{normalized}"
    except ValueError:
        pass
    return f"title:{hit.title.strip().casefold()}|source:{hit.source.casefold()}"


def _validated_endpoint(endpoint: str) -> str:
    value = endpoint.strip()
    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise ValueError("OMNISEEK_MCP_URL must be a valid HTTP URL") from exc
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("OMNISEEK_MCP_URL must be a valid HTTP URL")
    if parts.username or parts.password:
        raise ValueError("OMNISEEK_MCP_URL must not contain credentials")
    if parts.query or parts.fragment:
        raise ValueError("OMNISEEK_MCP_URL must not contain a query or fragment")
    if parts.scheme == "http" and not _is_loopback_host(parts.hostname or ""):
        raise ValueError("OMNISEEK_MCP_URL requires HTTPS for non-loopback hosts")
    return value


def _is_loopback_host(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _safe_result_url(value: object) -> str:
    url = str(value or "").strip()
    if len(url) > 2048:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    if parts.username or parts.password:
        return ""
    return url


def _validated_sources(sources: Sequence[str]) -> tuple[str, ...]:
    cleaned = tuple(
        dict.fromkeys(source.strip() for source in sources if source.strip())
    )
    if len(cleaned) > 16:
        raise ValueError("OMNISEEK_SOURCES accepts at most 16 source names")
    if any(not _SOURCE_NAME_PATTERN.fullmatch(source) for source in cleaned):
        raise ValueError("OMNISEEK_SOURCES contains an invalid source name")
    return cleaned


def _omniseek_hits(
    documents: Sequence[object],
    *,
    provider: str,
    limit: int,
) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for document in documents[: limit * 4]:
        if not isinstance(document, Mapping):
            continue
        url = _safe_result_url(document.get("url"))
        if not url:
            continue
        source = _bounded_text(document.get("source"), 100)
        hits.append(
            SearchHit(
                title=_bounded_text(document.get("title"), 500),
                snippet=_bounded_text(document.get("content"), 4000),
                url=url,
                provider=provider,
                source=source,
                media=_normalized_document_media(
                    document,
                    page_url=url,
                    source=source,
                ),
            )
        )
    return hits


def _requested_media_kinds(query: str) -> frozenset[str]:
    requested: set[str] = set()
    if _VIDEO_QUERY_PATTERN.search(query):
        requested.add("video")
    if _AUDIO_QUERY_PATTERN.search(query):
        requested.add("audio")
    if _IMAGE_QUERY_PATTERN.search(query):
        requested.add("image")
    return frozenset(requested)


def _routed_media_sources(requested_media: frozenset[str]) -> tuple[str, ...]:
    sources: list[str] = []
    if "video" in requested_media:
        sources.extend(_DEFAULT_VIDEO_SOURCES)
    if "audio" in requested_media:
        sources.extend(_DEFAULT_AUDIO_SOURCES)
    if "image" in requested_media:
        sources.extend(_DEFAULT_IMAGE_SOURCES)
    return tuple(dict.fromkeys(sources))[:16]


def _prioritize_requested_media(
    hits: Sequence[SearchHit],
    requested_media: frozenset[str],
    *,
    query: str,
) -> list[SearchHit]:
    normalized = [
        replace(
            hit,
            media=tuple(asset for asset in hit.media if asset.kind in requested_media),
        )
        for hit in hits
    ]
    return sorted(
        normalized,
        key=lambda hit: (not bool(hit.media), -_metadata_relevance(query, hit)),
    )


def _metadata_relevance(query: str, hit: SearchHit) -> int:
    terms = {
        term.casefold()
        for term in _RELEVANCE_TERM_PATTERN.findall(query.casefold())
        if len(term) > 1 and term.casefold() not in _MEDIA_QUERY_STOPWORDS
    }
    title = hit.title.casefold()
    snippet = hit.snippet.casefold()
    return sum(3 if term in title else 1 if term in snippet else 0 for term in terms)


def _bounded_text(value: object, limit: int) -> str:
    return str(value or "")[:limit].strip()


def _normalized_media(value: object, *, limit: int = 3) -> tuple[MediaAsset, ...]:
    """Normalize untrusted provider media without materializing unbounded arrays."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()

    assets: list[MediaAsset] = []
    seen: set[str] = set()
    for item in value[: limit * 4]:
        explicit_kind = ""
        candidate: object = item
        if isinstance(item, Mapping):
            candidate = item.get("url") or item.get("src")
            explicit_kind = _bounded_text(
                item.get("kind") or item.get("type"),
                20,
            ).casefold()
        url = _safe_result_url(candidate)
        if not url or url in seen:
            continue
        kind = _media_kind(url, explicit_kind)
        if not kind:
            continue
        assets.append(MediaAsset(url=url, kind=kind))
        seen.add(url)
        if len(assets) >= limit:
            break
    return tuple(assets)


def _normalized_document_media(
    document: Mapping[str, object],
    *,
    page_url: str,
    source: str,
    limit: int = 3,
) -> tuple[MediaAsset, ...]:
    assets = list(_normalized_media(document.get("media"), limit=limit))
    seen = {asset.url for asset in assets}
    metadata = document.get("metadata")
    handles = metadata.get("handles") if isinstance(metadata, Mapping) else None
    transcribable = (
        handles.get("transcribable") if isinstance(handles, Mapping) else None
    )
    if isinstance(transcribable, Sequence) and not isinstance(
        transcribable,
        (str, bytes),
    ):
        for candidate in transcribable[: limit * 4]:
            url = _safe_result_url(candidate)
            if not url or url in seen:
                continue
            assets.append(
                MediaAsset(
                    url=url,
                    kind=_transcribable_kind(url, source),
                )
            )
            seen.add(url)
            if len(assets) >= limit:
                break

    # Older adapters signal transcribability without repeating the page URL.
    if transcribable is True and page_url not in seen and len(assets) < limit:
        assets.append(
            MediaAsset(
                url=page_url,
                kind=_transcribable_kind(page_url, source),
            )
        )
        seen.add(page_url)
    if (
        source.casefold() in _AUDIO_PAGE_SOURCES
        and page_url not in seen
        and len(assets) < limit
    ):
        assets.append(MediaAsset(url=page_url, kind="audio"))
    if (
        source.casefold() in _VIDEO_PAGE_SOURCES
        and page_url not in seen
        and len(assets) < limit
    ):
        assets.append(MediaAsset(url=page_url, kind="video"))
    return tuple(assets)


def _transcribable_kind(url: str, source: str) -> str:
    inferred = _media_kind(url)
    if inferred in {"audio", "video"}:
        return inferred
    host = (urlsplit(url).hostname or "").casefold()
    source_name = source.casefold()
    if any(host == item or host.endswith(f".{item}") for item in _VIDEO_HOSTS):
        return "video"
    if any(token in source_name for token in ("bilibili", "video", "youtube")):
        return "video"
    return "audio"


def _media_kind(url: str, explicit_kind: str = "") -> str:
    aliases = {
        "audio": "audio",
        "image": "image",
        "photo": "image",
        "picture": "image",
        "video": "video",
    }
    if explicit_kind in aliases:
        return aliases[explicit_kind]

    path = urlsplit(url).path.casefold()
    if path.endswith(_VIDEO_EXTENSIONS):
        return "video"
    if path.endswith(_AUDIO_EXTENSIONS):
        return "audio"
    if path.endswith(_IMAGE_EXTENSIONS):
        return "image"
    return ""


def _omniseek_semaphore(*, source_count: int) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if source_count == 0:
        semaphores = _OMNISEEK_BROAD_SEMAPHORES
        env_name = "OMNISEEK_BROAD_MAX_CONCURRENCY"
        default_limit = 1
    elif source_count > 8:
        semaphores = _OMNISEEK_WIDE_TARGETED_SEMAPHORES
        env_name = "OMNISEEK_WIDE_MAX_CONCURRENCY"
        default_limit = 2
    else:
        semaphores = _OMNISEEK_TARGETED_SEMAPHORES
        env_name = "OMNISEEK_MAX_CONCURRENCY"
        default_limit = 4
    semaphore = semaphores.get(loop)
    if semaphore is None:
        raw_limit = os.getenv(env_name, str(default_limit))
        try:
            limit = int(raw_limit)
        except ValueError:
            limit = default_limit
        semaphore = asyncio.Semaphore(min(max(limit, 1), 64))
        semaphores[loop] = semaphore
    return semaphore


def _dashscope_runtime() -> tuple[
    concurrent.futures.ThreadPoolExecutor,
    threading.BoundedSemaphore,
]:
    global _DASHSCOPE_EXECUTOR, _DASHSCOPE_SLOTS
    with _DASHSCOPE_RUNTIME_LOCK:
        if _DASHSCOPE_EXECUTOR is None or _DASHSCOPE_SLOTS is None:
            raw_limit = os.getenv("DASHSCOPE_MAX_CONCURRENCY", "8")
            try:
                limit = int(raw_limit)
            except ValueError:
                limit = 8
            limit = min(max(limit, 1), 64)
            _DASHSCOPE_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
                max_workers=limit,
                thread_name_prefix="dashscope-search",
            )
            _DASHSCOPE_SLOTS = threading.BoundedSemaphore(limit)
        return _DASHSCOPE_EXECUTOR, _DASHSCOPE_SLOTS


def _validated_token(token: str) -> str:
    value = token.strip()
    if len(value) < 16:
        raise ValueError("OMNISEEK_TOKEN must contain at least 16 characters")
    return value


def _bounded_seconds(
    value: float,
    *,
    name: str,
    lower: float,
    upper: float,
) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite")
    return min(max(parsed, lower), upper)


def _omniseek_payload(result: Any) -> dict[str, Any]:
    if getattr(result, "isError", False):
        raise OmniSeekProtocolError("omniseek tool call failed")

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    for block in getattr(result, "content", ()) or ():
        text = (
            block.get("text")
            if isinstance(block, dict)
            else getattr(block, "text", None)
        )
        if not isinstance(text, str):
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise OmniSeekProtocolError("omniseek response is not valid structured data")
