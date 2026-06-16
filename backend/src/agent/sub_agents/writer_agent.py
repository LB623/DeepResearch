"""WriterAgent 子图，带有辩论循环优化功能。

它封装了报告撰写流程，采用迭代式评论员 ↔ 作者修改机制：
1. 提纲 — 设计章节结构
2. 草稿 — 撰写（或修改）内容
3. 评论员评审 — 对草稿进行评分并返回结构化反馈
4. 引用和润色 — 替换短链接、去重来源、最终润色

辩论循环（草稿 ↔ 评论员评审）重复进行，
直到评论员满意（ready_for_polish=True）或达到 max_revisions 次数上限。
"""

from __future__ import annotations

import json

from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from loguru import logger

from agent.base_agent import Agent, JsonAgent
from agent.configuration import Configuration
from agent.post import Post
from agent.prompts import (
    critic_review_instructions,
    draft_instructions,
    get_current_date,
    outline_instructions,
    polish_instructions,
)
from agent.state import OverallState
from agent.tools_and_schemas import CritiqueResult
from agent.utils import get_research_topic

load_dotenv()

_OUTLINE = "outline"
_DRAFT = "draft"
_CRITIC_REVIEW = "critic_review"
_CITE_AND_POLISH = "cite_and_polish"

# ── constants ──────────────────────────────────────────────────────────
DEFAULT_MAX_REVISIONS = 3
POLISH_THRESHOLD = 0.6  # ready_for_polish=True OR rating≥6 → proceed


# ═══════════════════════════════════════════════════════════════════════
# Node implementations
# ═══════════════════════════════════════════════════════════════════════

async def _outline(state: OverallState, config: RunnableConfig) -> dict:
    """Generate a structured report outline from the research topic and plan."""
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.answer_model
    logger.info(f"[WriterAgent] outline 准备使用模型={reasoning_model}")

    agent = Agent(model_id=reasoning_model)
    agent.set_step_prompt(outline_instructions)
    raw = await agent.astep(
        research_topic=get_research_topic(state["messages"]),
        research_proposal=state.get("plan", ""),
        summaries="\n---\n\n".join(state["web_search_result"]),
    )
    outline = Post.extract_pattern(raw, pattern="markdown")
    logger.info(f"[WriterAgent] outline 已生成 ({len(outline)} 字)")
    return {
        "report_outline": outline,
        "revision_count": 0,
        "max_revisions": DEFAULT_MAX_REVISIONS,
    }


async def _draft(state: OverallState, config: RunnableConfig) -> dict:
    """Draft (or revise) the full report following the outline.

    第一次尝试（无反馈）时，从头开始编写。
    修改过程中，会采纳评论者的结构化反馈意见，并且
    增加修改计数器。
    """
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.answer_model
    logger.info(f"[WriterAgent] _draft 准备使用模型={reasoning_model}")
    feedback = state.get("critic_feedback", "")
    outline_text = state.get("report_outline", "")
    is_revision = bool(feedback)
    revision = state.get("revision_count", 0) + (1 if is_revision else 0)

    if is_revision:
        logger.info(f"[WriterAgent] 修改稿 (revision {revision})")
        revision_context = (
            f"\n# 修订说明 (第 {revision} 次修订)\n"
            f"请根据以下审稿意见修改上一版草稿：\n\n"
            f"{feedback}\n\n"
            f"请逐条处理上述问题，优先修复 critical 和 major 级别的问题。"
            f"保留上版草稿中审稿人没有异议的内容。\n"
        )
        return_update = {"revision_count": revision, "critic_feedback": ""}
    else:
        logger.info(f"[WriterAgent] 从零开始撰写草稿")
        revision_context = ""
        return_update = {}

    agent = Agent(model_id=reasoning_model)
    agent.set_step_prompt(draft_instructions)
    raw = await agent.astep(
        current_date=get_current_date(),
        research_topic=get_research_topic(state["messages"]),
        research_proposal=state.get("plan", ""),
        outline=outline_text,
        summaries="\n---\n\n".join(state["web_search_result"]),
        revision_context=revision_context,
    )
    draft = Post.extract_pattern(raw, pattern="markdown")
    logger.info(f"[WriterAgent] draft 已生成 ({len(draft)} 字)")
    return {**return_update, "report_draft": draft}


