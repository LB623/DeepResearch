"""DeepResearch多智能体
由三个子智能体组成：
1. 计划阶段（图内，包含人机交互）
2. 研究智能体（子图）— 查询 → 搜索 → 评估循环
3. 写作智能体（子图）— 提纲 → 草稿 → 引用和润色
原有的单体图已重构，每个阶段都成为一个自包含、可独立测试的子图。
"""

import time
from collections.abc import Mapping
from typing import Any, cast

from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from loguru import logger

from agent.base_agent import Agent, JsonAgent
from agent.budget import budget_stop_reason, is_global_budget_stop, usage_updates
from agent.checkpoint import get_checkpointer
from agent.configuration import Configuration
from agent.post import Post
from agent.prompts import (
    get_current_date,
    plan_instructions,
    plan_reflection_instructions,
)
from agent.state import OverallState
from agent.sub_agents import research_agent_graph, writer_agent_graph
from agent.tools_and_schemas import PlanReflection
from agent.utils import (
    get_last_user_response,
    get_research_topic,
)

load_dotenv()

GENERATE_PLAN_NODE = "generate_plan"
RESEARCH_AGENT_NODE = "research"
WRITER_AGENT_NODE = "write"



async def generate_plan(state: OverallState, config: RunnableConfig) -> dict:
    """Generate a research plan based on the user's topic.

    Only runs when plan_status is "unconfirmed"; skipped on resubmit.
    """
    if state.get("plan_status", "unconfirmed") != "unconfirmed":
        return {}

    started_at = state.get("run_started_at") or time.time()
    reason = budget_stop_reason(
        {**state, "run_started_at": started_at},
        config,
    )
    if reason:
        return {
            "run_started_at": started_at,
            "budget_stop_reason": reason,
        }

    configurable = Configuration.from_runnable_config(config)
    agent = Agent(model_id=configurable.query_generator_model)
    agent.set_step_prompt(plan_instructions)
    response = await agent.astep(
        current_date=get_current_date(),
        research_topic=get_research_topic(
            state["messages"],
            [m.content for m in state.get("plan_messages", [])],
        ),
        research_proposal=state.get("plan", ""),
    )
    response = Post.extract_pattern(response, pattern="markdown")
    logger.info(f"[MainGraph] 生成的计划 ({len(response)} 字)")

    return {
        "messages": [AIMessage(content=response)],
        "plan": response,
        "plan_status": "unconfirmed",
        "plan_messages": [AIMessage(content=response)],
        **usage_updates(state, config, agent, started_at=started_at),
    }


async def evaluate_plan(state: OverallState, config: RunnableConfig) -> str:
    """计划生成后的路由。

    返回值：

    "awaiting_plan_confirmation" — 停止，等待人工输入

    "replan" — 重新生成路线规划

    "confirm_plan" — 计划已提交确认，进入评估节点
    """
    if is_global_budget_stop(state):
        logger.info(
            f"[MainGraph] budget exhausted: {state['budget_stop_reason']} → stop"
        )
        return END

    if state.get("plan_status", "unconfirmed") == "unconfirmed":
        logger.info("[MainGraph] 等待用户确认计划")
        return "awaiting_plan_confirmation"

    if not state.get("plan"):
        logger.info("[MainGraph] 没有计划可评估 → 重新计划")
        return "replan"

    logger.info("[MainGraph] 计划已提交确认 → 评估")
    return "confirm_plan"


async def confirm_plan(state: OverallState, config: RunnableConfig) -> dict:
    """评估计划确认并设置新鲜度等级。

    仅当 plan_status 为 "confirmed"（用户已提交确认）时进入此节点。
    根据用户消息中的关键词或 LLM 评估结果，决定是进入研究阶段还是重新规划。
    """
    started_at = state.get("run_started_at") or time.time()
    reason = budget_stop_reason(
        {**state, "run_started_at": started_at},
        config,
    )
    if reason:
        return {
            "run_started_at": started_at,
            "budget_stop_reason": reason,
        }

    configurable = Configuration.from_runnable_config(config)
    context = get_last_user_response(state["messages"])

    if "开始研究" in context or "需求确认" in context:
        logger.info("[MainGraph] plan explicitly confirmed → research")
        return {"fresh_level": "medium"}

    agent = JsonAgent(model_id=configurable.query_generator_model, keys=PlanReflection)
    agent.set_step_prompt(plan_reflection_instructions)
    result = await agent.astep(
        research_proposal=state.get("plan", ""),
        context=context,
    )
    budget_updates = usage_updates(
        state,
        config,
        agent,
        started_at=started_at,
    )
    if result.satisfy:
        logger.info("[MainGraph] plan implicitly confirmed → research")
        return {
            "fresh_level": getattr(result, "fresh_level", "medium"),
            **budget_updates,
        }

    logger.info("[MainGraph] 计划未确认 → 重新计划")
    return {"plan_status": "unconfirmed", **budget_updates}


