"""Tests for the OmniSeek deployment probe."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agent.retrieval import SearchHit
from agent.retrieval_preflight import _probe, _run


class _ProbeProvider:
    name = "omniseek"

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        assert query == "OpenAI API official documentation"
        assert limit == 3
        return [
            SearchHit(
                title="Docs",
                snippet="evidence",
                url="https://example.com/docs",
                provider="omniseek",
                source="official",
            )
        ]


@pytest.mark.asyncio
async def test_probe_reports_document_count_and_sources():
    assert await _probe(_ProbeProvider()) == (1, ("official",))


@pytest.mark.asyncio
async def test_run_fails_safely_when_credentials_are_missing(capsys):
    with patch("agent.retrieval_preflight._DEFAULT_TOKEN_FILE", None):
        assert await _run() == 2
    captured = capsys.readouterr()
    assert "OMNISEEK_TOKEN_FILE" in captured.err
    assert captured.out == ""


@pytest.mark.asyncio
async def test_run_never_prints_exception_details(monkeypatch, capsys):
    monkeypatch.setenv("OMNISEEK_MCP_URL", "http://localhost:8765/mcp")
    monkeypatch.setenv("OMNISEEK_TOKEN", "a-secure-token-value")

    with patch(
        "agent.retrieval_preflight.OmniSeekSearchProvider",
        side_effect=RuntimeError("private token or upstream response"),
    ):
        assert await _run() == 1

    captured = capsys.readouterr()
    assert "error_type=RuntimeError" in captured.err
    assert "private token" not in captured.err
