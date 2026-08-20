"""ResearchAgent 子图。

封装了核心研究循环：

1. generate_queries — 将主题分解为搜索查询

2. web_search（并行扇出）— 搜索并汇总每个查询

3. critique — 评估信息是否充分；如有必要，则循环返回步骤 (1)

当评估认为信息充分或达到 max_research_loops 时，循环终止。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from collections.abc import Sequence
from typing import Any, cast

from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from loguru import logger

from agent.base_agent import Agent, JsonAgent, WebSearchAgent
from agent.checkpoint import get_checkpointer
from agent.configuration import Configuration
from agent.kb import FactExtractor, FactStore, FactStoreProvider
from agent.kb.lifecycle import (
    FRESHNESS_MAX_AGE,
    KBLifecycleMode,
    get_mode,
    should_decay,
    should_filter,
    should_tag,
    should_warn,
)
from agent.logger import content_metadata
from agent.post import Post
from agent.prompts import (
    get_current_date,
    query_writer_instructions,
    reflection_instructions,
    web_searcher_instructions,
)
from agent.retrieval import (
    DashScopeSearchProvider,
    OmniSeekSearchProvider,
    SearchCoordinator,
)
from agent.state import OverallState, QueryGenerationState, WebSearchState
from agent.tools_and_schemas import Reflection, SearchQueryList
from agent.utils import get_research_topic, resolve_urls

# 注意：agent.exceptions（KBConnectionError、KBConfigError 等）将在 teach-06-exception 中引入。
# 目前，使用的是标准异常。

load_dotenv()

# ── KB 单例（延迟初始化，在代理运行之间共享） ──────────────
_kb_store_provider = FactStoreProvider()
_kb_extractor: FactExtractor | None = None


def _get_kb_store() -> FactStore | None:
    return _kb_store_provider.get()


def _get_kb_extractor() -> FactExtractor:
    global _kb_extractor
    if _kb_extractor is None:
        _kb_extractor = FactExtractor()
    return _kb_extractor

_GENERATE_QUERIES = "generate_queries"
_WEB_SEARCH = "web_search"
_CRITIQUE = "critique"
_BUDGET_GUARD = "budget_guard"

SEARCH_CALL_LIMIT = "search_call_limit"
ELAPSED_TIME_LIMIT = "elapsed_time_limit"
NO_PROGRESS = "no_progress"
TOKEN_LIMIT = "token_limit"


def _agent_total_tokens(agent: Agent) -> int:
    usage = getattr(getattr(agent, "llm", None), "last_usage", {})
    total = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0
    return int(total) if isinstance(total, (int, float)) else 0


def _budget_stop_reason(
    state: OverallState,
    configurable: Configuration,
) -> str:
    started_at = state.get("run_started_at") or time.time()
    if time.time() - started_at >= configurable.max_elapsed_seconds:
        return ELAPSED_TIME_LIMIT
    if state.get("no_progress_rounds", 0) >= configurable.max_no_progress_rounds:
        return NO_PROGRESS
    if state.get("llm_token_count", 0) >= configurable.max_total_tokens:
        return TOKEN_LIMIT
    if state.get("web_search_call_count", 0) >= configurable.max_web_search_calls:
        return SEARCH_CALL_LIMIT
    return ""


def _budget_guard(state: OverallState, config: RunnableConfig) -> dict:
    """Stop before external work when the persisted search budget is exhausted."""
    configurable = Configuration.from_runnable_config(config)
    started_at = state.get("run_started_at") or time.time()
    reason = _budget_stop_reason(state, configurable)
    if reason:
        return {
            "run_started_at": started_at,
            "budget_stop_reason": reason,
        }
    return {"run_started_at": started_at}


def _route_after_budget_guard(state: OverallState):
    if state.get("budget_stop_reason"):
        return END
    return _GENERATE_QUERIES


def _query_dedupe_enabled() -> bool:
    """Return whether query dedupe is enabled for benchmark A/B runs."""
    return os.getenv("QUERY_DEDUPE_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


def _normalize_query(query: object) -> str:
    """Normalize a search query for stable duplicate detection."""
    if isinstance(query, dict):
        query = query.get("query", "")
    text = str(query or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _dedupe_queries(
    queries: Sequence[object],
    executed_queries: Sequence[object] | None = None,
) -> tuple[list[str], list[str]]:
    """Deduplicate queries while preserving order.

    Returns (kept_queries, skipped_queries). ``executed_queries`` is used to
    avoid re-running follow-up queries that were already searched in prior
    loops.
    """
    if not _query_dedupe_enabled():
        return [str(q) for q in queries if str(q).strip()], []

    seen = {
        _normalize_query(q)
        for q in (executed_queries or [])
        if _normalize_query(q)
    }
    kept: list[str] = []
    skipped: list[str] = []

    for query in queries:
        text = str(query or "").strip()
        norm = _normalize_query(text)
        if not norm:
            continue
        if norm in seen:
            skipped.append(text)
            continue
        seen.add(norm)
        kept.append(text)

    return kept, skipped


def _omniseek_is_configured(configurable: Configuration) -> bool:
    """Keep service credentials outside runnable config and checkpoint state."""
    return (
        configurable.omniseek_mode != "off"
        and bool(os.getenv("OMNISEEK_MCP_URL", "").strip())
        and bool(os.getenv("OMNISEEK_TOKEN", "").strip())
    )


def _build_search_coordinator(
    configurable: Configuration,
    *,
    use_omniseek: bool,
) -> SearchCoordinator:
    dashscope = DashScopeSearchProvider(agent_factory=WebSearchAgent)
    if not use_omniseek or not _omniseek_is_configured(configurable):
        return SearchCoordinator([dashscope])

    try:
        omniseek = OmniSeekSearchProvider(
            endpoint=os.environ["OMNISEEK_MCP_URL"],
            token=os.environ["OMNISEEK_TOKEN"],
            wait_seconds=configurable.omniseek_wait_seconds,
            request_timeout_seconds=configurable.omniseek_request_timeout_seconds,
            sources=configurable.omniseek_sources.split(","),
            max_results=configurable.omniseek_result_limit,
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "[Retrieval] OmniSeek configuration rejected error_type={}",
            type(exc).__name__,
        )
        return SearchCoordinator([dashscope])

    if configurable.omniseek_mode == "only":
        return SearchCoordinator([omniseek])
    if configurable.omniseek_mode == "fallback":
        return SearchCoordinator([dashscope], fallback_providers=[omniseek])
    return SearchCoordinator([dashscope, omniseek])


def _search_sends(
    queries: Sequence[str],
    *,
    start_id: int,
    state: QueryGenerationState | OverallState,
    configurable: Configuration,
) -> list[Send]:
    remaining_omniseek = max(
        0,
        configurable.max_omniseek_calls - state.get("omniseek_call_count", 0),
    )
    omniseek_available = _omniseek_is_configured(configurable)
    return [
        Send(
            _WEB_SEARCH,
            {
                "search_query": query,
                "id": start_id + idx,
                # Reserve the persisted per-task budget before concurrent fan-out.
                "use_omniseek": omniseek_available and idx < remaining_omniseek,
            },
        )
        for idx, query in enumerate(queries)
    ]


def _generate_queries(state: OverallState, config: RunnableConfig) -> dict:
    """将研究主题分解为独立的搜索查询。

    在生成查询前，先从知识库中检索与主题相关的已知事实，
    避免重复搜索已有信息。
    """
    configurable = Configuration.from_runnable_config(config)
    if state.get("initial_search_query_count") is None:
        state["initial_search_query_count"] = configurable.number_of_initial_queries

    # ── KB/知识库检索 ──────────────────────────────────────────────
    known_facts_text = ""
    try:
        store = _get_kb_store()
        if store:
            mode = get_mode()
            topic = get_research_topic(state["messages"])
            freshness = state.get("fresh_level", "medium")
            max_age = FRESHNESS_MAX_AGE.get(freshness, 30) if should_filter(mode) else None
            decay = should_decay(mode)
            use_lifecycle = mode == KBLifecycleMode.LIFECYCLE

            hits = store.query(
                topic, top_k=20, min_confidence=0.6,
                max_age_days=max_age,
                decay=decay,
                lifecycle_mode=use_lifecycle,
            )
            if hits:
                facts_lines = []
                for h in hits:
                    line = f"- [{h['confidence']:.0%}] {h['fact']}"
                    if should_tag(mode):
                        age_days = h.get("age_days", (time.time() - h["created_at"]) / 86400)
                        age_tag = (
                            "🕐 刚刚" if age_days < 1 else
                            f"{age_days:.0f}天前" if age_days < 30 else
                            f"{age_days / 30:.0f}个月前"
                        )
                        line += f" ({age_tag}, 来源: {h['source_url'][:60]})"
                    else:
                        line += f" (来源: {h['source_url'][:60]})"
                    facts_lines.append(line)

                if should_warn(mode):
                    header = "\n## 📚 知识库中已有的相关事实\n"
                    footer = "\n\n⚠️ 标记较早的事实可能已过时，请优先搜索获取最新信息。"
                else:
                    header = "\n## 知识库中已有的相关事实（请勿重复搜索这些内容）\n"
                    footer = ""
                known_facts_text = header + "\n".join(facts_lines) + footer
                logger.info(f"[KB] 检索到 {len(hits)} 个facts 用作查询生成上下文")
    except Exception as exc:
        logger.warning(f"[KB] retrieval skipped: {exc}")
    logger.info(f"[ResearchAgent] _generate_queries使用模型: {configurable.query_generator_model}")
    agent = JsonAgent(model_id=configurable.query_generator_model, keys=SearchQueryList)
    agent.set_step_prompt(query_writer_instructions)
    result = agent.step(
        current_date=get_current_date(),
        research_topic=get_research_topic(state["messages"]),
        number_queries=state["initial_search_query_count"],
        research_proposal=state.get("plan", ""),
        known_facts=known_facts_text,
    )
    queries, skipped = _dedupe_queries(
        result.query,
        state.get("executed_queries", []),
    )
    requested_count = max(
        0,
        int(
            state.get(
                "initial_search_query_count",
                configurable.number_of_initial_queries,
            )
        ),
    )
    queries = queries[:requested_count]
    logger.info(
        f"[ResearchAgent] 生成 {len(result.query)} 个查询，"
        f"保留 {len(queries)} 个，跳过重复 {len(skipped)} 个"
    )
    llm_token_delta = _agent_total_tokens(agent)
    updates = {
        "search_query": queries,
        "generated_queries": queries,
        "skipped_duplicate_queries": skipped,
        "initial_search_query_count": state["initial_search_query_count"],
        "llm_token_count": llm_token_delta,
    }
    reason = _budget_stop_reason(
        {
            **state,
            "llm_token_count": state.get("llm_token_count", 0) + llm_token_delta,
        },
        configurable,
    )
    if reason:
        updates["budget_stop_reason"] = reason
    return updates


def _fan_out_to_web_search(
    state: QueryGenerationState,
    config: RunnableConfig,
) -> list[Send] | str:
    """Fan-out: 每个查询调用一次 web_search。"""
    configurable = Configuration.from_runnable_config(config)
    if state.get("budget_stop_reason") or _budget_stop_reason(
        cast(OverallState, state),
        configurable,
    ):
        return END
    queries = state.get("generated_queries") or state.get("search_query", [])
    queries, skipped = _dedupe_queries(queries, state.get("executed_queries", []))
    remaining = max(
        0,
        configurable.max_web_search_calls
        - state.get("web_search_call_count", 0),
    )
    queries = queries[:remaining]
    if skipped:
        logger.info(f"[ResearchAgent] fan-out 跳过 {len(skipped)} 个重复查询")
    if not queries:
        return END
    return _search_sends(
        queries,
        start_id=0,
        state=state,
        configurable=configurable,
    )


def _store_summary_facts(
    summary: str,
    *,
    topic: str,
    long2short: dict[str, str],
) -> int:
    """Persist extracted facts off the event loop; KB failures remain optional."""
    try:
        store = _get_kb_store()
        if not store:
            return 0
        extractor = _get_kb_extractor()
        facts = extractor.extract(summary, research_topic=topic)
        extractor_tokens = max(
            0,
            int(getattr(extractor, "last_token_count", 0) or 0),
        )
        if facts:
            # Restore real URLs so stored evidence never depends on ephemeral aliases.
            short2long = {short: long for long, short in long2short.items()}
            for fact in facts:
                fact["source_url"] = short2long.get(
                    fact["source_url"],
                    fact["source_url"],
                )
                fact["research_topic"] = topic
            store.add_facts(facts)
        return extractor_tokens
    except Exception as exc:
        logger.warning(
            "[KB] skip storage error_type={}",
            type(exc).__name__,
        )
        return 0


async def _web_search(state: WebSearchState, config: RunnableConfig) -> dict:
    """搜索单个查询并汇总结果。"""
    configurable = Configuration.from_runnable_config(config)
    coordinator = _build_search_coordinator(
        configurable,
        use_omniseek=state.get("use_omniseek", False),
    )
    batch = await coordinator.search(state["search_query"], 10)
    response = [hit.as_page() for hit in batch.hits]
    omniseek_call_count = int("omniseek" in batch.providers_attempted)
    omniseek_failure_count = sum(
        failure.provider == "omniseek" for failure in batch.failures
    )
    result: dict[str, Any]

    if not response:
        logger.error(
            "[ResearchAgent] 搜索结果为空: {}",
            content_metadata(state["search_query"], label="query"),
        )
        result = {
            "sources_gathered": [],
            "executed_queries": [state["search_query"]],
            "web_search_result": [f"未找到关于 '{state['search_query']}' 的搜索结果"],
            "web_search_call_count": 1,
            "omniseek_call_count": omniseek_call_count,
            "omniseek_failure_count": omniseek_failure_count,
        }
        if not _query_dedupe_enabled():
            result["search_query"] = [state["search_query"]]
        return result

    # URL shortening
    long2short = resolve_urls(response, state["id"])
    sources = []
    for hit in batch.hits:
        source = {
            "short_url": long2short[hit.url],
            "value": hit.url,
            "label": hit.title,
            "provider": hit.provider,
        }
        if hit.source:
            source["source"] = hit.source
        sources.append(source)
    raw_results = json.dumps(
        [{"snippet": i["snippet"], "title": i["title"], "url": long2short[i["url"]]}
         for i in response],
        ensure_ascii=False, indent=4,
    )
    logger.info(f"[ResearchAgent] _web_search 使用模型: {configurable.query_generator_model}")
    agent = Agent(model_id=configurable.query_generator_model)
    agent.set_step_prompt(web_searcher_instructions)
    summary = await asyncio.to_thread(
        agent.step,
        query=state["search_query"],
        current_date=get_current_date(),
        web_search_result=raw_results,
    )
    summary = Post.extract_pattern(summary, pattern="text")
    logger.info(
        "[ResearchAgent] 搜索完成: {}",
        content_metadata(state["search_query"], label="query"),
    )

    extractor_tokens = await asyncio.to_thread(
        _store_summary_facts,
        summary,
        topic=state["search_query"],
        long2short=long2short,
    )

    result = {
        "sources_gathered": sources,
        "executed_queries": [state["search_query"]],
        "web_search_result": [summary],
        "web_search_call_count": 1,
        "omniseek_call_count": omniseek_call_count,
        "omniseek_failure_count": omniseek_failure_count,
        "llm_token_count": _agent_total_tokens(agent) + extractor_tokens,
    }
    if not _query_dedupe_enabled():
        result["search_query"] = [state["search_query"]]
    return result


def _critique(state: OverallState, config: RunnableConfig) -> dict:
    """评估收集到的信息是否充足。"""
    configurable = Configuration.from_runnable_config(config)
    state["research_loop_count"] = state.get("research_loop_count", 0) + 1
    reasoning_model = state.get("reasoning_model") or configurable.reflection_model
    logger.info(f"[ResearchAgent] _critique评估使用模型: {reasoning_model}")

    agent = JsonAgent(model_id=reasoning_model, keys=Reflection)
    agent.set_step_prompt(reflection_instructions)
    result = agent.step(
        current_date=get_current_date(),
        number_queries=state["initial_search_query_count"],
        research_topic=get_research_topic(state["messages"]),
        summaries="\n\n---\n\n".join(state["web_search_result"]),
        research_proposal=state.get("plan", ""),
    )
    llm_token_delta = _agent_total_tokens(agent)
    # 防护：LLM 调用全部失败时，step() 返回空字符串
    if not isinstance(result, Reflection):
        logger.warning(
            f"[ResearchAgent] 评估模型调用失败（返回类型={type(result).__name__}），"
            f"视为信息不足，继续搜索"
        )
        updates: dict[str, Any] = {
            "is_sufficient": False,
            "knowledge_gap": "评估模型暂时不可用，需要继续搜索以补充信息",
            "follow_up_queries": [],
            "research_loop_count": state["research_loop_count"],
            "number_of_ran_queries": len(state.get("executed_queries", state.get("search_query", []))),
            "max_research_loops": state.get("max_research_loops", configurable.max_research_loops),
            "llm_token_count": llm_token_delta,
        }
        reason = _budget_stop_reason(
            {
                **state,
                "llm_token_count": state.get("llm_token_count", 0) + llm_token_delta,
            },
            configurable,
        )
        if reason:
            updates["budget_stop_reason"] = reason
        return updates

    logger.info(
        f"[ResearchAgent] 评估是否充足结果：{result.is_sufficient}, "
        f"{content_metadata(result.knowledge_gap, label='gap')}"
    )
    evidence_payload = {
        "sources": state.get("sources_gathered", []),
        "summaries": [
            summary
            for summary in state.get("web_search_result", [])
            if not str(summary).startswith("未找到关于 '")
        ],
    }
    evidence_fingerprint = hashlib.sha256(
        json.dumps(
            evidence_payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode(),
    ).hexdigest()
    previous_fingerprint = state.get("evidence_fingerprint", "")
    no_progress_rounds = (
        state.get("no_progress_rounds", 0) + 1
        if previous_fingerprint == evidence_fingerprint
        else 0
    )
    updates = {
        "is_sufficient": result.is_sufficient,
        "knowledge_gap": result.knowledge_gap,
        "follow_up_queries": result.follow_up_queries,
        "research_loop_count": state["research_loop_count"],
        "number_of_ran_queries": len(state.get("executed_queries", state.get("search_query", []))),
        "max_research_loops": state.get("max_research_loops", configurable.max_research_loops),
        "no_progress_rounds": no_progress_rounds,
        "evidence_fingerprint": evidence_fingerprint,
        "llm_token_count": llm_token_delta,
    }
    candidate_state = cast(
        OverallState,
        {
            **dict(state),
            **updates,
            "llm_token_count": state.get("llm_token_count", 0) + llm_token_delta,
        },
    )
    reason = _budget_stop_reason(candidate_state, configurable)
    if reason:
        updates["budget_stop_reason"] = reason
    return updates


def _route_after_critique(state: OverallState, config: RunnableConfig):
    """决定返回进行更多搜索，还是退出子图。"""
    configurable = Configuration.from_runnable_config(config)
    max_loops = state.get("max_research_loops") or configurable.max_research_loops

    if (
        state["is_sufficient"]
        or state["research_loop_count"] >= max_loops
        or state.get("budget_stop_reason")
    ):
        logger.info(f"[ResearchAgent] 退出循环，已执行 {state['research_loop_count']} 次")
        return END  # ← exits sub-graph, parent takes over
    else:
        logger.info(f"[ResearchAgent] 继续循环 ({state['research_loop_count']}/{max_loops})")
        queries, skipped = _dedupe_queries(
            state.get("follow_up_queries", []),
            state.get("executed_queries", []),
        )
        remaining = max(
            0,
            configurable.max_web_search_calls
            - state.get("web_search_call_count", 0),
        )
        queries = queries[:remaining]
        if skipped:
            logger.info(f"[ResearchAgent] 跳过 {len(skipped)} 个已执行 follow-up 查询: {skipped}")
        if not queries:
            return END
        return _search_sends(
            queries,
            start_id=state["number_of_ran_queries"],
            state=state,
            configurable=configurable,
        )


_builder = StateGraph(OverallState, context_schema=Configuration)

_builder.add_node(_BUDGET_GUARD, _budget_guard)
_builder.add_node(_GENERATE_QUERIES, _generate_queries)
_builder.add_node(_WEB_SEARCH, _web_search)
_builder.add_node(_CRITIQUE, _critique)

_builder.add_edge(START, _BUDGET_GUARD)
_builder.add_conditional_edges(
    _BUDGET_GUARD,
    _route_after_budget_guard,
    [_GENERATE_QUERIES, END],
)
_builder.add_conditional_edges(
    _GENERATE_QUERIES,
    _fan_out_to_web_search,
    [_WEB_SEARCH, END],
)
_builder.add_edge(_WEB_SEARCH, _CRITIQUE)
_builder.add_conditional_edges(_CRITIQUE, _route_after_critique, [_WEB_SEARCH, END])

research_agent_graph = _builder.compile(checkpointer=get_checkpointer(), name="ResearchAgent")
