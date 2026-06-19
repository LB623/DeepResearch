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

import re

from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from loguru import logger

from agent.base_agent import Agent, JsonAgent
from agent.checkpoint import get_checkpointer
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
_MATERIAL_CITATION_RE = re.compile(
    r"\[(材料|material|Material|source|Source)\s*[-_:：]?\s*(\d{1,3})\](?!\()"
)
_SHORT_URL_INDEX_RE = re.compile(r"/id/\d+-(\d+)$")
_SHORT_URL_PAIR_RE = re.compile(r"/id/(\d+)-(\d+)$")
_INTERNAL_CITATION_RE = re.compile(
    r"\[\[?(?:(?:https?://)?search\.com/)?(?:id/)?(\d+)-(\d+)\]?\](?!\()"
)
_NAMED_TERM_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9]{2,}|[A-Z][a-z]{2,8})\b")
_GENERIC_NAMED_TERMS = {
    "AI", "API", "HTTP", "HTTPS", "JSON", "LLM", "Markdown", "RAG", "URL",
    "Based", "Conclusion", "However", "Overview", "Report", "Risk", "Source",
    "Therefore", "These", "This", "Tool",
}
_NAMED_CLAIM_CONTEXT = ("工具", "模型", "平台", "框架", "产品", "系统", "标准", "项目", "公司")
_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,2})\s+(.+?)\s*$", re.MULTILINE)
_MARKDOWN_URL_RE = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)")
_MIN_POLISH_LENGTH_RATIO = 0.75


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
        logger.info("[WriterAgent] 从零开始撰写草稿")
        revision_context = ""
        return_update = {}

    previous_draft = state.get("report_draft", "") if is_revision else ""

    agent = Agent(model_id=reasoning_model)
    agent.set_step_prompt(draft_instructions)
    raw = await agent.astep(
        current_date=get_current_date(),
        research_topic=get_research_topic(state["messages"]),
        research_proposal=state.get("plan", ""),
        outline=outline_text,
        summaries="\n---\n\n".join(state["web_search_result"]),
        revision_context=revision_context,
        previous_draft=previous_draft,
    )
    draft = Post.extract_pattern(raw, pattern="markdown")
    rejection_reason = _draft_rejection_reason(outline_text, draft)
    if rejection_reason:
        logger.warning(
            f"[WriterAgent] draft incomplete ({rejection_reason}); "
            "retrying once with explicit completion instructions"
        )
        recovery_context = (
            f"{revision_context}\n"
            "# 完整性修复\n"
            "上一版输出不完整。请以该版本为基础补齐报告大纲中的所有章节，"
            "保留已有有效内容和引用。材料不足的章节明确写出证据边界，"
            "但不得省略章节或停在标题、列表、模板开头。\n"
        )
        retry_raw = await agent.astep(
            current_date=get_current_date(),
            research_topic=get_research_topic(state["messages"]),
            research_proposal=state.get("plan", ""),
            outline=outline_text,
            summaries="\n---\n\n".join(state["web_search_result"]),
            revision_context=recovery_context,
            previous_draft=draft,
        )
        retry_draft = Post.extract_pattern(retry_raw, pattern="markdown")
        retry_reason = _draft_rejection_reason(outline_text, retry_draft)
        if retry_reason is None or len(retry_draft) > len(draft):
            draft = retry_draft
        if retry_reason:
            logger.warning(f"[WriterAgent] recovered draft still incomplete: {retry_reason}")
    logger.info(f"[WriterAgent] draft 已生成 ({len(draft)} 字)")
    return {**return_update, "report_draft": draft}


