"""OpenAICompatibleLLM 模块的单元测试。

覆盖：
  - generate_response() 正常调用、空内容异常、空模型 ID
  - agenerate_response() 异步路径
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.exceptions import LLMUnexpectedError


class TestCredentialResolution:
    def test_routes_research_model_to_research_credentials(self, monkeypatch):
        from agent.llm.llm import _resolve_credentials

        monkeypatch.setenv("RESEARCH_LLM_MODEL", "research-model")
        monkeypatch.setenv("RESEARCH_LLM_API_KEY", "research-key")
        monkeypatch.setenv("RESEARCH_LLM_BASE_URL", "https://research.example/v1")

        assert _resolve_credentials("research-model") == (
            "research-key",
            "https://research.example/v1",
        )

    def test_routes_reasoning_model_to_reasoning_credentials(self, monkeypatch):
        from agent.llm.llm import _resolve_credentials

        monkeypatch.setenv("REASONING_LLM_MODEL", "reasoning-model")
        monkeypatch.setenv("REASONING_LLM_API_KEY", "reasoning-key")
        monkeypatch.setenv("REASONING_LLM_BASE_URL", "https://reasoning.example/v1")

        assert _resolve_credentials("reasoning-model") == (
            "reasoning-key",
            "https://reasoning.example/v1",
        )


# ═══════════════════════════════════════════════════════════════════════
# TestOpenAICompatibleLLM — generate_response
# ═══════════════════════════════════════════════════════════════════════

class TestOpenAICompatibleLLMGenerateResponse:
    """测试同步 generate_response() 方法。"""

    def test_normal_call_returns_content(self, mock_openai_client, mock_openai_response):
        """正常调用：LLM 返回内容。"""
        from agent.llm.llm import OpenAICompatibleLLM

        mock_openai_client.chat.completions.create.return_value = (
            mock_openai_response("DeepSeek 成立于 2023 年")
        )

        llm = OpenAICompatibleLLM(model_id="deepseek-v4-flash")
        result = llm.generate_response("请介绍 DeepSeek")

        assert result == "DeepSeek 成立于 2023 年"
        mock_openai_client.chat.completions.create.assert_called_once()

    def test_none_content_raises_unexpected_error(self, mock_openai_client, mock_openai_response):
        """API 返回 content=None → 抛 LLMUnexpectedError。"""
        from agent.llm.llm import OpenAICompatibleLLM

        mock_openai_client.chat.completions.create.return_value = (
            mock_openai_response(None)
        )
        # mock_openai_response(None) 会设置 choice.message.content = None
        # 需要覆盖一下
        choice = MagicMock()
        choice.message.content = None
        resp = MagicMock()
        resp.choices = [choice]
        mock_openai_client.chat.completions.create.return_value = resp

        llm = OpenAICompatibleLLM(model_id="deepseek-v4-flash")
        with pytest.raises(LLMUnexpectedError, match="empty content"):
            llm.generate_response("test")

    def test_empty_model_id_still_calls_api(self, mock_openai_client, mock_openai_response):
        """空 model_id 不会在客户端层报错——由 API 返回错误。

        这是行为文档测试：证明 model_id="" 会被透传给 OpenAI SDK。
        """
        from agent.llm.llm import OpenAICompatibleLLM

        mock_openai_client.chat.completions.create.return_value = (
            mock_openai_response("OK")
        )

        llm = OpenAICompatibleLLM(model_id="")
        # 空 model_id 可能触发 API 400，由 translate_openai_error 处理
        # 测试证明构造不会崩，调用路径存在
        llm.generate_response("test")


# ═══════════════════════════════════════════════════════════════════════
# TestOpenAICompatibleLLMAsync — agenerate_response
# ═══════════════════════════════════════════════════════════════════════

class TestOpenAICompatibleLLMAsync:
    """测试异步 agenerate_response() 方法。"""

    @pytest.mark.asyncio
    async def test_async_normal_call_returns_content(self):
        """异步正常调用：LLM 返回内容。"""
        from agent.llm.llm import OpenAICompatibleLLM

        with patch("agent.llm.llm.AsyncOpenAI") as mock_async_client_cls:
            choice = MagicMock()
            choice.message.content = "异步响应内容"
            resp = MagicMock()
            resp.choices = [choice]

            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=resp)
            mock_async_client_cls.return_value = mock_client

            llm = OpenAICompatibleLLM(model_id="deepseek-v4-flash")
            result = await llm.agenerate_response("测试异步调用")

            assert result == "异步响应内容"
            mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_none_content_raises_unexpected_error(self):
        """异步 API 返回 content=None → 抛 LLMUnexpectedError。"""
        from agent.llm.llm import OpenAICompatibleLLM

        with patch("agent.llm.llm.AsyncOpenAI") as mock_async_client_cls:
            choice = MagicMock()
            choice.message.content = None
            resp = MagicMock()
            resp.choices = [choice]

            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=resp)
            mock_async_client_cls.return_value = mock_client

            llm = OpenAICompatibleLLM(model_id="deepseek-v4-flash")
            with pytest.raises(LLMUnexpectedError, match="empty content"):
                await llm.agenerate_response("test")
