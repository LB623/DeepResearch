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
import time
from typing import Any
from urllib.parse import urlsplit

from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from loguru import logger

from agent.base_agent import Agent, JsonAgent
from agent.budget import (
    agent_total_tokens,
    budget_stop_reason,
    is_global_budget_stop,
    token_usage_updates,
    usage_updates,
)
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
_BUDGET_GUARD = "budget_guard"
_FALLBACK_REPORT = "fallback_report"

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
_MEDIA_KIND_LABELS = {"image": "图片", "video": "视频", "audio": "音频"}
_MAX_REPORT_MEDIA = 6


# ═══════════════════════════════════════════════════════════════════════
# Node implementations
# ═══════════════════════════════════════════════════════════════════════

def _budget_guard(state: OverallState, config: RunnableConfig) -> dict:
    started_at = state.get("run_started_at") or time.time()
    reason = budget_stop_reason(
        {**state, "run_started_at": started_at},
        config,
    )
    updates: dict[str, Any] = {"run_started_at": started_at}
    if reason:
        updates["budget_stop_reason"] = reason
    return updates


def _route_after_budget_guard(state: OverallState) -> str:
    if is_global_budget_stop(state):
        return _FALLBACK_REPORT
    return _OUTLINE


def _fallback_report(state: OverallState) -> dict:
    """Render existing evidence without another paid LLM call."""
    draft = state.get("report_draft", "").strip()
    if draft:
        report = draft
    else:
        summaries = [
            str(item).strip()
            for item in state.get("web_search_result", [])
            if str(item).strip()
        ]
        evidence = "\n\n---\n\n".join(summaries) or "当前预算内未获得可用证据。"
        report = (
            "# 研究报告（预算受限）\n\n"
            "> 研究预算已耗尽，以下内容仅整理已收集证据，未执行额外生成或验证。\n\n"
            "## 已收集证据\n\n"
            f"{evidence}"
        )
    report, _ = _finalize_report(
        report,
        state.get("sources_gathered", []),
    )
    return {"messages": [AIMessage(content=report)]}


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
        "max_revisions": configurable.max_writer_revisions,
        **usage_updates(
            state,
            config,
            agent,
            started_at=state.get("run_started_at") or time.time(),
        ),
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
        source_manifest=_source_manifest(state.get("sources_gathered", [])),
        revision_context=revision_context,
        previous_draft=previous_draft,
    )
    token_delta = agent_total_tokens(agent)
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
            source_manifest=_source_manifest(state.get("sources_gathered", [])),
            revision_context=recovery_context,
            previous_draft=draft,
        )
        token_delta += agent_total_tokens(agent)
        retry_draft = Post.extract_pattern(retry_raw, pattern="markdown")
        retry_reason = _draft_rejection_reason(outline_text, retry_draft)
        if retry_reason is None or len(retry_draft) > len(draft):
            draft = retry_draft
        if retry_reason:
            logger.warning(f"[WriterAgent] recovered draft still incomplete: {retry_reason}")
    logger.info(f"[WriterAgent] draft 已生成 ({len(draft)} 字)")
    return {
        **return_update,
        "report_draft": draft,
        **token_usage_updates(
            state,
            config,
            token_delta,
            started_at=state.get("run_started_at") or time.time(),
        ),
    }


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
        source_manifest=_source_manifest(state.get("sources_gathered", [])),
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
        **usage_updates(
            state,
            config,
            agent,
            started_at=state.get("run_started_at") or time.time(),
        ),
    }


def _route_after_critic(state: OverallState, config: RunnableConfig) -> str:
    """决定：继续修改或进入终审润色。

    进入润色的条件：
      - Critic 明确标记 ready_for_polish，或
      - revision_count >= max_revisions（安全兜底）

    否则回到 draft 继续修改。
    """
    if is_global_budget_stop(state):
        return _FALLBACK_REPORT

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


def _safe_http_url(value: object) -> str:
    url = str(value or "").strip()
    if not url or len(url) > 2048 or any(char.isspace() for char in url):
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    if parts.username or parts.password:
        return ""
    return url


def _media_assets(source: dict) -> list[tuple[str, str]]:
    media = source.get("media")
    if not isinstance(media, list):
        return []

    assets: list[tuple[str, str]] = []
    for item in media[:12]:
        if not isinstance(item, dict):
            continue
        url = _safe_http_url(item.get("url"))
        kind = str(item.get("kind") or "").casefold()
        if not url or kind not in _MEDIA_KIND_LABELS:
            continue
        assets.append((url, kind))
        if len(assets) >= 3:
            break
    return assets