def route_after_confirm(state: OverallState) -> str:
    """计划确认后的路由：进入研究阶段或重新规划。"""
    if is_global_budget_stop(state):
        return END
    if state.get("plan_status", "confirmed") == "unconfirmed":
        return "replan"
    return RESEARCH_AGENT_NODE


def route_after_research(state: OverallState) -> str:
    return WRITER_AGENT_NODE


_ADDITIVE_LIST_FIELDS = {
    "messages",
    "plan_messages",
    "search_query",
    "generated_queries",
    "executed_queries",
    "skipped_duplicate_queries",
    "web_search_result",
    "sources_gathered",
    "follow_up_queries",
}
_ADDITIVE_COUNTER_FIELDS = {"web_search_call_count", "llm_token_count"}


def _subgraph_delta_updates(
    parent: Mapping[str, Any],
    child: Mapping[str, Any],
) -> dict[str, Any]:
    """Convert a subgraph's accumulated state into parent reducer-safe deltas."""
    updates: dict[str, Any] = {}
    for key, value in child.items():
        previous = parent.get(key)
        if key in _ADDITIVE_COUNTER_FIELDS:
            delta = int(value or 0) - int(previous or 0)
            if delta:
                updates[key] = delta
            continue
        if key in _ADDITIVE_LIST_FIELDS:
            old_items = list(previous or [])
            new_items = list(value or [])
            if new_items[:len(old_items)] == old_items:
                suffix = new_items[len(old_items):]
                if suffix:
                    updates[key] = suffix
            continue
        if value != previous:
            updates[key] = value
    return updates


async def run_research_subgraph(
    state: OverallState,
    config: RunnableConfig,
) -> dict[str, Any]:
    result = await research_agent_graph.ainvoke(
        cast(OverallState, dict(state)),
        config=config,
    )
    return _subgraph_delta_updates(state, result)


async def run_writer_subgraph(
    state: OverallState,
    config: RunnableConfig,
) -> dict[str, Any]:
    result = await writer_agent_graph.ainvoke(
        cast(OverallState, dict(state)),
        config=config,
    )
    updates = _subgraph_delta_updates(state, result)
    # The writer uses a deduplicated source list only to render its final report.
    # ``sources_gathered`` is additive in the parent, so returning it here would
    # append those sources a second time.
    updates.pop("sources_gathered", None)
    return updates

builder = StateGraph(OverallState, context_schema=Configuration)

builder.add_node(GENERATE_PLAN_NODE, generate_plan)
builder.add_node("confirm_plan", confirm_plan)
builder.add_node(
    "replan",
    lambda state, config: {"plan_status": "unconfirmed"},
)
builder.add_node(
    "awaiting_plan_confirmation",
    lambda state, config: {},
)

# -- 子图节点 --
builder.add_node(RESEARCH_AGENT_NODE, run_research_subgraph)
builder.add_node(WRITER_AGENT_NODE, run_writer_subgraph)

builder.add_edge(START, GENERATE_PLAN_NODE)
builder.add_conditional_edges(
    GENERATE_PLAN_NODE,
    evaluate_plan,
    ["confirm_plan", "replan", "awaiting_plan_confirmation", END],
)
builder.add_conditional_edges(
    "confirm_plan",
    route_after_confirm,
    [RESEARCH_AGENT_NODE, "replan", END],
)
builder.add_edge("replan", GENERATE_PLAN_NODE)
builder.add_conditional_edges(
    RESEARCH_AGENT_NODE,
    route_after_research,
    [WRITER_AGENT_NODE],
)
builder.add_edge(WRITER_AGENT_NODE, END)

# -- compile --
graph = builder.compile(checkpointer=get_checkpointer(), name="pro-research-agent")
