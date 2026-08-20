"""Deployment probe for the configured OmniSeek MCP service."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from agent.retrieval import (
    OmniSeekSearchProvider,
    SearchProvider,
    load_omniseek_credentials,
)

_PROBE_QUERY = "OpenAI API official documentation"
_DEFAULT_TOKEN_FILE = (
    Path(__file__).resolve().parents[3]
    / "infrastructure"
    / "omniseek"
    / "data"
    / "credentials"
    / "omniseek_http.json"
)


async def _probe(provider: SearchProvider) -> tuple[int, tuple[str, ...]]:
    hits = await provider.search(_PROBE_QUERY, 3)
    sources = tuple(sorted({hit.source or hit.provider for hit in hits}))
    return len(hits), sources


async def _run() -> int:
    credentials = load_omniseek_credentials(default_token_file=_DEFAULT_TOKEN_FILE)
    if credentials is None:
        print(
            "OmniSeek preflight failed: configure OMNISEEK_TOKEN or OMNISEEK_TOKEN_FILE",
            file=sys.stderr,
        )
        return 2
    endpoint, token = credentials

    try:
        provider = OmniSeekSearchProvider(
            endpoint=endpoint,
            token=token,
            wait_seconds=float(os.getenv("OMNISEEK_WAIT_SECONDS", "3")),
            request_timeout_seconds=float(
                os.getenv("OMNISEEK_REQUEST_TIMEOUT_SECONDS", "12")
            ),
            sources=os.getenv("OMNISEEK_SOURCES", "").split(","),
            max_results=int(os.getenv("OMNISEEK_RESULT_LIMIT", "5")),
        )
        count, sources = await _probe(provider)
    except Exception as exc:
        print(
            f"OmniSeek preflight failed: error_type={type(exc).__name__}",
            file=sys.stderr,
        )
        return 1

    if count == 0:
        print("OmniSeek preflight failed: no documents returned", file=sys.stderr)
        return 1

    print(
        f"OmniSeek preflight ok: documents={count} sources={','.join(sources) or 'unknown'}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