def _markdown_label(value: object) -> str:
    cleaned = re.sub(r"[\[\]\r\n]+", " ", str(value or "媒体证据"))
    return re.sub(r"\s+", " ", cleaned).strip()[:120]


def _append_media_evidence(report: str, sources: list[dict]) -> str:
    """Append a deterministic gallery containing only provider-returned media."""
    blocks: list[str] = []
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_url = _safe_http_url(source.get("value"))
        label = _markdown_label(source.get("label")) or "媒体证据"
        for media_url, kind in _media_assets(source):
            if media_url in seen or media_url in report:
                continue
            seen.add(media_url)
            kind_label = _MEDIA_KIND_LABELS[kind]
            source_link = (
                f" · [查看原始来源](<{source_url}>)" if source_url else ""
            )
            if kind == "image":
                blocks.append(
                    f"### {label}\n\n"
                    f"![{label}](<{media_url}>)\n\n"
                    f"{kind_label}证据{source_link}"
                )
            else:
                blocks.append(
                    f"- [{kind_label}：{label}](<{media_url}>){source_link}"
                )
            if len(blocks) >= _MAX_REPORT_MEDIA:
                break
        if len(blocks) >= _MAX_REPORT_MEDIA:
            break

    if not blocks:
        return report
    return (
        report.rstrip()
        + "\n\n## 多媒体证据\n\n"
        + "\n\n".join(blocks)
        + "\n"
    )


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


def _replace_markdown_target(
    markdown: str,
    *,
    target: str,
    value: str,
    citation_number: int,
) -> str:
    pattern = re.compile(
        r"\[[^\]\r\n]+\]\(\s*<?" + re.escape(target) + r">?\s*\)"
    )
    return pattern.sub(f"[{citation_number}](<{value}>)", markdown)


def _source_number(source: dict, sources: list[dict]) -> int:
    key = _source_key(source)
    for index, candidate in enumerate(sources):
        if _source_key(candidate) == key:
            return index + 1
    return len(sources) + 1


def _normalize_citations(polished: str, sources: list[dict]) -> tuple[str, list[dict]]:
    """Convert internal citations into numbered, real-URL markdown links."""
    unique_sources: list[dict] = []
    seen: set[str] = set()

    def add_source(source: dict) -> int:
        key = _source_key(source)
        if key not in seen:
            seen.add(key)
            unique_sources.append(source)
        return _source_number(source, sources)

    for source in sources:
        short_url = _safe_http_url(source.get("short_url"))
        value = _safe_http_url(source.get("value"))
        media_urls = [url for url, _ in _media_assets(source)]
        if not value:
            continue
        if (short_url and short_url in polished) or value in polished:
            number = add_source(source)
            if short_url:
                polished = _replace_markdown_target(
                    polished,
                    target=short_url,
                    value=value,
                    citation_number=number,
                )
                polished = polished.replace(short_url, value)
            polished = _replace_markdown_target(
                polished,
                target=value,
                value=value,
                citation_number=number,
            )
        elif any(url in polished for url in media_urls):
            add_source(source)

    sources_by_pair: dict[tuple[int, int], dict] = {}
    for source in sources:
        match = _SHORT_URL_PAIR_RE.search(source.get("short_url", ""))
        if match:
            sources_by_pair[(int(match.group(1)), int(match.group(2)))] = source

    def replace_internal_citation(match: re.Match[str]) -> str:
        pair = (int(match.group(1)), int(match.group(2)))
        source = sources_by_pair.get(pair)
        if source is None or not source.get("value"):
            return match.group(0)
        value = source["value"]
        number = add_source(source)
        return f"[{number}](<{value}>)"

    polished = _INTERNAL_CITATION_RE.sub(replace_internal_citation, polished)

    def replace_material(match: re.Match[str]) -> str:
        index = int(match.group(2))
        source = _source_for_material_index(sources, index)
        if source is None or not source.get("value"):
            return match.group(0)
        value = source["value"]
        number = add_source(source)
        return f"[{number}](<{value}>)"

    polished = _MATERIAL_CITATION_RE.sub(replace_material, polished)
    polished = re.sub(
        r"\[([^\]\r\n]+)\]\(<?https?://search\.com/id/[^)>\s]+>?\)",
        r"\1（来源未解析）",
        polished,
    )
    polished = re.sub(
        r"https?://search\.com/id/[^)\]\s]+",
        "来源未解析",
        polished,
    )
    return polished, unique_sources


