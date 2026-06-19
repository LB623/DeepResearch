#!/usr/bin/env python
"""Run an A/B benchmark for DeepResearch Agent harness changes.

The benchmark compares two variants on the same topic set:

- baseline: ``QUERY_DEDUPE_ENABLED=0`` to reproduce the old state behavior.
- optimized: ``QUERY_DEDUPE_ENABLED=1`` to enable query normalization/dedupe.

It records deterministic harness metrics directly from graph state and captured
web-search calls. Citation validity can optionally be judged with LLM-as-Judge.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from loguru import logger

from agent.graph import graph
from agent.llm.llm import get_usage_totals, reset_usage_totals
from agent.search_cache import clear_cache
from agent.sub_agents.research_agent import research_agent_graph
from eval.judge import Judge

load_dotenv()

DEFAULT_SET = Path(__file__).with_name("benchmark_set.json")
DEFAULT_DOC = Path(__file__).parents[2] / "docs" / "reviews" / "2026-06-16-agent-harness-benchmark.md"


@dataclass
class BenchmarkTopic:
    topic: str
    domain: str = ""
    initial_search_query_count: int = 3
    max_research_loops: int = 3


@dataclass
class TopicMetrics:
    topic: str
    domain: str
    variant: str
    success: bool
    error: str | None = None
    latency_seconds: float = 0.0
    report_chars: int = 0
    research_loops: int = 0
    state_query_count: int = 0
    state_unique_query_count: int = 0
    state_duplicate_query_rate: float = 0.0
    generated_query_count: int = 0
    executed_query_count: int = 0
    executed_unique_query_count: int = 0
    executed_duplicate_query_rate: float = 0.0
    skipped_duplicate_query_count: int = 0
    source_count: int = 0
    kb_row_count_before: int | None = None
    kb_row_count_after: int | None = None
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_chars: int = 0
    citation_total: int | None = None
    citation_valid: int | None = None
    citation_valid_rate: float | None = None


@dataclass
class VariantSummary:
    variant: str
    task_count: int
    success_rate: float
    avg_latency_seconds: float
    avg_research_loops: float
    avg_state_query_count: float
    avg_state_duplicate_query_rate: float
    avg_executed_query_count: float
    avg_executed_duplicate_query_rate: float
    avg_skipped_duplicate_query_count: float
    avg_llm_calls: float
    avg_total_tokens: float | None
    avg_prompt_chars: float
    citation_valid_rate: float | None = None


class SearchCapture:
    """Capture raw web-search calls made by ``WebSearchAgent.step``."""

    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def __enter__(self):
        import agent.base_agent as mod

        self._mod = mod
        self._orig_step = mod.WebSearchAgent.step

        def _patched_step(agent_self, prompt, **kwargs):
            result = self._orig_step(agent_self, prompt, **kwargs)
            self.calls.append({
                "query": str(prompt),
                "result_count": len(result or []),
                "cached_or_live": "unknown",
            })
            return result

        mod.WebSearchAgent.step = _patched_step
        return self

    def __exit__(self, exc_type, exc, tb):
        self._mod.WebSearchAgent.step = self._orig_step


def normalize_query(query: object) -> str:
    text = str(query or "").strip().lower()
    return re.sub(r"\s+", " ", text)


def duplicate_rate(items: list[object]) -> tuple[int, int, float]:
    normalized = [normalize_query(item) for item in items if normalize_query(item)]
    total = len(normalized)
    unique = len(set(normalized))
    rate = 0.0 if total == 0 else 1 - unique / total
    return total, unique, rate


def load_topics(path: Path, limit: int | None = None) -> list[BenchmarkTopic]:
    data = json.loads(path.read_text(encoding="utf-8"))
    topics = [
        BenchmarkTopic(
            topic=item["topic"],
            domain=item.get("domain", ""),
            initial_search_query_count=item.get("initial_search_query_count", 3),
            max_research_loops=item.get("max_research_loops", 3),
        )
        for item in data.get("topics", [])
    ]
    return topics[:limit] if limit else topics


def extract_report(state: dict) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return ""


def get_kb_row_count() -> int | None:
    try:
        from agent.kb.fact_store import FactStore

        stats = FactStore().stats()
        row_count = stats.get("row_count")
        return int(row_count) if str(row_count).isdigit() else None
    except Exception as exc:
        logger.warning(f"KB stats unavailable: {type(exc).__name__}: {exc}")
        return None


async def run_topic(
    cfg: BenchmarkTopic,
    variant: str,
    judge: Judge | None = None,
    clear_search_cache: bool = True,
    research_only: bool = False,
    query_model: str | None = None,
    reflection_model: str | None = None,
) -> TopicMetrics:
    os.environ["QUERY_DEDUPE_ENABLED"] = "0" if variant == "baseline" else "1"
    if clear_search_cache:
        clear_cache()

    reset_usage_totals()
    start = time.perf_counter()
    capture = SearchCapture()

    try:
        kb_row_count_before = get_kb_row_count()
        thread_id = f"benchmark-{variant}-{abs(hash(cfg.topic)) & 0xFFFF}-{int(start * 1000)}"
        configurable = {
            "thread_id": thread_id,
            "number_of_initial_queries": cfg.initial_search_query_count,
            "max_research_loops": cfg.max_research_loops,
        }
        if query_model:
            configurable["query_generator_model"] = query_model
        if reflection_model:
            configurable["reflection_model"] = reflection_model

        config = {
            "configurable": {
                **configurable,
            }
        }

        if research_only:
            with capture:
                phase2_state = await research_agent_graph.ainvoke(
                    {
                        "messages": [HumanMessage(content=cfg.topic)],
                        "plan": "",
                        "plan_status": "confirmed",
                        "initial_search_query_count": cfg.initial_search_query_count,
                        "max_research_loops": cfg.max_research_loops,
                        "research_loop_count": 0,
                        "fresh_level": "medium",
                    },
                    config=config,
                )
        else:
            phase1_state = await graph.ainvoke(
                {"messages": [HumanMessage(content=cfg.topic)]},
                config=config,
            )
            plan = phase1_state.get("plan", "")

            with capture:
                phase2_state = await graph.ainvoke(
                    {
                        "messages": [
                            HumanMessage(content=cfg.topic),
                            *(phase1_state.get("plan_messages", [])),
                            HumanMessage(content="需求确认"),
                        ],
                        "plan": plan,
                        "plan_status": "confirmed",
                        "initial_search_query_count": cfg.initial_search_query_count,
                        "max_research_loops": cfg.max_research_loops,
                        "research_loop_count": 0,
                    },
                    config=config,
                )

        latency = time.perf_counter() - start
        usage = get_usage_totals()
        report = extract_report(phase2_state)
        sources = phase2_state.get("sources_gathered", [])
        state_queries = list(phase2_state.get("search_query", []) or [])
        generated_queries = list(phase2_state.get("generated_queries", []) or [])
        executed_queries = list(phase2_state.get("executed_queries", []) or [])
        if not executed_queries:
            executed_queries = [call["query"] for call in capture.calls]
        skipped = list(phase2_state.get("skipped_duplicate_queries", []) or [])

        state_total, state_unique, state_dup = duplicate_rate(state_queries)
        exec_total, exec_unique, exec_dup = duplicate_rate(executed_queries)

        citation_total = None
        citation_valid = None
        citation_valid_rate = None
        if judge and report and sources:
            score = judge.evaluate_citations(
                sources=json.dumps(sources, ensure_ascii=False, indent=2),
                report=report,
            )
            if score:
                citation_total = score.total_citations
                citation_valid = score.valid_citations
                citation_valid_rate = (
                    None
                    if score.total_citations == 0
                    else score.valid_citations / score.total_citations
                )
        kb_row_count_after = get_kb_row_count()

        return TopicMetrics(
            topic=cfg.topic,
            domain=cfg.domain,
            variant=variant,
            success=(
                bool(phase2_state.get("web_search_result"))
                if research_only
                else bool(report and len(report) > 200)
            ),
            latency_seconds=round(latency, 2),
            report_chars=len(report),
            research_loops=int(phase2_state.get("research_loop_count", 0) or 0),
            state_query_count=state_total,
            state_unique_query_count=state_unique,
            state_duplicate_query_rate=round(state_dup, 4),
            generated_query_count=len(generated_queries),
            executed_query_count=exec_total,
            executed_unique_query_count=exec_unique,
            executed_duplicate_query_rate=round(exec_dup, 4),
            skipped_duplicate_query_count=len(skipped),
            source_count=len(sources),
            kb_row_count_before=kb_row_count_before,
            kb_row_count_after=kb_row_count_after,
            llm_calls=int(usage["calls"]),
            prompt_tokens=int(usage["prompt_tokens"]),
            completion_tokens=int(usage["completion_tokens"]),
            total_tokens=int(usage["total_tokens"]),
            prompt_chars=int(usage["prompt_chars"]),
            citation_total=citation_total,
            citation_valid=citation_valid,
            citation_valid_rate=None if citation_valid_rate is None else round(citation_valid_rate, 4),
        )
    except Exception as exc:
        latency = time.perf_counter() - start
        usage = get_usage_totals()
        logger.exception(f"Benchmark topic failed: {cfg.topic}")
        return TopicMetrics(
            topic=cfg.topic,
            domain=cfg.domain,
            variant=variant,
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            latency_seconds=round(latency, 2),
            llm_calls=int(usage["calls"]),
            prompt_tokens=int(usage["prompt_tokens"]),
            completion_tokens=int(usage["completion_tokens"]),
            total_tokens=int(usage["total_tokens"]),
            prompt_chars=int(usage["prompt_chars"]),
        )


def average(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def summarize(variant: str, rows: list[TopicMetrics]) -> VariantSummary:
    successful = [row for row in rows if row.success]
    token_values = [row.total_tokens for row in successful if row.total_tokens > 0]
    citation_pairs = [
        (row.citation_valid or 0, row.citation_total or 0)
        for row in successful
        if row.citation_total is not None
    ]
    citation_total = sum(total for _, total in citation_pairs)
    citation_valid = sum(valid for valid, _ in citation_pairs)

    return VariantSummary(
        variant=variant,
        task_count=len(rows),
        success_rate=0.0 if not rows else round(len(successful) / len(rows), 4),
        avg_latency_seconds=round(average([row.latency_seconds for row in successful]), 2),
        avg_research_loops=round(average([row.research_loops for row in successful]), 2),
        avg_state_query_count=round(average([row.state_query_count for row in successful]), 2),
        avg_state_duplicate_query_rate=round(average([row.state_duplicate_query_rate for row in successful]), 4),
        avg_executed_query_count=round(average([row.executed_query_count for row in successful]), 2),
        avg_executed_duplicate_query_rate=round(average([row.executed_duplicate_query_rate for row in successful]), 4),
        avg_skipped_duplicate_query_count=round(average([row.skipped_duplicate_query_count for row in successful]), 2),
        avg_llm_calls=round(average([row.llm_calls for row in successful]), 2),
        avg_total_tokens=None if not token_values else round(average(token_values), 2),
        avg_prompt_chars=round(average([row.prompt_chars for row in successful]), 2),
        citation_valid_rate=None if citation_total == 0 else round(citation_valid / citation_total, 4),
    )


def pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def delta(before: float | None, after: float | None, percent_point: bool = False) -> str:
    if before is None or after is None:
        return "N/A"
    diff = after - before
    if percent_point:
        return f"{diff * 100:+.1f}pp"
    if before == 0:
        return f"{diff:+.2f}"
    return f"{diff / before * 100:+.1f}%"


def render_markdown(
    report: dict[str, Any],
    output_json: Path,
    judge_enabled: bool,
) -> str:
    summaries = {item["variant"]: item for item in report["summaries"]}
    base = summaries.get("baseline")
    opt = summaries.get("optimized")
    now = report["timestamp"]

    lines = [
        "# Agent Harness Benchmark",
        "",
        f"- 生成时间: {now}",
        f"- 原始数据: `{output_json}`",
        f"- Benchmark 集: `{report['benchmark_set']}`",
        f"- Run mode: `{report['run_mode']}`",
        f"- Query model: `{report.get('query_model') or 'default'}`",
        f"- Reflection model: `{report.get('reflection_model') or 'default'}`",
        f"- Citation Judge: {'enabled' if judge_enabled else 'disabled'}",
        "",
        "## 问题",
        "",
        "并行检索阶段把生成查询和已执行查询混写到累加型 `search_query` 状态，导致多轮任务中查询列表被重复累计，后续评估、引用追踪和成本分析都失真。",
        "",
        "## 优化",
        "",
        "将查询状态拆分为 `generated_queries`、`executed_queries` 和 `skipped_duplicate_queries`，并在 fan-out 和 follow-up 执行前做规范化去重。`QUERY_DEDUPE_ENABLED=0` 用于复现 baseline，默认开启优化。",
        "",
        "## 汇总结果",
        "",
        "| 指标 | Baseline | Optimized | 变化 |",
        "|---|---:|---:|---:|",
    ]

    if base and opt:
        rows = [
            ("任务成功率", pct(base["success_rate"]), pct(opt["success_rate"]), delta(base["success_rate"], opt["success_rate"], True)),
            ("状态查询重复率", pct(base["avg_state_duplicate_query_rate"]), pct(opt["avg_state_duplicate_query_rate"]), delta(base["avg_state_duplicate_query_rate"], opt["avg_state_duplicate_query_rate"], True)),
            ("实际执行查询重复率", pct(base["avg_executed_duplicate_query_rate"]), pct(opt["avg_executed_duplicate_query_rate"]), delta(base["avg_executed_duplicate_query_rate"], opt["avg_executed_duplicate_query_rate"], True)),
            ("平均状态查询数", f"{base['avg_state_query_count']:.2f}", f"{opt['avg_state_query_count']:.2f}", delta(base["avg_state_query_count"], opt["avg_state_query_count"])),
            ("平均执行查询数", f"{base['avg_executed_query_count']:.2f}", f"{opt['avg_executed_query_count']:.2f}", delta(base["avg_executed_query_count"], opt["avg_executed_query_count"])),
            ("平均 LLM 调用数", f"{base['avg_llm_calls']:.2f}", f"{opt['avg_llm_calls']:.2f}", delta(base["avg_llm_calls"], opt["avg_llm_calls"])),
            ("平均 total tokens", str(base["avg_total_tokens"] or "N/A"), str(opt["avg_total_tokens"] or "N/A"), delta(base["avg_total_tokens"], opt["avg_total_tokens"])),
            ("平均 prompt chars", f"{base['avg_prompt_chars']:.2f}", f"{opt['avg_prompt_chars']:.2f}", delta(base["avg_prompt_chars"], opt["avg_prompt_chars"])),
            ("引用有效率", pct(base.get("citation_valid_rate")), pct(opt.get("citation_valid_rate")), delta(base.get("citation_valid_rate"), opt.get("citation_valid_rate"), True)),
        ]
        for name, before, after, change in rows:
            lines.append(f"| {name} | {before} | {after} | {change} |")
    else:
        lines.append("| N/A | N/A | N/A | N/A |")

    lines.extend([
        "",
        "## 单题结果",
        "",
        "| Variant | Topic | Success | State Dup | Exec Dup | State Q | Exec Q | Loops | KB Before | KB After | LLM Calls | Error |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ])
    for row in report["topics"]:
        lines.append(
            "| {variant} | {topic} | {success} | {state_dup} | {exec_dup} | {state_q} | {exec_q} | {loops} | {kb_before} | {kb_after} | {calls} | {error} |".format(
                variant=row["variant"],
                topic=row["topic"][:48].replace("|", "\\|"),
                success="yes" if row["success"] else "no",
                state_dup=pct(row["state_duplicate_query_rate"]),
                exec_dup=pct(row["executed_duplicate_query_rate"]),
                state_q=row["state_query_count"],
                exec_q=row["executed_query_count"],
                loops=row["research_loops"],
                kb_before=row.get("kb_row_count_before"),
                kb_after=row.get("kb_row_count_after"),
                calls=row["llm_calls"],
                error=(row["error"] or "")[:80].replace("|", "\\|"),
            )
        )

    lines.extend([
        "",
        "## 简历可用表述",
        "",
        "如果 10 题全部真实跑通，可将上表中的优化前后数据压缩为简历 bullet；如果存在 blocked/error，应只引用成功样本范围，并在报告中保留失败原因。",
    ])
    return "\n".join(lines) + "\n"


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepResearch harness A/B benchmark")
    parser.add_argument("--benchmark-set", type=Path, default=DEFAULT_SET)
    parser.add_argument("--output", type=Path, default=Path("benchmark_report_20260616.json"))
    parser.add_argument("--markdown", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--variant", choices=["baseline", "optimized", "both"], default="both")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--initial-queries", type=int, default=None)
    parser.add_argument("--max-loops", type=int, default=None)
    parser.add_argument("--query-model", type=str, default=None)
    parser.add_argument("--reflection-model", type=str, default=None)
    parser.add_argument("--judge-citations", action="store_true")
    parser.add_argument("--keep-search-cache", action="store_true")
    parser.add_argument(
        "--research-only",
        action="store_true",
        help="只运行 ResearchAgent 子图，用于快速采集检索 Harness 指标",
    )
    args = parser.parse_args()

    topics = load_topics(args.benchmark_set, limit=args.limit)
    for topic in topics:
        if args.initial_queries is not None:
            topic.initial_search_query_count = args.initial_queries
        if args.max_loops is not None:
            topic.max_research_loops = args.max_loops
    variants = ["baseline", "optimized"] if args.variant == "both" else [args.variant]
    judge = Judge() if args.judge_citations else None

    rows: list[TopicMetrics] = []
    for variant in variants:
        logger.info(f"Running benchmark variant={variant}, topics={len(topics)}")
        for index, cfg in enumerate(topics, start=1):
            logger.info(f"[{variant}] {index}/{len(topics)} {cfg.topic}")
            rows.append(
                await run_topic(
                    cfg,
                    variant=variant,
                    judge=judge,
                    clear_search_cache=not args.keep_search_cache,
                    research_only=args.research_only,
                    query_model=args.query_model,
                    reflection_model=args.reflection_model,
                )
            )

    summaries = [
        summarize(variant, [row for row in rows if row.variant == variant])
        for variant in variants
    ]

    report = {
        "timestamp": datetime.now().isoformat(),
        "benchmark_set": str(args.benchmark_set),
        "run_mode": "research-only" if args.research_only else "full",
        "query_model": args.query_model,
        "reflection_model": args.reflection_model,
        "variants": variants,
        "summaries": [asdict(item) for item in summaries],
        "topics": [asdict(item) for item in rows],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Benchmark JSON saved to {args.output}")

    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(
        render_markdown(report, args.output, judge_enabled=args.judge_citations),
        encoding="utf-8",
    )
    logger.info(f"Benchmark Markdown saved to {args.markdown}")
def main() -> None:
    """Run the async benchmark CLI."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