async def _critic_review(state: OverallState, config: RunnableConfig) -> dict:
    """Critic reviews the draft and returns structured feedback.

    使用 JsonAgent 和 CritiqueResult 模式生成结构化输出。
    """
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.reflection_model
    logger.info(f"[WriterAgent] critic reviewing draft 准备使用模型={reasoning_model}")

    draft_text = state.get("report_draft", "")
    summaries_text = "\n---\n\n".join(state["web_search_result"])
    research_topic = get_research_topic(state["messages"])
    unsupported_named_terms = _unsupported_named_terms(
        draft_text,
        evidence=summaries_text,
        research_topic=research_topic,
    )

    agent = JsonAgent(model_id=reasoning_model, keys=CritiqueResult)
    agent.set_step_prompt(critic_review_instructions)
    result: CritiqueResult = await agent.astep(
        research_topic=research_topic,
        research_proposal=state.get("plan", ""),
        summaries=summaries_text,
        unsupported_named_terms=(
            ", ".join(unsupported_named_terms) if unsupported_named_terms else "无"
        ),
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
        logger.info("[WriterAgent] Critic ready_for_polish → polish")
        return _CITE_AND_POLISH

    if revision >= max_rev:
        logger.info(f"[WriterAgent] 已达到最大修改次数 ({revision}/{max_rev}) → polish")
        return _CITE_AND_POLISH

    logger.info(f"[WriterAgent] needs revision (rev={revision}/{max_rev}) → draft")
    return _DRAFT


def _source_key(source: dict) -> str:
    return source.get("short_url") or source.get("value") or repr(source)


def _source_for_material_index(sources: list[dict], index: int) -> dict | None:
    """Resolve `[材料-02]` to the corresponding gathered source.

    The model tends to number materials by the order it saw in the final prompt.
    If that order is unavailable, fall back to the trailing index in the
    internal short URL, e.g. `https://search.com/id/0-2`.
    """
    if 0 <= index < len(sources):
        return sources[index]

    for source in sources:
        match = _SHORT_URL_INDEX_RE.search(source.get("short_url", ""))
        if match and int(match.group(1)) == index:
            return source
    return None


def _normalize_citations(polished: str, sources: list[dict]) -> tuple[str, list[dict]]:
    """Convert internal citation forms into user-facing markdown links."""
    unique_sources: list[dict] = []
    seen: set[str] = set()

    def add_source(source: dict) -> None:
        key = _source_key(source)
        if key not in seen:
            seen.add(key)
            unique_sources.append(source)

    for source in sources:
        short_url = source.get("short_url")
        value = source.get("value")
        if short_url and value and short_url in polished:
            polished = polished.replace(short_url, value)
            add_source(source)
        elif value and value in polished:
            add_source(source)

    sources_by_pair: dict[tuple[int, int], dict] = {}
    for source in sources:
        match = _SHORT_URL_PAIR_RE.search(source.get("short_url", ""))
        if match:
            sources_by_pair[(int(match.group(1)), int(match.group(2)))] = source

    def replace_internal_citation(match: re.Match[str]) -> str:
        pair = (int(match.group(1)), int(match.group(2)))
        source = sources_by_pair.get(pair)
        value = source.get("value") if source else None
        if not value:
            return match.group(0)
        add_source(source)
        label = f"{pair[0]}-{pair[1]}"
        return f"[{label}]({value})"

    polished = _INTERNAL_CITATION_RE.sub(replace_internal_citation, polished)

    def replace_material(match: re.Match[str]) -> str:
        label = match.group(0)[1:-1]
        index = int(match.group(2))
        source = _source_for_material_index(sources, index)
        value = source.get("value") if source else None
        if not value:
            return match.group(0)
        add_source(source)
        return f"[{label}]({value})"

    polished = _MATERIAL_CITATION_RE.sub(replace_material, polished)
    return polished, unique_sources


def _normalized_headings(markdown: str) -> set[str]:
    """Return stable H1/H2 labels used for final-report completeness checks."""
    return {
        re.sub(r"\s+", " ", heading).strip().lower()
        for _, heading in _MARKDOWN_HEADING_RE.findall(markdown or "")
    }


def _outline_sections(markdown: str) -> set[str]:
    """Return H2 section labels that every complete draft must preserve."""
    return {
        re.sub(r"\s+", " ", heading).strip().lower()
        for marker, heading in _MARKDOWN_HEADING_RE.findall(markdown or "")
        if marker == "##"
    }


def _markdown_urls(markdown: str) -> set[str]:
    return set(_MARKDOWN_URL_RE.findall(markdown or ""))


def _named_terms(text: str) -> set[str]:
    return {
        term
        for term in _NAMED_TERM_RE.findall(text or "")
        if term not in _GENERIC_NAMED_TERMS
    }


def _named_terms_in_claim_context(text: str) -> set[str]:
    terms: set[str] = set()
    for line in (text or "").splitlines():
        if any(marker in line for marker in _NAMED_CLAIM_CONTEXT):
            terms.update(_named_terms(line))
    return terms


def _unsupported_named_terms(
    draft: str,
    *,
    evidence: str,
    research_topic: str,
) -> list[str]:
    allowed_text = f"{research_topic}\n{evidence}".casefold()
    return sorted(
        term for term in _named_terms(draft) if term.casefold() not in allowed_text
    )


def _draft_rejection_reason(outline: str, draft: str) -> str | None:
    if not draft.strip() or draft.lstrip().startswith("```markdown"):
        return "empty or unterminated markdown output"

    missing_sections = _outline_sections(outline) - _outline_sections(draft)
    if missing_sections:
        preview = ", ".join(sorted(missing_sections)[:3])
        return f"missing outline sections: {preview}"
    return None


def _polish_rejection_reason(
    draft: str,
    polished: str,
    sources: list[dict],
) -> str | None:
    """Reject incomplete polish output or citations not present in gathered evidence."""
    if not polished.strip() or polished.lstrip().startswith("```markdown"):
        return "empty or unterminated markdown output"

    if len(draft) >= 1000 and len(polished) < len(draft) * _MIN_POLISH_LENGTH_RATIO:
        return (
            f"output too short ({len(polished)} < "
            f"{_MIN_POLISH_LENGTH_RATIO:.0%} of draft {len(draft)})"
        )

    missing_headings = _normalized_headings(draft) - _normalized_headings(polished)
    if missing_headings:
        preview = ", ".join(sorted(missing_headings)[:3])
        return f"missing report headings: {preview}"

    allowed_urls = _markdown_urls(draft)
    for source in sources:
        allowed_urls.update(
            url
            for url in (source.get("short_url"), source.get("value"))
            if url
        )
    unknown_urls = _markdown_urls(polished) - allowed_urls
    if unknown_urls:
        return f"unknown citation URL: {sorted(unknown_urls)[0]}"

    new_named_terms = _named_terms_in_claim_context(polished) - _named_terms(draft)
    if new_named_terms:
        return f"new named terms introduced during polish: {', '.join(sorted(new_named_terms)[:3])}"

    return None


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
        critic_feedback=state.get("critic_feedback", ""),
    )
    polished = Post.extract_pattern(raw, pattern="markdown")

    rejection_reason = _polish_rejection_reason(
        draft_text,
        polished,
        state.get("sources_gathered", []),
    )
    if rejection_reason:
        logger.warning(
            f"[WriterAgent] polish rejected ({rejection_reason}); "
            "falling back to complete draft"
        )
        polished = draft_text

    polished, unique_sources = _normalize_citations(
        polished,
        state.get("sources_gathered", []),
    )

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

writer_agent_graph = _builder.compile(checkpointer=get_checkpointer(), name="WriterAgent")

# try:
#     display(Image(writer_agent_graph.get_graph().draw_mermaid_png(output_file_path="./WriterAgent子图.png")))
# except Exception:
#     pass
