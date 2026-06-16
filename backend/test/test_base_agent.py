"""Tests for Agent, JsonAgent, MCPAgent, and WebSearchAgent classes."""

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from agent.tools_and_schemas import PlanReflection


# ═══════════════════════════════════════════════════════════════════════
# Agent
# ═══════════════════════════════════════════════════════════════════════

class TestAgent:
    def test_step_calls_llm_and_returns_content(self):
        from agent.base_agent import Agent

        with patch("agent.base_agent.OpenAICompatibleLLM") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.generate_response.return_value = "LLM response"
            mock_llm_cls.return_value = mock_llm

            agent = Agent(model_id="test-model")
            agent.set_step_prompt("Hello {name}")
            result = agent.step(name="World")

            assert result == "LLM response"
            mock_llm.generate_response.assert_called_once()

    def test_step_retries_on_failure(self):
        from agent.base_agent import Agent

        with patch("agent.base_agent.OpenAICompatibleLLM") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.generate_response.side_effect = [
                Exception("First call failed"),
                Exception("Second call failed"),
                "success after retries",
            ]
            mock_llm_cls.return_value = mock_llm

            agent = Agent(model_id="test-model")
            result = agent.step()

            assert result == "success after retries"
            assert mock_llm.generate_response.call_count == 3

    def test_step_returns_empty_on_all_failures(self):
        from agent.base_agent import Agent

        with patch("agent.base_agent.OpenAICompatibleLLM") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.generate_response.side_effect = Exception("Always fails")
            mock_llm_cls.return_value = mock_llm

            agent = Agent(model_id="test-model")
            result = agent.step()

            assert result == ""
            assert mock_llm.generate_response.call_count == 3

    def test_prompt_format_replaces_placeholders(self):
        from agent.base_agent import Agent

        agent = Agent()
        result = agent.prompt_format("Hello {name}, you are {age}", name="Alice", age="30")
        assert result == "Hello Alice, you are 30"

    def test_prompt_format_missing_key_ignored(self):
        from agent.base_agent import Agent

        agent = Agent()
        result = agent.prompt_format("Hello {name}", other="value")
        assert result == "Hello {name}"  # not replaced

    def test_direct_call(self):
        from agent.base_agent import Agent

        with patch("agent.base_agent.OpenAICompatibleLLM") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.generate_response.return_value = "direct response"
            mock_llm_cls.return_value = mock_llm

            agent = Agent()
            result = agent("test prompt")
            assert result == "direct response"


# ═══════════════════════════════════════════════════════════════════════
# JsonAgent
# ═══════════════════════════════════════════════════════════════════════

class TestJsonAgent:
    def test_post_process_extracts_json_and_parses_with_keys(self):
        from agent.base_agent import JsonAgent

        agent = JsonAgent(keys=PlanReflection)
        raw = 'some text ```json\n{"satisfy": true}\n``` more text'
        result = agent.post_process(raw)
        assert isinstance(result, PlanReflection)
        assert result.satisfy is True

    def test_post_process_without_keys_returns_dict(self):
        from agent.base_agent import JsonAgent

        agent = JsonAgent()
        raw = '```json\n{"key": "value", "num": 42}\n```'
        result = agent.post_process(raw)
        assert result == {"key": "value", "num": 42}

    def test_step_with_json_output(self):
        from agent.base_agent import JsonAgent
        from agent.tools_and_schemas import PlanReflection

        with patch("agent.base_agent.OpenAICompatibleLLM") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.generate_response.return_value = '```json\n{"satisfy": false}\n```'
            mock_llm_cls.return_value = mock_llm

            agent = JsonAgent(keys=PlanReflection)
            result = agent.step(context="test context")
            assert isinstance(result, PlanReflection)
            assert result.satisfy is False


# ═══════════════════════════════════════════════════════════════════════
# MCPAgent
# ═══════════════════════════════════════════════════════════════════════