def _publisher_label(url: str) -> str:
    host = (urlsplit(url).hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]
    if host.endswith("zhihu.com"):
        return "知乎专栏（第三方内容平台）"
    if host.endswith("csdn.net"):
        return "CSDN（第三方内容平台）"
    return host or "未知网站"


def _source_manifest(sources: list[dict]) -> str:
    if not sources:
        return "无可用来源。"

    entries: list[str] = []
    for index, source in enumerate(sources, start=1):
        url = _safe_http_url(source.get("value"))
        if not url:
            continue
        title = _markdown_label(source.get("label")) or _publisher_label(url)
        publisher = _publisher_label(url)
        authority = (
            "第三方内容平台，不得称为官方模型卡、官方公告或官方数据"
            if "第三方内容平台" in publisher
            else "未自动认定为官方；只有材料明确证明发布主体时才能称为官方来源"
        )
        short_url = _safe_http_url(source.get("short_url")) or "无"
        entries.append(
            f"- 材料 {index}: 标题={title}; 网站={publisher}; "
            f"引用地址={short_url}; 真实地址={url}; 权威性={authority}"
        )
    return "\n".join(entries) or "无可用来源。"


def _append_source_index(
    report: str,
    used_sources: list[dict],
    all_sources: list[dict],
) -> str:
    if not used_sources or "## 来源索引（系统核验）" in report:
        return report

    lines = [
        "## 来源索引（系统核验）",
        "",
        "> 以下索引按实际链接列出。检索到某个页面不代表该页面属于官方来源。",
        "",
    ]
    for source in used_sources:
        url = _safe_http_url(source.get("value"))
        if not url:
            continue
        number = _source_number(source, all_sources)
        title = _markdown_label(source.get("label")) or _publisher_label(url)
        publisher = _publisher_label(url)
        lines.append(
            f"- **[{number}]** [{title}](<{url}>) — 网站：{publisher}"
        )
    return report.rstrip() + "\n\n" + "\n".join(lines).rstrip() + "\n"


def _finalize_report(report: str, sources: list[dict]) -> tuple[str, list[dict]]:
    report = _append_media_evidence(report, sources)
    report, unique_sources = _normalize_citations(report, sources)
    report = _append_source_index(report, unique_sources, sources)
    return report, unique_sources


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
        allowed_urls.update(url for url, _ in _media_assets(source))
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
        source_manifest=_source_manifest(state.get("sources_gathered", [])),
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

    polished, unique_sources = _finalize_report(
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
        **usage_updates(
            state,
            config,
            agent,
            started_at=state.get("run_started_at") or time.time(),
        ),
    }


def _route_after_outline(state: OverallState) -> str:
    if is_global_budget_stop(state):
        return _FALLBACK_REPORT
    return _DRAFT


def _route_after_draft(state: OverallState) -> str:
    if is_global_budget_stop(state):
        return _FALLBACK_REPORT
    return _CRITIC_REVIEW


# ═══════════════════════════════════════════════════════════════════════
# 构建子图（带循环）
# ═══════════════════════════════════════════════════════════════════════

_builder = StateGraph(OverallState, context_schema=Configuration)

_builder.add_node(_BUDGET_GUARD, _budget_guard)
_builder.add_node(_OUTLINE, _outline) # 生成大纲
_builder.add_node(_DRAFT, _draft)  # 写草稿 / 修订
_builder.add_node(_CRITIC_REVIEW, _critic_review) # 审稿
_builder.add_node(_CITE_AND_POLISH, _cite_and_polish) # 终稿
_builder.add_node(_FALLBACK_REPORT, _fallback_report)

# Flow: outline → draft → critic → (loop or polish)
_builder.add_edge(START, _BUDGET_GUARD)
_builder.add_conditional_edges(
    _BUDGET_GUARD,
    _route_after_budget_guard,
    [_OUTLINE, _FALLBACK_REPORT],
)
_builder.add_conditional_edges(_OUTLINE, _route_after_outline, [_DRAFT, _FALLBACK_REPORT])
_builder.add_conditional_edges(_DRAFT, _route_after_draft, [_CRITIC_REVIEW, _FALLBACK_REPORT])
_builder.add_conditional_edges(
    _CRITIC_REVIEW,
    _route_after_critic,
    [_DRAFT, _CITE_AND_POLISH, _FALLBACK_REPORT],
)
_builder.add_edge(_CITE_AND_POLISH, END)
_builder.add_edge(_FALLBACK_REPORT, END)

writer_agent_graph = _builder.compile(checkpointer=get_checkpointer(), name="WriterAgent")
