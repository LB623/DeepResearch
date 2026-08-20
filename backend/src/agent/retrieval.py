"""Unified retrieval seam for search providers.

Providers translate their transport-specific payloads into :class:`SearchHit`.
The coordinator owns concurrency, failure isolation, and cross-provider dedupe so
LangGraph nodes do not need to understand individual provider contracts.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from loguru import logger

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


class DashScopeSearchProvider:
    """Adapter for the existing DashScope-hosted web-search application."""

    name = "dashscope"

    def __init__(
        self,
        agent_factory: Callable[[], WebSearchAgent] = WebSearchAgent,
    ) -> None:
        self._agent_factory = agent_factory

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        response = await self._agent_factory().astep(prompt=query, count=limit)
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


class SearchCoordinator:
    """Run provider adapters concurrently and return one deduplicated batch."""

    def __init__(self, providers: Sequence[SearchProvider]) -> None:
        if not providers:
            raise ValueError("at least one search provider is required")
        self._providers = tuple(providers)

    async def search(self, query: str, limit: int) -> SearchBatch:
        bounded_limit = max(0, int(limit))
        tasks = [provider.search(query, bounded_limit) for provider in self._providers]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        hits: list[SearchHit] = []
        failures: list[ProviderFailure] = []
        for provider, outcome in zip(self._providers, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                error_type = type(outcome).__name__
                failures.append(ProviderFailure(provider.name, error_type))
                logger.warning(
                    "[Retrieval] provider failed provider={} error_type={}",
                    provider.name,
                    error_type,
                )
                continue
            hits.extend(outcome)

        return SearchBatch(
            hits=_dedupe_hits(hits),
            providers_attempted=tuple(provider.name for provider in self._providers),
            failures=tuple(failures),
        )


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
