"""Async Agent tests — validates astep(), aacquire(), and async retry behavior."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.exceptions import (
    LLMAuthError,
    LLMRateLimitError,
    MCPAuthError,
    MCPRateLimitError,
    TransientError,
    PermanentError,
)


# ═══════════════════════════════════════════════════════════════════════
# RateLimiter.aacquire()
# ═══════════════════════════════════════════════════════════════════════

class TestAsyncRateLimiter:
    @pytest.mark.asyncio
    async def test_aacquire_no_wait_first_call(self):
        from agent.base_agent import RateLimiter

        rl = RateLimiter(max_qps=100.0)
        wait = await rl.aacquire()
        assert wait == 0.0

    @pytest.mark.asyncio
    async def test_aacquire_throttles_rapid_calls(self):
        from agent.base_agent import RateLimiter

        rl = RateLimiter(max_qps=2.0)
        assert await rl.aacquire() == 0.0
        wait = await rl.aacquire()
        assert wait > 0.0

    @pytest.mark.asyncio
    async def test_aacquire_after_interval_no_wait(self):
        import time
        from agent.base_agent import RateLimiter

        rl = RateLimiter(max_qps=2.0)
        await rl.aacquire()
        rl.last_request_time = time.time() - 1.0
        assert await rl.aacquire() == 0.0


# ═══════════════════════════════════════════════════════════════════════
# Agent.astep()
# ═══════════════════════════════════════════════════════════════════════

class TestAsyncAgent:
    @pytest.mark.asyncio
    async def test_astep_calls_async_llm(self):
        from agent.base_agent import Agent

        with patch("agent.base_agent.OpenAICompatibleLLM") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.agenerate_response = AsyncMock(return_value="async response")
            mock_llm_cls.return_value = mock_llm

            agent = Agent(model_id="test")
            agent.set_step_prompt("Hello {name}")
            result = await agent.astep(name="World")

            assert result == "async response"
            mock_llm.agenerate_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_astep_retries_on_transient(self):
        from agent.base_agent import Agent

        with patch("agent.base_agent.OpenAICompatibleLLM") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.agenerate_response = AsyncMock(side_effect=[
                LLMRateLimitError("429"),
                LLMRateLimitError("429"),
                "success after retries",
            ])
            mock_llm_cls.return_value = mock_llm

            agent = Agent(model_id="test")
            result = await agent.astep()

            assert result == "success after retries"
            assert mock_llm.agenerate_response.call_count == 3

    @pytest.mark.asyncio
    async def test_astep_fails_fast_on_permanent(self):
        from agent.base_agent import Agent

        with patch("agent.base_agent.OpenAICompatibleLLM") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.agenerate_response = AsyncMock(side_effect=LLMAuthError("bad key"))
            mock_llm_cls.return_value = mock_llm

            agent = Agent(model_id="test")
            with pytest.raises(LLMAuthError):
                await agent.astep()
            assert mock_llm.agenerate_response.call_count == 1

    @pytest.mark.asyncio
    async def test_astep_returns_empty_on_all_transient_failures(self):
        from agent.base_agent import Agent

        with patch("agent.base_agent.OpenAICompatibleLLM") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.agenerate_response = AsyncMock(
                side_effect=LLMRateLimitError("always 429")
            )
            mock_llm_cls.return_value = mock_llm

            agent = Agent(model_id="test")
            result = await agent.astep()
            assert result == ""
            assert mock_llm.agenerate_response.call_count == 3


# ═══════════════════════════════════════════════════════════════════════
# WebSearchAgent.astep()
# ═══════════════════════════════════════════════════════════════════════

class TestAsyncWebSearchAgent:
    @pytest.mark.asyncio
    async def test_astep_returns_processed_pages(self):
        from agent.base_agent import WebSearchAgent
        import json

        with patch("agent.base_agent.Application") as mock_app:
            success_resp = MagicMock()
            success_resp.status_code = 200
            success_resp.output.text = json.dumps({
                "result": {"content": [{"text": json.dumps({"pages": [
                    {"snippet": "ok", "title": "OK", "url": "https://ok.com"}
                ]})}]}
            })
            mock_app.call.return_value = success_resp

            agent = WebSearchAgent()
            agent.set_step_prompt("{prompt}")
            result = await agent.astep(prompt="test query", count=10)

            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["snippet"] == "ok"

    @pytest.mark.asyncio
    async def test_astep_retries_on_rate_limit(self):
        from agent.base_agent import WebSearchAgent
        import json
        from agent import search_cache

        # 确保缓存已清空，防止 Redis 缓存泄漏导致 mock.call 未被触发
        search_cache.clear_cache()

        with patch("agent.base_agent.Application") as mock_app:
            fail_resp = MagicMock()
            fail_resp.status_code = 200
            inner = json.dumps({"status": 429, "request_id": "req-429"})
            fail_resp.output.text = json.dumps(
                {"result": {"isError": True, "content": [{"text": json.dumps(json.loads(inner))}]}}
            )

            success_resp = MagicMock()
            success_resp.status_code = 200
            success_resp.output.text = json.dumps({
                "result": {"content": [{"text": json.dumps({"pages": [
                    {"snippet": "ok", "title": "OK", "url": "https://ok.com"}
                ]})}]}
            })

            mock_app.call.side_effect = [fail_resp, success_resp]

            agent = WebSearchAgent()
            agent.set_step_prompt("{prompt}")
            result = await agent.astep(prompt="test", count=10)

            assert result is not None
            assert mock_app.call.call_count == 2
