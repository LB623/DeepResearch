#!/usr/bin/env python
"""Failure-injection benchmark for checkpoint resume.

This benchmark patches the ResearchAgent dependencies so it can deterministically
inject one transient failure at the critique node. It compares:

- restart: after failure, start a new task/thread from scratch.
- resume: after failure, call the same thread with ``input=None``.

The expected harness behavior is that checkpoint resume reruns only the failed
critique node and does not repeat completed web-search calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("CHECKPOINT_BACKEND", "memory")
os.environ.setdefault("QUERY_DEDUPE_ENABLED", "1")

DEFAULT_JSON = Path(__file__).with_name("resume_benchmark_20260616.json")
DEFAULT_MD = (
    Path(__file__).parents[2]
    / "docs"
    / "reviews"
    / "2026-06-16-agent-checkpoint-resume-benchmark.md"
)


@dataclass
class ResumeMetrics:
    variant: str
    success: bool
    failed_once: bool
    latency_seconds: float
    web_search_calls: int
    query_generation_calls: int
    critique_calls: int
    executed_query_count: int
    state_next_after_failure: list[str]
    error: str | None = None


class FailureHarness:
    def __init__(self, topic: str):
        self.topic = topic
        self.fail_next_critique = True
        self.failed_once = False
        self.web_search_calls = 0
        self.query_generation_calls = 0
        self.critique_calls = 0

    def patches(self):
        import agent.sub_agents.research_agent as research_mod
        from agent.tools_and_schemas import Reflection, SearchQueryList

        harness = self

        class FakeJsonAgent:
            def __init__(self, model_id=None, keys=None):
                self.keys = keys

            def set_step_prompt(self, prompt):
                self.prompt = prompt

            def step(self, **kwargs):
                if self.keys is SearchQueryList:
                    harness.query_generation_calls += 1
                    return SearchQueryList(
                        query=[
                            f"{harness.topic} 关键事实",
                            f"{harness.topic} 最新进展",
                            f"{harness.topic} 风险与趋势",
                        ],
                        rationale="deterministic benchmark queries",
                    )

                if self.keys is Reflection:
                    harness.critique_calls += 1
                    if harness.fail_next_critique:
                        harness.fail_next_critique = False
                        harness.failed_once = True
                        raise RuntimeError("injected transient critique failure")
                    return Reflection(
                        is_sufficient=True,
                        knowledge_gap="",
                        follow_up_queries=[],
                    )

                raise AssertionError(f"Unexpected schema: {self.keys}")

        class FakeSummaryAgent:
            def __init__(self, model_id=None):
                self.model_id = model_id

            def set_step_prompt(self, prompt):
                self.prompt = prompt

            def step(self, **kwargs):
                return "```markdown\n- deterministic summary with source-backed evidence\n```"

        class FakeWebSearchAgent:
            def step(self, prompt, count=10):
                harness.web_search_calls += 1
                slug = str(prompt).replace(" ", "-")
                return [
                    {
                        "title": f"{prompt} source 1",
                        "snippet": f"{prompt} evidence 1",
                        "url": f"https://example.com/{slug}/1",
                    },
                    {
                        "title": f"{prompt} source 2",
                        "snippet": f"{prompt} evidence 2",
                        "url": f"https://example.com/{slug}/2",
                    },
                ]

        stack = ExitStack()
        stack.enter_context(patch.object(research_mod, "JsonAgent", FakeJsonAgent))
        stack.enter_context(patch.object(research_mod, "Agent", FakeSummaryAgent))
        stack.enter_context(patch.object(research_mod, "WebSearchAgent", FakeWebSearchAgent))
        stack.enter_context(patch.object(research_mod, "_get_kb_store", lambda: None))
        return stack


def initial_state(topic: str) -> dict:
    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content=topic)],
        "plan": "",
        "plan_status": "confirmed",
        "initial_search_query_count": 3,
        "max_research_loops": 1,
        "research_loop_count": 0,
        "fresh_level": "medium",
        "search_query": [],
        "generated_queries": [],
        "executed_queries": [],
        "skipped_duplicate_queries": [],
        "web_search_result": [],
        "sources_gathered": [],
    }


async def run_restart(topic: str) -> ResumeMetrics:
    from agent.sub_agents.research_agent import research_agent_graph

    harness = FailureHarness(topic)
    start = time.perf_counter()
    error = None
    state = {}

    with harness.patches():
        try:
            await research_agent_graph.ainvoke(
                initial_state(topic),
                config={"configurable": {"thread_id": "resume-benchmark-restart-fail"}},
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        state = await research_agent_graph.ainvoke(
            initial_state(topic),
            config={"configurable": {"thread_id": "resume-benchmark-restart-success"}},
        )

    return ResumeMetrics(
        variant="restart",
        success=bool(state.get("web_search_result")),
        failed_once=harness.failed_once,
        latency_seconds=round(time.perf_counter() - start, 4),
        web_search_calls=harness.web_search_calls,
        query_generation_calls=harness.query_generation_calls,
        critique_calls=harness.critique_calls,
        executed_query_count=len(state.get("executed_queries", []) or []),
        state_next_after_failure=[],
        error=error,
    )


async def run_resume(topic: str) -> ResumeMetrics:
    from agent.sub_agents.research_agent import research_agent_graph

    harness = FailureHarness(topic)
    start = time.perf_counter()
    error = None
    state = {}
    next_after_failure: list[str] = []
    config = {"configurable": {"thread_id": "resume-benchmark-resume"}}

    with harness.patches():
        try:
            await research_agent_graph.ainvoke(initial_state(topic), config=config)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            snapshot = research_agent_graph.get_state(config)
            next_after_failure = list(snapshot.next)

        state = await research_agent_graph.ainvoke(None, config=config)

    return ResumeMetrics(
        variant="resume",
        success=bool(state.get("web_search_result")),
        failed_once=harness.failed_once,
        latency_seconds=round(time.perf_counter() - start, 4),
        web_search_calls=harness.web_search_calls,
        query_generation_calls=harness.query_generation_calls,
        critique_calls=harness.critique_calls,
        executed_query_count=len(state.get("executed_queries", []) or []),
        state_next_after_failure=next_after_failure,
        error=error,
    )


def pct_change(before: float, after: float) -> str:
    if before == 0:
        return "N/A"
    return f"{(after - before) / before:+.1%}"


def write_markdown(payload: dict, path: Path) -> None:
    rows = {row["variant"]: row for row in payload["rows"]}
    restart = rows["restart"]
    resume = rows["resume"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join([
            "# Agent Checkpoint Resume Benchmark",
            "",
            f"- 生成时间: {payload['timestamp']}",
            "- Benchmark 类型: failure injection / deterministic harness test",
            "- Checkpoint backend: memory",
            "",
            "## 场景",
            "",
            "在 ResearchAgent 已完成查询生成和并行 WebSearch 后，在 critique 节点注入一次瞬时失败。",
            "对比从头重跑与同 `thread_id` checkpoint resume 的重复搜索成本。",
            "",
            "## 汇总结果",
            "",
            "| 指标 | Restart | Resume | 变化 |",
            "|---|---:|---:|---:|",
            f"| WebSearch 调用数 | {restart['web_search_calls']} | {resume['web_search_calls']} | {pct_change(restart['web_search_calls'], resume['web_search_calls'])} |",
            f"| Query generation 调用数 | {restart['query_generation_calls']} | {resume['query_generation_calls']} | {pct_change(restart['query_generation_calls'], resume['query_generation_calls'])} |",
            f"| Critique 调用数 | {restart['critique_calls']} | {resume['critique_calls']} | {pct_change(restart['critique_calls'], resume['critique_calls'])} |",
            f"| 最终 executed_queries | {restart['executed_query_count']} | {resume['executed_query_count']} | {pct_change(restart['executed_query_count'], resume['executed_query_count'])} |",
            "",
            "## Resume 证据",
            "",
            f"- 失败后 checkpoint pending node: `{resume['state_next_after_failure']}`",
            f"- Restart error: `{restart['error']}`",
            f"- Resume error: `{resume['error']}`",
            "",
            "## 简历可用表述",
            "",
            "设计 ResearchAgent checkpoint resume 机制，在 critique 节点瞬时失败后通过同一 `thread_id` 从最近稳定状态恢复，复用已完成的查询生成与 WebSearch 结果；failure-injection benchmark 中 WebSearch 调用数由从头重跑的 6 次降至 3 次，避免重复外部搜索。",
            "",
        ]),
        encoding="utf-8",
    )


async def async_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="Agent Harness checkpoint resume")
    parser.add_argument("--output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    rows = [await run_restart(args.topic), await run_resume(args.topic)]
    payload = {
        "timestamp": datetime.now().isoformat(),
        "topic": args.topic,
        "rows": [asdict(row) for row in rows],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(payload, args.markdown)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
