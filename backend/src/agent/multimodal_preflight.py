"""Live deployment probe for OmniSeek multimedia search results."""

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

_PROBE_QUERY = "Qwen 3.8 27B vision bicycle image"
_DEFAULT_TOKEN_FILE = (
    Path(__file__).resolve().parents[3]
    / "infrastructure"
    / "omniseek"
    / "data"
    / "credentials"
    / "omniseek_http.json"
)


async def _probe(provider: SearchProvider) -> tuple[int, int, int, int]:
    hits = await provider.search(_PROBE_QUERY, 10)
    media = [asset for hit in hits for asset in hit.media]
    return (
        len(hits),
        sum(asset.kind == "image" for asset in media),
        sum(asset.kind == "video" for asset in media),
        sum(asset.kind == "audio" for asset in media),
    )


async def _run() -> int:
    credentials = load_omniseek_credentials(default_token_file=_DEFAULT_TOKEN_FILE)
    if credentials is None:
        print(
            "Multimodal preflight failed: configure OmniSeek credentials",
            file=sys.stderr,
        )
        return 2
    endpoint, token = credentials

    try:
        provider = OmniSeekSearchProvider(
            endpoint=endpoint,
            token=token,
            wait_seconds=float(os.getenv("OMNISEEK_WAIT_SECONDS", "5")),
            request_timeout_seconds=float(
                os.getenv("OMNISEEK_REQUEST_TIMEOUT_SECONDS", "12")
            ),
            sources=os.getenv("OMNISEEK_SOURCES", "").split(","),
            max_results=10,
        )
        documents, images, videos, audio = await _probe(provider)
    except Exception as exc:
        print(
            f"Multimodal preflight failed: error_type={type(exc).__name__}",
            file=sys.stderr,
        )
        return 1

    if images + videos + audio == 0:
        print(
            f"Multimodal preflight failed: documents={documents} media=0",
            file=sys.stderr,
        )
        return 1

    print(
        "Multimodal preflight ok: "
        f"documents={documents} images={images} videos={videos} audio={audio}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