class TestMCPAgent:
    def test_step_calls_application_and_returns_parsed_result(self, mock_dashscope_app):
        from agent.base_agent import MCPAgent

        agent = MCPAgent()
        agent.set_step_prompt("search: {prompt}")
        result = agent.step(prompt="test query")

        assert result is not None
        mock_dashscope_app.call.assert_called_once()

    def test_step_retries_on_parse_failure(self, mock_dashscope_app):
        from agent.base_agent import MCPAgent

        # First two calls return invalid, third succeeds
        bad_resp = MagicMock()
        bad_resp.status_code = 200
        bad_resp.output.text = "invalid json"

        mock_dashscope_app.call.side_effect = [
            bad_resp,
            bad_resp,
            mock_dashscope_app.call.return_value,  # the valid one from fixture
        ]

        agent = MCPAgent()
        result = agent.step(prompt="test")
        assert result is not None
        assert mock_dashscope_app.call.call_count == 3

    def test_step_returns_none_on_all_failures(self, mock_dashscope_app):
        from agent.base_agent import MCPAgent

        bad_resp = MagicMock()
        bad_resp.status_code = 500
        mock_dashscope_app.call.return_value = bad_resp

        agent = MCPAgent()
        result = agent.step(prompt="test")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════
# WebSearchAgent
# ═══════════════════════════════════════════════════════════════════════

class TestWebSearchAgent:
    def test_step_returns_processed_pages(self, mock_dashscope_app):
        from agent.base_agent import WebSearchAgent

        agent = WebSearchAgent()
        agent.set_step_prompt("{prompt}")
        result = agent.step(prompt="AI芯片市场", count=10)

        assert isinstance(result, list)
        assert len(result) > 0
        assert "snippet" in result[0]
        assert "title" in result[0]
        assert "url" in result[0]

    def test_step_uses_cache_on_hit(self, mock_dashscope_app):
        from agent.base_agent import WebSearchAgent
        from agent import search_cache

        # Pre-populate cache
        cached_data = [{"snippet": "cached result", "title": "Cached", "url": "https://cached.com"}]
        search_cache.set_cached("cached query", count=10, result=cached_data)

        agent = WebSearchAgent()
        result = agent.step(prompt="cached query", count=10)

        assert result == cached_data
        # Application.call should NOT be called when cache hits
        mock_dashscope_app.call.assert_not_called()

    def test_step_cache_miss_calls_api(self, mock_dashscope_app):
        from agent.base_agent import WebSearchAgent
        from agent import search_cache

        search_cache.clear_cache()

        agent = WebSearchAgent()
        result = agent.step(prompt="uncached query", count=10)

        assert result is not None
        mock_dashscope_app.call.assert_called_once()

    def test_429_retry_with_backoff(self, mock_dashscope_app):
        from agent.base_agent import WebSearchAgent

        # First call raises 429-like error from post_process, second succeeds
        # The mock's default response is success, but we can make post_process fail first
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                # Return a response that post_process treats as 429
                inner = json.dumps({"status": 429, "request_id": "test-429"})
                bad_resp = MagicMock()
                bad_resp.status_code = 200
                bad_resp.output.text = json.dumps({"result": {"isError": True, "content": [{"text": inner}]}})
                return bad_resp
            return mock_dashscope_app._mock_call_original

        # Actually, the mock_dashscope_app fixture uses a class-level mock.
        # Let's test the concept differently — test that 429 in error raises correctly
        from agent.base_agent import WebSearchAgent

        # Mock Application.call to raise on first call
        with patch("agent.base_agent.Application") as mock_app:
            success_resp = MagicMock()
            success_resp.status_code = 200
            success_resp.output.text = json.dumps({
                "result": {"content": [{"text": json.dumps({"pages": [
                    {"snippet": "ok", "title": "OK", "url": "https://ok.com"}
                ]})}]}
            })

            mock_app.call.side_effect = [
                Exception("429"),  # First call fails with 429
                Exception("429"),  # Second call fails with 429
                success_resp,       # Third succeeds
            ]

            agent = WebSearchAgent()
            agent.set_step_prompt("{prompt}")
            result = agent.step(prompt="retry test", count=10)

            assert result is not None
            assert len(result) == 1
            assert mock_app.call.call_count == 3
