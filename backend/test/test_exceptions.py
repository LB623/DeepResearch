"""Tests for the new exception classification system.

Validates:
  - Exception hierarchy (Transient vs Permanent)
  - is_transient / is_permanent helpers
  - OpenAI error → Agent exception translation
  - PermanentError → fail-fast (no retry) in Agent/WebSearchAgent
  - KB degradation counter and alert threshold
  - KB embedding 401/403 → KBEmbeddingFatalError
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.exceptions import (
    TransientError,
    PermanentError,
    AgentError,
    LLMRateLimitError,
    LLMServerError,
    LLMNetworkError,
    LLMAuthError,
    LLMBadRequestError,
    LLMUnexpectedError,
    MCPRateLimitError,
    MCPAuthError,
    MCPAccessDeniedError,
    MCPParseError,
    MCPEmptyResultError,
    MCPServerError,
    KBConnectionError,
    KBEmbeddingError,
    KBEmbeddingFatalError,
    KBConfigError,
    is_transient,
    is_permanent,
)


# ═══════════════════════════════════════════════════════════════════════
# Exception hierarchy tests
# ═══════════════════════════════════════════════════════════════════════

class TestExceptionHierarchy:
    def test_transient_subclasses_are_transient(self):
        assert is_transient(LLMRateLimitError("test"))
        assert is_transient(LLMServerError("test"))
        assert is_transient(LLMNetworkError("test"))
        assert is_transient(MCPRateLimitError("test"))
        assert is_transient(MCPServerError("test"))
        assert is_transient(MCPEmptyResultError("test"))
        assert is_transient(KBConnectionError("test"))
        assert is_transient(KBEmbeddingError("test"))

    def test_permanent_subclasses_are_permanent(self):
        assert is_permanent(LLMAuthError("test"))
        assert is_permanent(LLMBadRequestError("test"))
        assert is_permanent(LLMUnexpectedError("test"))
        assert is_permanent(MCPAuthError("test"))
        assert is_permanent(MCPAccessDeniedError("test"))
        assert is_permanent(MCPParseError("test"))
        assert is_permanent(KBEmbeddingFatalError("test"))
        assert is_permanent(KBConfigError("test"))

    def test_permanent_is_not_transient(self):
        assert not is_transient(LLMAuthError("test"))
        assert not is_transient(MCPParseError("test"))

    def test_transient_is_not_permanent(self):
        assert not is_permanent(LLMRateLimitError("test"))
        assert not is_permanent(KBConnectionError("test"))

    def test_connection_error_is_transient(self):
        assert is_transient(ConnectionError("test"))
        assert is_transient(TimeoutError("test"))

    def test_native_error_is_neither(self):
        assert not is_transient(ValueError("test"))
        assert not is_permanent(ValueError("test"))

    def test_request_id_propagation(self):
        err = MCPRateLimitError("rate limited", request_id="req-123")
        assert err.request_id == "req-123"

    def test_all_agent_errors_are_agent_error(self):
        for cls in [
            LLMRateLimitError, LLMAuthError, MCPParseError,
            KBConnectionError, KBConfigError,
        ]:
            err = cls("test")
            assert isinstance(err, AgentError)


# ═══════════════════════════════════════════════════════════════════════
# OpenAI error translation tests
# ═══════════════════════════════════════════════════════════════════════

class TestOpenAIErrorTranslation:
    @staticmethod
    def _make_mock_response(status_code=200):
        """Create a minimal mock httpx.Response for OpenAI SDK constructors."""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.request = MagicMock()
        return mock_resp

    def test_rate_limit_error_to_llm_rate_limit(self):
        from agent.llm.llm import _translate_openai_error
        from openai import RateLimitError

        resp = self._make_mock_response(429)
        orig = RateLimitError("rate limited", response=resp, body=None)
        translated = _translate_openai_error(orig)
        assert isinstance(translated, LLMRateLimitError)
        assert is_transient(translated)

    def test_auth_error_to_llm_auth(self):
        from agent.llm.llm import _translate_openai_error
        from openai import AuthenticationError

        resp = self._make_mock_response(401)
        orig = AuthenticationError("bad key", response=resp, body=None)
        translated = _translate_openai_error(orig)
        assert isinstance(translated, LLMAuthError)
        assert is_permanent(translated)

    def test_bad_request_to_llm_bad_request(self):
        from agent.llm.llm import _translate_openai_error
        from openai import BadRequestError

        resp = self._make_mock_response(400)
        orig = BadRequestError("model not found", response=resp, body=None)
        translated = _translate_openai_error(orig)
        assert isinstance(translated, LLMBadRequestError)
        assert is_permanent(translated)

    def test_connection_error_to_llm_network(self):
        from agent.llm.llm import _translate_openai_error
        from openai import APIConnectionError

        req = self._make_mock_response().request
        orig = APIConnectionError(message="refused", request=req)
        translated = _translate_openai_error(orig)
        assert isinstance(translated, LLMNetworkError)
        assert is_transient(translated)

    def test_server_error_to_llm_server(self):
        from agent.llm.llm import _translate_openai_error
        from openai import InternalServerError

        resp = self._make_mock_response(500)
        orig = InternalServerError("boom", response=resp, body=None)
        translated = _translate_openai_error(orig)
        assert isinstance(translated, LLMServerError)
        assert is_transient(translated)

    def test_permission_denied_to_llm_bad_request(self):
        from agent.llm.llm import _translate_openai_error
        from openai import PermissionDeniedError

        resp = self._make_mock_response(403)
        orig = PermissionDeniedError("no access", response=resp, body=None)
        translated = _translate_openai_error(orig)
        assert isinstance(translated, LLMBadRequestError)
        assert is_permanent(translated)

    def test_unknown_to_unexpected(self):
        from agent.llm.llm import _translate_openai_error
        from openai import APIError

        req = self._make_mock_response(418).request
        orig = APIError("something weird", request=req, body=None)
        translated = _translate_openai_error(orig)
        assert isinstance(translated, LLMUnexpectedError)
        assert is_permanent(translated)

    def test_llm_empty_content_raises(self):
        from agent.llm.llm import OpenAICompatibleLLM, LLMUnexpectedError

        with patch("agent.llm.llm.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_choice = MagicMock()
            mock_choice.message.content = None  # empty content
            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai_cls.return_value = mock_client

            llm = OpenAICompatibleLLM(model_id="test")
            with pytest.raises(LLMUnexpectedError, match="empty"):
                llm.generate_response("test query")


# ═══════════════════════════════════════════════════════════════════════
# Fail-fast behavior tests
# ═══════════════════════════════════════════════════════════════════════

class TestPermanentErrorFailFast:
    def test_agent_fails_fast_on_permanent_error(self):
        """Agent.step should stop retrying and re-raise on PermanentError."""
        from agent.base_agent import Agent

        with patch("agent.base_agent.OpenAICompatibleLLM") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.generate_response.side_effect = LLMAuthError("bad key")
            mock_llm_cls.return_value = mock_llm

            agent = Agent(model_id="test")
            with pytest.raises(LLMAuthError):
                agent.step()
            # Only called ONCE (not retried 3 times)
            assert mock_llm.generate_response.call_count == 1

    def test_web_search_fails_fast_on_permanent_error(self):
        """WebSearchAgent.step should stop retrying on MCPAuthError/MCPParseError."""
        from agent.base_agent import WebSearchAgent

        with patch("agent.base_agent.Application") as mock_app:
            # Simulate a response that post_process raises MCPAuthError
            fail_resp = MagicMock()
            fail_resp.status_code = 200
            inner = '{"status": 401, "request_id": "req-401"}'
            import json
            fail_resp.output.text = json.dumps(
                {"result": {"isError": True, "content": [{"text": json.dumps(json.loads(inner))}]}}
            )
            mock_app.call.return_value = fail_resp

            agent = WebSearchAgent()
            agent.set_step_prompt("{prompt}")
            with pytest.raises(MCPAuthError):
                agent.step(prompt="test", count=10)
            # Should fail-fast on 401 — only 1 call
            assert mock_app.call.call_count == 1

    def test_web_search_retries_transient_then_succeeds(self):
        """WebSearchAgent should retry on transient errors, then succeed."""
        from agent.base_agent import WebSearchAgent

        with patch("agent.base_agent.Application") as mock_app:
            # First call: MCPRateLimitError (transient), second call: success
            fail_resp = MagicMock()
            fail_resp.status_code = 200
            inner = '{"status": 429, "request_id": "req-429"}'
            import json
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
            result = agent.step(prompt="test", count=10)

            assert result is not None
            assert mock_app.call.call_count == 2  # retried once, succeeded


# ═══════════════════════════════════════════════════════════════════════
# KB degradation counter tests
# ═══════════════════════════════════════════════════════════════════════
#
# _record_kb_degradation / _reset_kb_degradation 装饰器已在重构中移除。
# KB 降级处理现在通过日志告警 + 静默降级实现，不再使用计数器机制。
# 保留类定义为占位，实际降级行为由集成测试中的 KB 存储边界测试覆盖。


class TestKBDegradationCounter:
    @pytest.mark.skip(reason="KB degradation counter 机制已在重构中移除")
    def test_counter_increments_on_failure(self):
        pass

    @pytest.mark.skip(reason="KB degradation counter 机制已在重构中移除")
    def test_reset_clears_counter(self):
        pass

    @pytest.mark.skip(reason="KB degradation counter 机制已在重构中移除")
    def test_alert_triggered_at_threshold(self):
        pass

    @pytest.mark.skip(reason="KB degradation counter 机制已在重构中移除")
    @pytest.mark.asyncio
    async def test_config_error_not_counted_as_degradation(self, sample_state):
        pass


# ═══════════════════════════════════════════════════════════════════════
# FactStore embedding fatal error tests
# ═══════════════════════════════════════════════════════════════════════

class TestFactStoreEmbeddingFatalErrors:
    def test_401_raises_fatal_error(self):
        """Embedding 401 should raise KBEmbeddingFatalError immediately."""
        from agent.kb.fact_store import FactStore

        with patch("agent.kb.fact_store.MilvusClient") as mock_client_cls, \
             patch("agent.kb.fact_store.requests.post") as mock_post, \
             patch("agent.kb.fact_store.time.sleep"):
            mock_client = MagicMock()
            mock_client.has_collection.return_value = True
            mock_client_cls.return_value = mock_client

            fail_resp = MagicMock()
            fail_resp.status_code = 401
            # raise_for_status will raise HTTPError
            import requests as req
            http_err = req.HTTPError("401 Unauthorized")
            http_err.response = fail_resp
            mock_post.side_effect = http_err

            store = FactStore()
            with pytest.raises(KBEmbeddingFatalError, match="401"):
                store._embed(["test"])

    def test_403_raises_fatal_error(self):
        """Embedding 403 should raise KBEmbeddingFatalError immediately."""
        from agent.kb.fact_store import FactStore

        with patch("agent.kb.fact_store.MilvusClient") as mock_client_cls, \
             patch("agent.kb.fact_store.requests.post") as mock_post, \
             patch("agent.kb.fact_store.time.sleep"):
            mock_client = MagicMock()
            mock_client.has_collection.return_value = True
            mock_client_cls.return_value = mock_client

            fail_resp = MagicMock()
            fail_resp.status_code = 403
            import requests as req
            http_err = req.HTTPError("403 Forbidden")
            http_err.response = fail_resp
            mock_post.side_effect = http_err

            store = FactStore()
            with pytest.raises(KBEmbeddingFatalError, match="403"):
                store._embed(["test"])

    def test_400_raises_fatal_error(self):
        """Embedding 400 should raise KBEmbeddingFatalError."""
        from agent.kb.fact_store import FactStore

        with patch("agent.kb.fact_store.MilvusClient") as mock_client_cls, \
             patch("agent.kb.fact_store.requests.post") as mock_post, \
             patch("agent.kb.fact_store.time.sleep"):
            mock_client = MagicMock()
            mock_client.has_collection.return_value = True
            mock_client_cls.return_value = mock_client

            fail_resp = MagicMock()
            fail_resp.status_code = 400
            import requests as req
            http_err = req.HTTPError("400 Bad Request")
            http_err.response = fail_resp
            mock_post.side_effect = http_err

            store = FactStore()
            with pytest.raises(KBEmbeddingFatalError, match="400"):
                store._embed(["test"])
