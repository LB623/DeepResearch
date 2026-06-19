"""ResearchAgent 子图。

封装了核心研究循环：

1. generate_queries — 将主题分解为搜索查询

2. web_search（并行扇出）— 搜索并汇总每个查询

3. critique — 评估信息是否充分；如有必要，则循环返回步骤 (1)

当评估认为信息充分或达到 max_research_loops 时，循环终止。
"""

from __future__ import annotations

import json
import os
import re
import time

from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from loguru import logger

from agent.base_agent import Agent, JsonAgent, WebSearchAgent
from agent.checkpoint import get_checkpointer
from agent.configuration import Configuration
from agent.kb import FactExtractor, FactStore
from agent.kb.lifecycle import (
    FRESHNESS_MAX_AGE,
    KBLifecycleMode,
    get_mode,
    should_decay,
    should_filter,
    should_tag,
    should_warn,
)
from agent.post import Post
from agent.prompts import (
    get_current_date,
    query_writer_instructions,
    reflection_instructions,
    web_searcher_instructions,
)
from agent.state import OverallState, QueryGenerationState, WebSearchState
from agent.tools_and_schemas import Reflection, SearchQueryList
from agent.utils import get_research_topic, resolve_urls

# 注意：agent.exceptions（KBConnectionError、KBConfigError 等）将在 teach-06-exception 中引入。
# 目前，使用的是标准异常。

load_dotenv()

# ── KB 单例（延迟初始化，在代理运行之间共享） ──────────────
_kb_store: FactStore | None = None
_kb_extractor: FactExtractor | None = None


def _get_kb_store() -> FactStore | None:
    global _kb_store
    if _kb_store is None:
        try:
            _kb_store = FactStore()
            logger.info("[KB] FactStor 连接到 Milvus")
        except Exception as exc:
            logger.warning(f"[KB] FactStore 初始化失败（Milvus 可能已关闭）: {exc}")
            _kb_store = False  # type: ignore — sentinel
    return _kb_store if _kb_store is not False else None  # type: ignore[return-value]


def _get_kb_extractor() -> FactExtractor:
    global _kb_extractor
    if _kb_extractor is None:
        _kb_extractor = FactExtractor()
    return _kb_extractor

_GENERATE_QUERIES = "generate_queries"
_WEB_SEARCH = "web_search"
_CRITIQUE = "critique"


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
    queries: list[object],
    executed_queries: list[object] | None = None,
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
    logger.info(
        f"[ResearchAgent] 生成 {len(result.query)} 个查询，"
        f"保留 {len(queries)} 个，跳过重复 {len(skipped)} 个: {queries}"
    )
    return {
        "search_query": queries,
        "generated_queries": queries,
        "skipped_duplicate_queries": skipped,
        "initial_search_query_count": state["initial_search_query_count"],
    }


def _fan_out_to_web_search(state: QueryGenerationState) -> list[Send]:
    """Fan-out: 每个查询调用一次 web_search。"""
    queries = state.get("generated_queries") or state.get("search_query", [])
    queries, skipped = _dedupe_queries(queries, state.get("executed_queries", []))
    if skipped:
        logger.info(f"[ResearchAgent] fan-out 跳过 {len(skipped)} 个重复查询: {skipped}")
    return [
        Send(_WEB_SEARCH, {"search_query": q, "id": int(idx)})
        for idx, q in enumerate(queries)
    ]


