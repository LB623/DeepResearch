"""Unified retrieval seam for search providers.

Providers translate their transport-specific payloads into :class:`SearchHit`.
The coordinator owns concurrency, failure isolation, and cross-provider dedupe so
LangGraph nodes do not need to understand individual provider contracts.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx
from loguru import logger
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

from agent.base_agent import WebSearchAgent


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
    configured_file = os.getenv("OMNISEEK_TOKEN_FILE", "").strip()
    token_file = Path(configured_file).expanduser() if configured_file else default_token_file

    if not token and token_file and token_file.is_file():
        try:
            payload = json.loads(token_file.read_text(encoding="utf-8"))
            candidate = payload.get("token") if isinstance(payload, dict) else None
            token = candidate.strip() if isinstance(candidate, str) else ""
        except (OSError, UnicodeError, json.JSONDecodeError):
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
        response = await asyncio.to_thread(
            self._agent_factory().step,
            prompt=query,
            count=limit,
        )
        if not response:
            return []

        hits: list[SearchHit] = []
        for page in response:
            if not isinstance(page, dict):
                continue
            url = str(page.get("url") or "").strip()
            if not url:
                continue
            hits.append(
                SearchHit(
                    title=str(page.get("title") or "").strip(),
                    snippet=str(page.get("snippet") or "").strip(),
                    url=url,
                    provider=self.name,
                )
            )
        return hits[: max(0, limit)]


class OmniSeekProtocolError(RuntimeError):
    """Safe, transport-independent failure at the OmniSeek seam."""


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
        self._sources = tuple(
            source.strip() for source in sources if source and source.strip()
        )
        self._staleness = (
            staleness if staleness in {"fresh", "cached_ok", "cache_only"}
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
        for document in documents:
            if not isinstance(document, Mapping):
                continue
            url = str(document.get("url") or "").strip()
            if not url:
                continue
            hits.append(
                SearchHit(
                    title=str(document.get("title") or "").strip(),
                    snippet=str(document.get("content") or "").strip()[:4000],
                    url=url,
                    provider=self.name,
                    source=str(document.get("source") or "").strip(),
                )
            )
        return hits[:bounded_limit]

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
    ) -> None:
        if not providers and not fallback_providers:
            raise ValueError("at least one search provider is required")
        self._providers = tuple(providers)
        self._fallback_providers = tuple(fallback_providers)

    async def search(self, query: str, limit: int) -> SearchBatch:
        bounded_limit = max(0, int(limit))
        hits, attempted, failures = await self._run_providers(
            self._providers,
            query,
            bounded_limit,
        )
        if not hits and self._fallback_providers:
            fallback_hits, fallback_attempted, fallback_failures = (
                await self._run_providers(
                    self._fallback_providers,
                    query,
                    bounded_limit,
                )
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
        tasks = [provider.search(query, limit) for provider in providers]
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
    return value


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
        text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
        if not isinstance(text, str):
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise OmniSeekProtocolError("omniseek response is not valid structured data")
