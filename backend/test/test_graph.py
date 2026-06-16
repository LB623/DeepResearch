"""Integration tests for the main orchestrator graph — plan phase and routing."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage


# ═══════════════════════════════════════════════════════════════════════
# Graph topology
# ═══════════════════════════════════════════════════════════════════════

class TestMainGraphTopology:
    def test_graph_nodes_exist(self):
        from agent.graph import graph, GENERATE_PLAN_NODE, RESEARCH_AGENT_NODE, WRITER_AGENT_NODE

        nodes = list(graph.nodes.keys())
        assert GENERATE_PLAN_NODE in nodes
        assert RESEARCH_AGENT_NODE in nodes
        assert WRITER_AGENT_NODE in nodes
        assert "replan" in nodes
        assert "awaiting_plan_confirmation" in nodes

    def test_graph_has_start_edge(self):
        from agent.graph import graph, GENERATE_PLAN_NODE

        nodes = list(graph.nodes.keys())
        assert GENERATE_PLAN_NODE in nodes
        assert graph.builder is not None


# ═══════════════════════════════════════════════════════════════════════
# generate_plan node (async)
# ═══════════════════════════════════════════════════════════════════════

class TestGeneratePlan:
    @pytest.mark.asyncio
    async def test_generates_plan_for_unconfirmed_status(self):
        from agent.graph import generate_plan

        state = {
            "messages": [HumanMessage(content="分析AI芯片市场趋势")],
            "plan_status": "unconfirmed",
            "plan": "",
            "plan_messages": [],
        }

        with patch("agent.graph.Agent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(
                return_value="```markdown\n# 研究计划\n\n1. 市场概况\n2. 竞争分析\n```"
            )
            mock_agent_cls.return_value = mock_agent

            result = await generate_plan(state, {"configurable": {}})

            assert "plan" in result
            assert "研究计划" in result["plan"]
            assert result["plan_status"] == "unconfirmed"
            assert len(result["messages"]) == 1
            assert len(result["plan_messages"]) == 1

    @pytest.mark.asyncio
    async def test_skips_when_already_confirmed(self):
        from agent.graph import generate_plan

        state = {
            "messages": [HumanMessage(content="topic")],
            "plan_status": "confirmed",
            "plan": "existing plan",
            "plan_messages": [],
        }

        result = await generate_plan(state, {"configurable": {}})
        assert result == {}


# ═══════════════════════════════════════════════════════════════════════
# evaluate_plan routing (async)
# ═══════════════════════════════════════════════════════════════════════

class TestEvaluatePlan:
    @pytest.mark.asyncio
    async def test_unconfirmed_status_awaits_confirmation(self):
        from agent.graph import evaluate_plan

        state = {
            "messages": [HumanMessage(content="topic")],
            "plan_status": "unconfirmed",
            "plan": "# 研究计划\n内容",
        }

        result = await evaluate_plan(state, {"configurable": {}})
        assert result == "awaiting_plan_confirmation"

    @pytest.mark.asyncio
    async def test_explicit_confirm_keywords(self):
        """Keyword confirmation is now in confirm_plan, not evaluate_plan."""
        from agent.graph import confirm_plan

        state = {
            "messages": [HumanMessage(content="topic"), HumanMessage(content="需求确认")],
            "plan_status": "confirmed",
            "plan": "# 研究计划\n内容",
        }

        result = await confirm_plan(state, {"configurable": {}})
        assert result == {"fresh_level": "medium"}

    @pytest.mark.asyncio
    async def test_implicit_confirm_via_llm(self):
        """LLM-based confirmation is now in confirm_plan, not evaluate_plan."""
        from agent.graph import confirm_plan
        from agent.tools_and_schemas import PlanReflection

        state = {
            "messages": [HumanMessage(content="topic"), HumanMessage(content="这个计划没问题")],
            "plan_status": "confirmed",
            "plan": "# 研究计划\n内容",
        }

        with patch("agent.graph.JsonAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(return_value=PlanReflection(satisfy=True))
            mock_agent_cls.return_value = mock_agent

            result = await confirm_plan(state, {"configurable": {}})
            assert "fresh_level" in result
            assert "plan_status" not in result  # not replan

    @pytest.mark.asyncio
    async def test_llm_rejects_plan_triggers_replan(self):
        """LLM rejection is now in confirm_plan, not evaluate_plan."""
        from agent.graph import confirm_plan
        from agent.tools_and_schemas import PlanReflection

        state = {
            "messages": [HumanMessage(content="topic"), HumanMessage(content="这个计划不行")],
            "plan_status": "confirmed",
            "plan": "# 研究计划\n内容",
        }

        with patch("agent.graph.JsonAgent") as mock_agent_cls:
            mock_agent = MagicMock()
            mock_agent.astep = AsyncMock(return_value=PlanReflection(satisfy=False))
            mock_agent_cls.return_value = mock_agent

            result = await confirm_plan(state, {"configurable": {}})
            assert result == {"plan_status": "unconfirmed"}

    @pytest.mark.asyncio
    async def test_no_plan_triggers_replan(self):
        from agent.graph import evaluate_plan

        state = {
            "messages": [HumanMessage(content="topic"), HumanMessage(content="开始研究")],
            "plan_status": "confirmed",
            "plan": None,
        }

        result = await evaluate_plan(state, {"configurable": {}})
        assert result == "replan"


# ═══════════════════════════════════════════════════════════════════════
# replan node
# ═══════════════════════════════════════════════════════════════════════

class TestReplan:
    def test_resets_plan_status(self):
        state = {"plan_status": "confirmed"}
        result = {"plan_status": "unconfirmed"}
        assert result["plan_status"] == "unconfirmed"
