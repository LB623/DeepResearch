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
from dataclasses import dataclass, field
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

_OMNISEEK_SEMAPHORES: WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    asyncio.Semaphore,
] = WeakKeyDictionary()
_DASHSCOPE_RUNTIME_LOCK = threading.Lock()
_DASHSCOPE_EXECUTOR: concurrent.futures.ThreadPoolExecutor | None = None
_DASHSCOPE_SLOTS: threading.BoundedSemaphore | None = None
_SOURCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One normalized search result with explicit provenance."""

    title: str
    snippet: str
    url: str
    provider: str
    source: str = ""

    def as_page(self) -> dict[str, str]:
        """Return the legacy page shape consumed by the research summarizer."""
        return {"title": self.title, "snippet": self.snippet, "url": self.url}


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
        semantic: bool | None = False,
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

        arguments: dict[str, object] = {
            "query": query,
            "limit": bounded_limit,
            "raw": False,
            "wait_s": self._wait_seconds,
            "staleness": self._staleness,
        }
        if self._sources:
            arguments["sources"] = list(self._sources)
        if self._semantic is not None:
            arguments["semantic"] = self._semantic

        result = await self._tool_caller("omniseek_search", arguments)
        payload = _omniseek_payload(result)
        documents = payload.get("documents")
        if not isinstance(documents, list):
            raise OmniSeekProtocolError("omniseek response has no document list")

        hits: list[SearchHit] = []
        for document in documents[: bounded_limit * 4]:
            if not isinstance(document, Mapping):
                continue
            url = _safe_result_url(document.get("url"))
            if not url:
                continue
            hits.append(
                SearchHit(
                    title=_bounded_text(document.get("title"), 500),
                    snippet=_bounded_text(document.get("content"), 4000),
                    url=url,
                    provider=self.name,
                    source=_bounded_text(document.get("source"), 100),
                )
            )
        return hits[:bounded_limit]

    async def _call_tool(
        self,
        name: str,
        arguments: dict[str, object],
    ) -> CallToolResult:
        async with _omniseek_semaphore():
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


def _bounded_text(value: object, limit: int) -> str:
    return str(value or "")[:limit].strip()


def _omniseek_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    semaphore = _OMNISEEK_SEMAPHORES.get(loop)
    if semaphore is None:
        raw_limit = os.getenv("OMNISEEK_MAX_CONCURRENCY", "8")
        try:
            limit = int(raw_limit)
        except ValueError:
            limit = 8
        semaphore = asyncio.Semaphore(min(max(limit, 1), 64))
        _OMNISEEK_SEMAPHORES[loop] = semaphore
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