def _web_search(state: WebSearchState, config: RunnableConfig) -> dict:
    """搜索单个查询并汇总结果。"""
    configurable = Configuration.from_runnable_config(config)
    searcher = WebSearchAgent()
    response = searcher.step(prompt=state["search_query"], count=10)

    if not response:
        logger.error(f"[ResearchAgent] 搜索结果为空： '{state['search_query']}'")
        result = {
            "sources_gathered": [],
            "executed_queries": [state["search_query"]],
            "web_search_result": [f"未找到关于 '{state['search_query']}' 的搜索结果"],
        }
        if not _query_dedupe_enabled():
            result["search_query"] = [state["search_query"]]
        return result

    # URL shortening
    long2short = resolve_urls(response, state["id"])
    sources = [
        {"short_url": long2short[item["url"]], "value": item["url"], "label": item["title"]}
        for item in response
    ]
    raw_results = json.dumps(
        [{"snippet": i["snippet"], "title": i["title"], "url": long2short[i["url"]]}
         for i in response],
        ensure_ascii=False, indent=4,
    )
    logger.info(f"[ResearchAgent] _web_search 使用模型: {configurable.query_generator_model}")
    agent = Agent(model_id=configurable.query_generator_model)
    agent.set_step_prompt(web_searcher_instructions)
    summary = agent.step(
        query=state["search_query"],
        current_date=get_current_date(),
        web_search_result=raw_results,
    )
    summary = Post.extract_pattern(summary, pattern="text")
    logger.info(f"[ResearchAgent] 已搜索： '{state['search_query']}'")

    # ── KB/知识库 存储 ────────────────────────────────────────────────
    try:
        store = _get_kb_store()
        if store:
            extractor = _get_kb_extractor()
            topic = get_research_topic(state.get("messages", []))
            facts = extractor.extract(summary, research_topic=topic)
            if facts:
                # 将短链接还原为真实 URL，避免 KB 中存储不可解析的过期引用
                short2long = {v: k for k, v in long2short.items()}
                for f in facts:
                    f["source_url"] = short2long.get(f["source_url"], f["source_url"])
                    f["research_topic"] = topic
                store.add_facts(facts)
    except Exception as exc:
        logger.warning(f"[KB] 跳过存储: {exc}")

    result = {
        "sources_gathered": sources,
        "executed_queries": [state["search_query"]],
        "web_search_result": [summary],
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
    # 防护：LLM 调用全部失败时，step() 返回空字符串
    if not isinstance(result, Reflection):
        logger.warning(
            f"[ResearchAgent] 评估模型调用失败（返回类型={type(result).__name__}），"
            f"视为信息不足，继续搜索"
        )
        return {
            "is_sufficient": False,
            "knowledge_gap": "评估模型暂时不可用，需要继续搜索以补充信息",
            "follow_up_queries": [],
            "research_loop_count": state["research_loop_count"],
            "number_of_ran_queries": len(state.get("executed_queries", state.get("search_query", []))),
            "max_research_loops": state.get("max_research_loops", configurable.max_research_loops),
        }

    logger.info(
        f"[ResearchAgent] 评估是否充足结果：{result.is_sufficient}, "
        f"gap='{result.knowledge_gap[:80]}...'"
    )
    return {
        "is_sufficient": result.is_sufficient,
        "knowledge_gap": result.knowledge_gap,
        "follow_up_queries": result.follow_up_queries,
        "research_loop_count": state["research_loop_count"],
        "number_of_ran_queries": len(state.get("executed_queries", state.get("search_query", []))),
        "max_research_loops": state.get("max_research_loops", configurable.max_research_loops),
    }


def _route_after_critique(state: OverallState, config: RunnableConfig):
    """决定返回进行更多搜索，还是退出子图。"""
    configurable = Configuration.from_runnable_config(config)
    max_loops = state.get("max_research_loops") or configurable.max_research_loops

    if state["is_sufficient"] or state["research_loop_count"] >= max_loops:
        logger.info(f"[ResearchAgent] 退出循环，已执行 {state['research_loop_count']} 次")
        return END  # ← exits sub-graph, parent takes over
    else:
        logger.info(f"[ResearchAgent] 继续循环 ({state['research_loop_count']}/{max_loops})")
        queries, skipped = _dedupe_queries(
            state.get("follow_up_queries", []),
            state.get("executed_queries", []),
        )
        if skipped:
            logger.info(f"[ResearchAgent] 跳过 {len(skipped)} 个已执行 follow-up 查询: {skipped}")
        return [
            Send(_WEB_SEARCH,
                 {"search_query": q, "id": state["number_of_ran_queries"] + int(idx)})
            for idx, q in enumerate(queries)
        ]


_builder = StateGraph(OverallState, config_schema=Configuration)

_builder.add_node(_GENERATE_QUERIES, _generate_queries)
_builder.add_node(_WEB_SEARCH, _web_search)
_builder.add_node(_CRITIQUE, _critique)

_builder.add_edge(START, _GENERATE_QUERIES)
_builder.add_conditional_edges(_GENERATE_QUERIES, _fan_out_to_web_search, [_WEB_SEARCH])
_builder.add_edge(_WEB_SEARCH, _CRITIQUE)
_builder.add_conditional_edges(_CRITIQUE, _route_after_critique, [_WEB_SEARCH, END])

research_agent_graph = _builder.compile(checkpointer=get_checkpointer(), name="ResearchAgent")