async def _critic_review(state: OverallState, config: RunnableConfig) -> dict:
    """Critic reviews the draft and returns structured feedback.

    使用 JsonAgent 和 CritiqueResult 模式生成结构化输出。
    """
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.answer_model
    logger.info(f"[WriterAgent] critic reviewing draft 准备使用模型={reasoning_model}")

    draft_text = state.get("report_draft", "")

    agent = JsonAgent(model_id=reasoning_model, keys=CritiqueResult)
    agent.set_step_prompt(critic_review_instructions)
    result: CritiqueResult = await agent.astep(
        research_topic=get_research_topic(state["messages"]),
        research_proposal=state.get("plan", ""),
        summaries="\n---\n\n".join(state["web_search_result"]),
        draft=draft_text,
    )

    # 针对修改稿的点评反馈
    if result.issues:
        issues_text = "\n".join(
            f"- [{iss.severity.upper()}] {iss.location}: {iss.problem}\n"
            f"  建议: {iss.suggestion}"
            for iss in result.issues
        )
    else:
        issues_text = "无明显问题。"

    feedback = (
        f"## 审稿评分: {result.overall_rating}/10\n"
        f"## 综合评价: {result.summary}\n\n"
        f"## 具体问题:\n{issues_text}"
    )

    logger.info(
        f"[WriterAgent] 审稿评分={result.overall_rating}/10, "
        f"issues={len(result.issues)} "
        f"(critical={sum(1 for i in result.issues if i.severity=='critical')}, "
        f"主要的={sum(1 for i in result.issues if i.severity=='major')}, "
        f"次要的={sum(1 for i in result.issues if i.severity=='minor')}), "
        f"准备润色={result.ready_for_polish}"
    )

    return {
        "critic_feedback": feedback,
        "critic_score": result.overall_rating,
        "ready_for_polish": result.ready_for_polish,
    }


def _route_after_critic(state: OverallState, config: RunnableConfig) -> str:
    """决定：继续修改或进入终审润色。

    进入润色的条件：
      - Critic 明确标记 ready_for_polish，或
      - revision_count >= max_revisions（安全兜底）

    否则回到 draft 继续修改。
    """
    revision = state.get("revision_count", 0)
    max_rev = state.get("max_revisions", DEFAULT_MAX_REVISIONS)
    ready = state.get("ready_for_polish", False)

    if ready:
        logger.info(f"[WriterAgent] Critic ready_for_polish → polish")
        return _CITE_AND_POLISH

    if revision >= max_rev:
        logger.info(f"[WriterAgent] 已达到最大修改次数 ({revision}/{max_rev}) → polish")
        return _CITE_AND_POLISH

    logger.info(f"[WriterAgent] needs revision (rev={revision}/{max_rev}) → draft")
    return _DRAFT


async def _cite_and_polish(state: OverallState, config: RunnableConfig) -> dict:
    """Finalise: LLM polish + replace short URLs with real URLs + deduplicate sources."""
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.answer_model
    logger.info(f"[WriterAgent] polishing 准备使用模型={reasoning_model}")

    draft_text = state.get("report_draft", "")

    # Step A — LLM polish pass
    agent = Agent(model_id=reasoning_model)
    agent.set_step_prompt(polish_instructions)
    raw = await agent.astep(
        research_topic=get_research_topic(state["messages"]),
        draft=draft_text,
        summaries="\n---\n\n".join(state["web_search_result"]),
    )
    polished = Post.extract_pattern(raw, pattern="markdown")

    unique_sources = []
    for source in state.get("sources_gathered", []):
        if source["short_url"] in polished:
            polished = polished.replace(source["short_url"], source["value"])
            unique_sources.append(source)

    logger.info(
        f"[WriterAgent] 已润色 ({len(polished)} 字), "
        f"{len(unique_sources)} 个引用来源, "
        f"{state.get('revision_count', 0)} revision(s)"
    )
    return {
        "messages": [AIMessage(content=polished)],
        "sources_gathered": unique_sources,
    }


# ═══════════════════════════════════════════════════════════════════════
# 构建子图（带循环）
# ═══════════════════════════════════════════════════════════════════════

_builder = StateGraph(OverallState, config_schema=Configuration)

_builder.add_node(_OUTLINE, _outline) # 生成大纲
_builder.add_node(_DRAFT, _draft)  # 写草稿 / 修订
_builder.add_node(_CRITIC_REVIEW, _critic_review) # 审稿
_builder.add_node(_CITE_AND_POLISH, _cite_and_polish) # 终稿

# Flow: outline → draft → critic → (loop or polish)
_builder.add_edge(START, _OUTLINE)
_builder.add_edge(_OUTLINE, _DRAFT)
_builder.add_edge(_DRAFT, _CRITIC_REVIEW)
_builder.add_conditional_edges(
    _CRITIC_REVIEW,
    _route_after_critic,
    [_DRAFT, _CITE_AND_POLISH],
)
_builder.add_edge(_CITE_AND_POLISH, END)

writer_agent_graph = _builder.compile(name="WriterAgent")

# try:
#     display(Image(writer_agent_graph.get_graph().draw_mermaid_png(output_file_path="./WriterAgent子图.png")))
# except Exception:
#     pass