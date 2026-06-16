"""Shared fixtures and mock helpers for the DeepResearch test suite."""

import os
import pytest
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════════════════
# Environment fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Set up environment variables for all tests.

    Autouse ensures every test runs with a clean, predictable env."""
    monkeypatch.setenv("APP_TOKEN", "test-api-key-12345")
    monkeypatch.setenv("LLM_BASE_URL", "https://test-llm.example.com/v1")
    monkeypatch.setenv("MCP_APP_ID", "test-mcp-app-id")
    monkeypatch.setenv(
        "AVAILABLE_MODELS",
        '[{"model_id":"qwen-test","display_name":"Qwen-Test","icon":"Zap","icon_color":"yellow-400"}]',
    )
    monkeypatch.setenv("WEB_SEARCH_MAX_QPS", "100")
    monkeypatch.setenv("MILVUS_URI", "http://localhost:19530")
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-embedding-key")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "https://test-embedding.example.com/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-v3")
    monkeypatch.delenv("NUMBER_OF_INITIAL_QUERIES", raising=False)
    monkeypatch.delenv("MAX_RESEARCH_LOOPS", raising=False)
    monkeypatch.delenv("QUERY_GENERATOR_MODEL", raising=False)
    monkeypatch.delenv("REFLECTION_MODEL", raising=False)
    monkeypatch.delenv("ANSWER_MODEL", raising=False)


# ═══════════════════════════════════════════════════════════════════════
# Sample data fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_messages():
    """Minimal message list for tests that need messages."""
    from langchain_core.messages import HumanMessage

    return [HumanMessage(content="分析AI芯片市场趋势")]


@pytest.fixture
def sample_state():
    """Minimal OverallState dict for sub-agent tests."""
    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content="分析AI芯片市场趋势")],
        "plan": "# 研究计划\n分析AI芯片市场",
        "plan_status": "confirmed",
        "plan_messages": [],
        "search_query": [],
        "web_search_result": ["AI芯片市场规模达500亿美元", "NVIDIA占据80%市场份额"],
        "sources_gathered": [
            {"short_url": "https://search.com/id/0-0", "value": "https://real.com/1", "label": "Source 1"},
            {"short_url": "https://search.com/id/0-1", "value": "https://real.com/2", "label": "Source 2"},
        ],
        "initial_search_query_count": 2,
        "max_research_loops": 2,
        "research_loop_count": 0,
        "reasoning_model": "qwen-test",
        "report_outline": "",
        "report_draft": "",
        "critic_feedback": "",
        "critic_score": 0.0,
        "revision_count": 0,
        "max_revisions": 3,
    }


@pytest.fixture
def sample_web_results():
    """Sample processed web search results (list of dicts)."""
    return [
        {"snippet": "AI芯片市场2025年达500亿美元", "title": "AI Chip Market Report", "url": "https://real.com/1"},
        {"snippet": "NVIDIA占据80%市场份额", "title": "NVIDIA Market Share", "url": "https://real.com/2"},
    ]


# ═══════════════════════════════════════════════════════════════════════
# Mock helper fixtures — LLM layer
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_openai_response():
    """Create a mock OpenAI chat completion response."""
    def _make(content="mock LLM response"):
        choice = MagicMock()
        choice.message.content = content
        response = MagicMock()
        response.choices = [choice]
        return response
    return _make


@pytest.fixture
def mock_openai_client(mock_openai_response):
    """Patch the OpenAI client constructor to return a mock."""
    with patch("agent.llm.llm.OpenAI") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_openai_response()
        mock_client_cls.return_value = mock_client
        yield mock_client


# ═══════════════════════════════════════════════════════════════════════
# Mock helper fixtures — MCP / dashscope
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_dashscope_app():
    """Patch dashscope Application.call to return a mock success response."""
    with patch("agent.base_agent.Application") as mock_app:
        def _make_response(pages=None):
            if pages is None:
                pages = [
                    {"snippet": "Test snippet", "title": "Test Title", "url": "https://example.com"},
                ]
            inner_json = '{"pages": ' + __import__('json').dumps(pages, ensure_ascii=False) + '}'
            resp = MagicMock()
            resp.status_code = 200
            resp.output.text = '{"result": {"content": [{"text": "' + inner_json.replace('"', '\\"') + '"}]}}'
            return resp

        mock_app.call.return_value = _make_response()
        yield mock_app
