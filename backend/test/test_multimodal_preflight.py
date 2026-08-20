"""Tests for the live multimedia search deployment probe."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agent.multimodal_preflight import _probe, _run
from agent.retrieval import MediaAsset, SearchHit


class _ProbeProvider:
    name = "omniseek"

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        assert query == "Qwen 3.8 27B vision bicycle image"
        assert limit == 10
        return [
            SearchHit(
                title="Video",
                snippet="evidence",
                url="https://example.com/video",
                provider="omniseek",
                media=(
                    MediaAsset(url="https://cdn.example.com/cover.jpg", kind="image"),
                    MediaAsset(url="https://example.com/video", kind="video"),
                ),
            )
        ]


@pytest.mark.asyncio
async def test_probe_reports_each_media_kind():
    assert await _probe(_ProbeProvider()) == (1, 1, 1, 0)


@pytest.mark.asyncio
async def test_run_fails_safely_when_credentials_are_missing(capsys):
    with patch("agent.multimodal_preflight._DEFAULT_TOKEN_FILE", None):
        assert await _run() == 2
    captured = capsys.readouterr()
    assert "credentials" in captured.err
    assert captured.out == ""


@pytest.mark.asyncio
async def test_run_requires_at_least_one_media_asset(monkeypatch, capsys):
    monkeypatch.setenv("OMNISEEK_MCP_URL", "http://localhost:8765/mcp")
    monkeypatch.setenv("OMNISEEK_TOKEN", "a-secure-token-value")

    with patch(
        "agent.multimodal_preflight._probe",
        return_value=(3, 0, 0, 0),
    ):
        assert await _run() == 1

    captured = capsys.readouterr()
    assert "documents=3 media=0" in captured.err
