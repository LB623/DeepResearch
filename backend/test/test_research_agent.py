"""Integration tests for ResearchAgent sub-graph — nodes, routing, and graph topology."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langgraph.graph import StateGraph

from agent.state import OverallState
from agent.sub_agents.research_agent import (
    research_agent_graph,
    _generate_queries,
    _fan_out_to_web_search,
    _web_search,
    _critique,
    _route_after_critique,
    _GENERATE_QUERIES,
    _WEB_SEARCH,
    _CRITIQUE,
)


# ═══════════════════════════════════════════════════════════════════════
# Graph topology
# ═══════════════════════════════════════════════════════════════════════

class TestResearchAgentGraphTopology:
    def test_graph_is_compiled(self):
        assert research_agent_graph is not None
        assert hasattr(research_agent_graph, "nodes")

    def test_required_nodes_exist(self):
        nodes = list(research_agent_graph.nodes.keys())
        assert _GENERATE_QUERIES in nodes
        assert _WEB_SEARCH in nodes
        assert _CRITIQUE in nodes


# ═══════════════════════════════════════════════════════════════════════
# _generate_queries node (async)
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateQueries:
    def test_generates_queries_with_mocked_json_agent(self, sample_state):
        from agent.tools_and_schemas import SearchQueryList

        with patch("agent.sub_agents.research_agent._get_kb_store", return_value=None), \
             patch("agent.sub_agents.research_agent.JsonAgent") as mock_json_agent_cls:
            mock_agent = MagicMock()
            mock_agent.step = MagicMock(return_value=SearchQueryList(
                query=["q1", "q2"],
                rationale="test rationale",
            ))
            mock_json_agent_cls.return_value = mock_agent

            result = _generate_queries(sample_state, {"configurable": {}})
            assert "search_query" in result
            assert len(result["search_query"]) == 2

    def test_generates_queries_with_kb_hits(self, sample_state):
        from agent.tools_and_schemas import SearchQueryList

        mock_store = MagicMock()
        mock_store.query.return_value = [
            {"fact": "known fact 1", "source_url": "https://s.com/1", "relevance": 0.9},
            {"fact": "known fact 2", "source_url": "https://s.com/2", "relevance": 0.8},
        ]

        with patch("agent.sub_agents.research_agent._get_kb_store", return_value=mock_store), \
             patch("agent.sub_agents.research_agent.JsonAgent") as mock_json_agent_cls:
            mock_agent = MagicMock()
            mock_agent.step = MagicMock(return_value=SearchQueryList(
                query=["q1"],
                rationale="avoided known facts",
            ))
            mock_json_agent_cls.return_value = mock_agent

            result = _generate_queries(sample_state, {"configurable": {}})
            assert "search_query" in result
            mock_store.query.assert_called_once()

    def test_kb_failure_does_not_block(self, sample_state):
        from agent.tools_and_schemas import SearchQueryList

        with patch("agent.sub_agents.research_agent._get_kb_store", side_effect=Exception("KB down")), \
             patch("agent.sub_agents.research_agent.JsonAgent") as mock_json_agent_cls:
            mock_agent = MagicMock()
            mock_agent.step = MagicMock(return_value=SearchQueryList(
                query=["q1"],
                rationale="kb failed but we continue",
            ))
            mock_json_agent_cls.return_value = mock_agent

            result = _generate_queries(sample_state, {"configurable": {}})
            assert len(result["search_query"]) == 1


# ═══════════════════════════════════════════════════════════════════════
# _fan_out_to_web_search node (sync — pure data transform)
# ═══════════════════════════════════════════════════════════════════════

class TestFanOutToWebSearch:
    def test_fan_out_creates_one_send_per_query(self):
        state = {"search_query": ["q1", "q2", "q3"]}
        sends = _fan_out_to_web_search(state)
        assert len(sends) == 3
        assert sends[0].node == _WEB_SEARCH
        assert sends[0].arg["search_query"] == "q1"
        assert sends[0].arg["id"] == 0
        assert sends[2].arg["search_query"] == "q3"
        assert sends[2].arg["id"] == 2

    def test_fan_out_empty_queries(self):
        state = {"search_query": []}
        sends = _fan_out_to_web_search(state)
        assert len(sends) == 0


# ═══════════════════════════════════════════════════════════════════════
# _web_search node (async)
# ═══════════════════════════════════════════════════════════════════════

class TestWebSearchNode:
    def test_search_and_summarize_with_results(self, sample_state):
        sample_pages = [
            {"snippet": "AI chips growing fast", "title": "AI Report", "url": "https://real.com/1"},
        ]

        with patch("agent.sub_agents.research_agent.WebSearchAgent") as mock_ws_cls, \
             patch("agent.sub_agents.research_agent.Agent") as mock_agent_cls, \
             patch("agent.sub_agents.research_agent._get_kb_store", return_value=None):
            mock_searcher = MagicMock()
            mock_searcher.step = MagicMock(return_value=sample_pages)
            mock_ws_cls.return_value = mock_searcher

            mock_summarizer = MagicMock()
            mock_summarizer.step = MagicMock(return_value="```text\nSummarized content\n```")
            mock_agent_cls.return_value = mock_summarizer

            result = _web_search(
                {"search_query": "AI chips", "id": 0, "messages": sample_state["messages"]},
                {"configurable": {}},
            )

            assert "web_search_result" in result
            assert "sources_gathered" in result
            assert len(result["sources_gathered"]) == 1

    def test_empty_search_result_handled(self, sample_state):
        with patch("agent.sub_agents.research_agent.WebSearchAgent") as mock_ws_cls, \
             patch("agent.sub_agents.research_agent._get_kb_store", return_value=None):
            mock_searcher = MagicMock()
            mock_searcher.step = MagicMock(return_value=None)
            mock_ws_cls.return_value = mock_searcher

            result = _web_search(
                {"search_query": "no results", "id": 0, "messages": sample_state["messages"]},
                {"configurable": {}},
            )

            assert result["sources_gathered"] == []
            assert "未找到" in result["web_search_result"][0]


# ═══════════════════════════════════════════════════════════════════════
# _critique node (async)
# ═══════════════════════════════════════════════════════════════════════

class TestCritique:
    @pytest.mark.asyncio
    async def test_critique_returns_reflection(self, sample_state):
        from agent.tools_and_schemas import Reflection

        with patch("agent.sub_agents.research_agent.JsonAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.step = MagicMock(return_value=Reflection(
                is_sufficient=True,
                knowledge_gap="",
                follow_up_queries=[],
            ))
            mock_agent_cls.return_value = mock_agent

            result = _critique(sample_state, {"configurable": {}})

            assert result["is_sufficient"] is True
            assert result["research_loop_count"] == 1

    @pytest.mark.asyncio
    async def test_critique_insufficient_with_followup(self, sample_state):
        from agent.tools_and_schemas import Reflection

        with patch("agent.sub_agents.research_agent.JsonAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.step = MagicMock(return_value=Reflection(
                is_sufficient=False,
                knowledge_gap="缺少细分市场数据",
                follow_up_queries=["AI芯片细分市场", "中国AI芯片"],
            ))
            mock_agent_cls.return_value = mock_agent

            result = _critique(sample_state, {"configurable": {}})

            assert result["is_sufficient"] is False
            assert len(result["follow_up_queries"]) == 2


# ═══════════════════════════════════════════════════════════════════════
# _route_after_critique routing (sync — pure routing)
# ═══════════════════════════════════════════════════════════════════════

class TestRouteAfterCritique:
    def test_route_when_sufficient(self, sample_state):
        state = {**sample_state, "is_sufficient": True, "research_loop_count": 1}
        result = _route_after_critique(state, {"configurable": {}})
        assert result == "__end__"

    def test_route_when_max_loops_reached(self, sample_state):
        state = {
            **sample_state,
            "is_sufficient": False,
            "research_loop_count": 2,
            "max_research_loops": 2,
        }
        result = _route_after_critique(state, {"configurable": {}})
        assert result == "__end__"

    def test_route_continue_with_followup(self, sample_state):
        state = {
            **sample_state,
            "is_sufficient": False,
            "research_loop_count": 1,
            "max_research_loops": 3,
            "follow_up_queries": ["new query 1", "new query 2"],
            "number_of_ran_queries": 3,
        }
        result = _route_after_critique(state, {"configurable": {}})

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0].arg["search_query"] == "new query 1"


# ═══════════════════════════════════════════════════════════════════════
# TestWebSearchKBStorage — KB 存储路径覆盖
# ═══════════════════════════════════════════════════════════════════════

class TestWebSearchKBStorage:
    """测试 _web_search 节点中 KB 事实存储的错误/边界路径。"""

    def test_kb_store_facts_on_success(self, sample_state):
        """搜索成功 → 事实被提取并存入 KB。"""
        from agent.tools_and_schemas import Reflection  # noqa: 保持导入兼容

        with patch(
            "agent.sub_agents.research_agent.WebSearchAgent"
        ) as mock_searcher_cls, patch(
            "agent.sub_agents.research_agent.Agent"
        ) as mock_agent_cls, patch(
            "agent.sub_agents.research_agent._get_kb_store"
        ) as mock_get_store, patch(
            "agent.sub_agents.research_agent._get_kb_extractor"
        ) as mock_get_extractor:
            # 模拟搜索返回
            mock_searcher = MagicMock()
            mock_searcher.step = MagicMock(return_value=[
                {"snippet": "test", "title": "test", "url": "https://real.com/1"}
            ])
            mock_searcher_cls.return_value = mock_searcher

            # 模拟 LLM 汇总
            mock_agent = MagicMock()
            mock_agent.step = MagicMock(return_value="汇总：AI芯片市场增长强劲")
            mock_agent_cls.return_value = mock_agent

            # 模拟 KB store 可用
            mock_store = MagicMock()
            mock_get_store.return_value = mock_store

            # 模拟 extractor 返回事实
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [
                {"fact": "AI芯片市场500亿美元", "source_url": "https://a.com", "confidence": 0.9}
            ]
            mock_get_extractor.return_value = mock_extractor

            state = {
                "search_query": "AI芯片市场",
                "id": 0,
                "messages": sample_state["messages"],
            }
            from langchain_core.runnables import RunnableConfig  # noqa
            config: RunnableConfig = {"configurable": {}}

            result = _web_search(state, config)

            # 搜索结果仍然正常返回
            assert "web_search_result" in result
            assert len(result["web_search_result"]) > 0

            # KB store 被调用
            mock_store.add_facts.assert_called_once()

    def test_kb_store_none_skips_silently(self, sample_state):
        """KB store 为 None → 静默跳过。"""
        with patch(
            "agent.sub_agents.research_agent.WebSearchAgent"
        ) as mock_searcher_cls, patch(
            "agent.sub_agents.research_agent.Agent"
        ) as mock_agent_cls, patch(
            "agent.sub_agents.research_agent._get_kb_store"
        ) as mock_get_store:
            mock_searcher = MagicMock()
            mock_searcher.step = MagicMock(return_value=[
                {"snippet": "test", "title": "test", "url": "https://real.com/1"}
            ])
            mock_searcher_cls.return_value = mock_searcher

            mock_agent = MagicMock()
            mock_agent.step = MagicMock(return_value="汇总内容")
            mock_agent_cls.return_value = mock_agent

            mock_get_store.return_value = None  # ← KB 不可用

            state = {
                "search_query": "AI芯片市场",
                "id": 0,
                "messages": sample_state["messages"],
            }
            from langchain_core.runnables import RunnableConfig  # noqa
            config: RunnableConfig = {"configurable": {}}

            result = _web_search(state, config)
            # 不崩
            assert "web_search_result" in result

    def test_kb_store_exception_is_silent(self, sample_state):
        """KB 存储抛异常 → 静默捕获，不影响搜索结果返回。"""
        with patch(
            "agent.sub_agents.research_agent.WebSearchAgent"
        ) as mock_searcher_cls, patch(
            "agent.sub_agents.research_agent.Agent"
        ) as mock_agent_cls, patch(
            "agent.sub_agents.research_agent._get_kb_store"
        ) as mock_get_store, patch(
            "agent.sub_agents.research_agent._get_kb_extractor"
        ) as mock_get_extractor:
            mock_searcher = MagicMock()
            mock_searcher.step = MagicMock(return_value=[
                {"snippet": "test", "title": "test", "url": "https://real.com/1"}
            ])
            mock_searcher_cls.return_value = mock_searcher

            mock_agent = MagicMock()
            mock_agent.step = MagicMock(return_value="汇总内容")
            mock_agent_cls.return_value = mock_agent

            mock_store = MagicMock()
            mock_store.add_facts.side_effect = Exception("Milvus 服务崩溃")
            mock_get_store.return_value = mock_store

            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [
                {"fact": "某事实", "source_url": "https://x.com", "confidence": 0.9}
            ]
            mock_get_extractor.return_value = mock_extractor

            state = {
                "search_query": "AI芯片市场",
                "id": 0,
                "messages": sample_state["messages"],
            }
            from langchain_core.runnables import RunnableConfig  # noqa
            config: RunnableConfig = {"configurable": {}}

            result = _web_search(state, config)
            # 搜索结果仍然返回，不受 KB 异常影响
            assert "web_search_result" in result
            assert len(result["web_search_result"]) > 0
