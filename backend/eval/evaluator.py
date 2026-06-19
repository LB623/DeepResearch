"""DeepResearch Agent 的评估运行器。

支持两种模式：
  - e2e:   在测试主题上运行完整的 agent 流水线，对最终报告进行评分。
  - comp:  对各个节点（plan、queries、critique、citations）进行组件级评估。

包含 human-in-the-loop 的计划确认步骤，因此我们使用两阶段调用：
(1) 获取计划，(2) 自动确认并继续。当配置了用户反馈时，升级为三阶段调用。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import textwrap
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from loguru import logger

from agent.configuration import Configuration
from agent.graph import graph
from eval.judge import (
    CitationScore,
    CritiqueScore,
    E2EScore,
    Judge,
    PlanQueryAlignmentScore,
    PlanReflectionScore,
    PlanScore,
    QueryScore,
    SummarizationScore,
)

load_dotenv()


# ============================================================
# 辅助工具 — 捕获 graph 未暴露的中间输出
# ============================================================

class _CaptureCtx:
    """通过 monkey-patch 注入 WebSearchAgent 的线程局部捕获容器。

    graph 的 web_search 节点内部调用 WebSearchAgent.step()，
    由 LLM 进行摘要，仅将摘要存入 state。我们 hook .step()
    以便原始搜索结果可用于摘要保真度评估。
    """

    def __init__(self):
        self.raw_results: list[dict] = []  # 每次 web_search 调用的原始页面

    def patch(self):
        import agent.base_agent as mod

        self._orig_step = mod.WebSearchAgent.step

        def _patched_step(agent_self, prompt, **kwargs):
            result = self._orig_step(agent_self, prompt, **kwargs)
            if result:
                self.raw_results.append(
                    {"query": prompt, "pages": result}
                )
            return result

        mod.WebSearchAgent.step = _patched_step

    def unpatch(self):
        import agent.base_agent as mod

        mod.WebSearchAgent.step = self._orig_step


def _normalize_query(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _stable_unique_queries(values: list[object]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value or "").strip()
        normalized = _normalize_query(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(text)
    return unique


# ============================================================
# 数据类型
# ============================================================

@dataclass
class TopicCfg:
    """每个主题的评估运行配置。"""
    topic: str
    initial_search_query_count: int = 2
    max_research_loops: int = 2
    user_feedback: str | None = None
    expected_intent: str | None = None


@dataclass
class E2EResult:
    topic: str
    report: str = ""
    sources: str = ""  # JSON 序列化的 sources_gathered
    score: E2EScore | None = None
    error: str | None = None


@dataclass
class ComponentResult:
    topic: str
    plan_score: PlanScore | None = None
    plan_query_alignment_score: PlanQueryAlignmentScore | None = None
    query_score: QueryScore | None = None
    summarization_scores: list[SummarizationScore] = field(default_factory=list)
    critique_score: CritiqueScore | None = None
    citation_score: CitationScore | None = None
    plan_reflection_score: PlanReflectionScore | None = None
    error: str | None = None


@dataclass
class EvalReport:
    timestamp: str
    e2e_results: list[E2EResult] = field(default_factory=list)
    component_results: list[ComponentResult] = field(default_factory=list)


# ============================================================
# 评估器
# ============================================================

class Evaluator:
    """编排端到端和组件级评估。"""

    def __init__(self, judge_model_id: str | None = None):
        self.judge = Judge(model_id=judge_model_id)
        self._async_runner = asyncio.Runner()

    def _invoke_graph(self, state: dict, config: dict) -> dict:
        """Run the async LangGraph from the synchronous eval CLI."""
        return self._async_runner.run(graph.ainvoke(state, config=config))

    def close(self) -> None:
        """Release the persistent event loop after all eval topics finish."""
        self._async_runner.close()

    # --------------------------------------------------------
    # 端到端
    # --------------------------------------------------------

    def run_e2e(self, topics: list[TopicCfg]) -> list[E2EResult]:
        """对每个主题运行完整的 agent 并对最终报告进行评分。"""
        results: list[E2EResult] = []
        for i, cfg in enumerate(topics):
            logger.info(f"端到端 [{i + 1}/{len(topics)}] 主题={cfg.topic[:80]}...")
            try:
                result = self._invoke_agent(cfg)
                if result.error:
                    results.append(result)
                    continue

                result.score = self.judge.evaluate_report(
                    research_topic=cfg.topic,
                    search_sources=result.sources,
                    report=result.report,
                )
                results.append(result)
                logger.info(
                    f"  总评分={result.score.overall_score if result.score else '无'}"
                )
            except Exception as exc:
                logger.error(f"端到端评估失败 '{cfg.topic[:60]}': {exc}")
                results.append(E2EResult(topic=cfg.topic, error=str(exc)))
        return results

    # --------------------------------------------------------
    # 组件级
    # --------------------------------------------------------

    def run_components(self, topics: list[TopicCfg]) -> list[ComponentResult]:
        """对每个主题独立评估各个 agent 节点。"""
        results: list[ComponentResult] = []
        for i, cfg in enumerate(topics):
            logger.info(f"组件级 [{i + 1}/{len(topics)}] 主题={cfg.topic[:80]}...")
            try:
                results.append(self._eval_one_topic_components(cfg))
            except Exception as exc:
                logger.error(f"组件级评估失败 '{cfg.topic[:60]}': {exc}")
                results.append(ComponentResult(topic=cfg.topic, error=str(exc)))
        return results

    # --------------------------------------------------------
    # 内部：agent 调用（共享辅助方法）
    # --------------------------------------------------------

    def _invoke_agent_with_feedback(
        self, cfg: TopicCfg, capture: _CaptureCtx | None = None
    ) -> dict:
        """调用 agent，可选择在计划确认阶段模拟用户反馈。

        当提供 *capture* 时，其 patch 在研究阶段处于激活状态，
        以便拦截原始搜索结果。

        返回一个包含以下键的字典：
            plan_a、plan_b、actual_behavior、report、sources、phase2_state
        """
        config = {
            "configurable": {
                "thread_id": f"eval-{hash(cfg.topic + (cfg.user_feedback or '')) & 0xFFFF}-{uuid.uuid4().hex[:8]}",
                "number_of_initial_queries": cfg.initial_search_query_count,
                "max_research_loops": cfg.max_research_loops,
            }
        }

        # ---- 阶段 1：触发计划生成 ----
        phase1_state = self._invoke_graph(
            {"messages": [HumanMessage(content=cfg.topic)]},
            config=config,
        )
        plan_a = phase1_state.get("plan", "")

        if cfg.user_feedback is None:
            # 向后兼容的两阶段自动确认流程
            if capture:
                capture.patch()
            try:
                phase2_state = self._invoke_graph(
                    {
                        "messages": [
                            HumanMessage(content=cfg.topic),
                            *(phase1_state.get("plan_messages", [])),
                            HumanMessage(content="需求确认"),
                        ],
                        "plan": plan_a,
                        "plan_status": "confirmed",
                        "initial_search_query_count": cfg.initial_search_query_count,
                        "max_research_loops": cfg.max_research_loops,
                        "research_loop_count": 0,
                    },
                    config=config,
                )
            finally:
                if capture:
                    capture.unpatch()
            actual_behavior = "direct_proceed"
            plan_b = ""
        else:
            # ---- 阶段 2：发送用户反馈 ----
            phase2_state = self._invoke_graph(
                {
                    "messages": [
                        HumanMessage(content=cfg.topic),
                        *(phase1_state.get("plan_messages", [])),
                        HumanMessage(content=cfg.user_feedback),
                    ],
                    "plan": plan_a,
                    "plan_status": "confirmed",
                    "initial_search_query_count": cfg.initial_search_query_count,
                    "max_research_loops": cfg.max_research_loops,
                    "research_loop_count": 0,
                },
                config=config,
            )

            plan_status_after_p2 = phase2_state.get("plan_status", "")
            if plan_status_after_p2 == "unconfirmed":
                actual_behavior = "replan_then_proceed"
                plan_b = phase2_state.get("plan", "")
                # ---- 阶段 3：确认重新计划后的结果（研究） ----
                if capture:
                    capture.patch()
                try:
                    phase2_state = self._invoke_graph(
                        {
                            "messages": [
                                HumanMessage(content=cfg.topic),
                                *(phase2_state.get("plan_messages", [])),
                                HumanMessage(content="需求确认"),
                            ],
                            "plan": plan_b,
                            "plan_status": "confirmed",
                            "initial_search_query_count": cfg.initial_search_query_count,
                            "max_research_loops": cfg.max_research_loops,
                            "research_loop_count": 0,
                        },
                        config=config,
                    )
                finally:
                    if capture:
                        capture.unpatch()
            elif any(kw in cfg.user_feedback for kw in ["需求确认", "开始研究"]):
                actual_behavior = "direct_proceed"
                plan_b = ""
            else:
                actual_behavior = "llm_proceed"
                plan_b = ""

        # 提取最终报告
        messages = phase2_state.get("messages", [])
        report = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content and len(msg.content) > 200:
                report = msg.content
                break

        sources = json.dumps(
            phase2_state.get("sources_gathered", []),
            ensure_ascii=False,
            indent=2,
        )

        return {
            "plan_a": plan_a,
            "plan_b": plan_b,
            "actual_behavior": actual_behavior,
            "report": report,
            "sources": sources,
            "phase1_state": phase1_state,
            "phase2_state": phase2_state,
        }

    def _invoke_agent(self, cfg: TopicCfg) -> E2EResult:
        """运行 agent 并返回 E2EResult。

        当设置了 *cfg.user_feedback* 时，计划确认阶段通过 LLM 意图识别路径
        进行测试；否则使用现有的自动确认行为。
        """
        try:
            result = self._invoke_agent_with_feedback(cfg)
            return E2EResult(
                topic=cfg.topic,
                report=result["report"],
                sources=result["sources"],
            )
        except Exception as exc:
            logger.error(f"Agent 调用失败: {exc}")
            return E2EResult(topic=cfg.topic, error=str(exc))

    # --------------------------------------------------------
    # 内部：单个主题的组件级评估
    # --------------------------------------------------------

    def _eval_one_topic_components(self, cfg: TopicCfg) -> ComponentResult:
        result = ComponentResult(topic=cfg.topic)
        capture = _CaptureCtx()

        # 通过共享辅助方法运行完整流水线（如配置了反馈则处理反馈）
        agent_result = self._invoke_agent_with_feedback(cfg, capture)

        plan_a = agent_result["plan_a"]
        plan_b = agent_result["plan_b"]
        actual_behavior = agent_result["actual_behavior"]
        phase2 = agent_result["phase2_state"]

        # 实际用于研究的计划
        effective_plan = plan_b if plan_b else plan_a

        # 评估计划（用于研究的那个）
        if effective_plan:
            result.plan_score = self.judge.evaluate_plan(
                research_topic=cfg.topic, plan=effective_plan
            )

        # 评估计划反思（仅在提供了用户反馈时）
        if cfg.user_feedback and cfg.expected_intent:
            result.plan_reflection_score = self.judge.evaluate_plan_reflection(
                original_plan=plan_a,
                user_feedback=cfg.user_feedback,
                new_plan=plan_b,
                actual_behavior=actual_behavior,
                expected_intent=cfg.expected_intent,
            )

        # 评估搜索查询
        search_queries = phase2.get("generated_queries") or phase2.get("search_query", [])
        if search_queries:
            query_list = (
                _stable_unique_queries(search_queries)
                if isinstance(search_queries, list)
                else []
            )
            result.query_score = self.judge.evaluate_queries(
                research_topic=cfg.topic,
                queries=query_list,
                rationale="（内部推理未捕获；参见计划上下文）",
            )

            # 评估计划 → 查询对齐（针对用于研究的计划）
            if effective_plan and query_list:
                result.plan_query_alignment_score = (
                    self.judge.evaluate_plan_query_alignment(
                        plan=effective_plan, queries=query_list
                    )
                )

        # 评估摘要保真度（针对每个捕获的原始搜索结果）
        web_search_results = list(phase2.get("web_search_result", []) or [])
        executed_queries = list(phase2.get("executed_queries", []) or [])
        raw_by_query: dict[str, deque[dict]] = defaultdict(deque)
        for raw in capture.raw_results:
            raw_by_query[_normalize_query(raw.get("query", ""))].append(raw)

        for query, summary in zip(executed_queries, web_search_results):
            candidates = raw_by_query.get(_normalize_query(query))
            raw = candidates.popleft() if candidates else None
            if not raw or not summary:
                continue
            score = self.judge.evaluate_summarization(
                search_query=raw.get("query", ""),
                raw_search_results=json.dumps(raw.get("pages", []), ensure_ascii=False, indent=2),
                summary=str(summary),
            )
            if score:
                result.summarization_scores.append(score)

        # 评估反思
        is_sufficient = phase2.get("is_sufficient")
        if is_sufficient is not None:
            result.critique_score = self.judge.evaluate_critique(
                research_topic=cfg.topic,
                summaries="\n---\n".join(
                    str(s) for s in phase2.get("web_search_result", [])
                ),
                is_sufficient=bool(is_sufficient),
                knowledge_gap=phase2.get("knowledge_gap", ""),
                follow_up_queries=phase2.get("follow_up_queries", []),
            )

        # 评估最终报告中的引用
        report = agent_result["report"]
        if report:
            sources = agent_result["sources"]
            if sources and sources != "[]":
                result.citation_score = self.judge.evaluate_citations(
                    sources=sources, report=report
                )

        return result


# ============================================================
# 报告格式化
# ============================================================

def format_eval_report(report: EvalReport) -> str:
    """渲染一份人类可读的评估摘要。"""
    lines = ["=" * 72, "  DeepResearch Agent 评估报告", "=" * 72, ""]

    # 端到端摘要
    if report.e2e_results:
        lines.append("--- 端到端报告得分 ---")
        lines.append("")
        scores = []
        for r in report.e2e_results:
            if r.score:
                scores.append(r.score)
                lines.append(f"  主题: {r.topic[:80]}")
                lines.append(f"    总评分: {r.score.overall_score:.1f}/5")
                lines.append(f"    事实准确性: {r.score.factual_accuracy.score}/5")
                lines.append(f"    信息覆盖度: {r.score.information_coverage.score}/5")
                lines.append(f"    逻辑结构:   {r.score.logical_structure.score}/5")
                lines.append(f"    时效性:     {r.score.timeliness.score}/5")
                lines.append(f"    引用质量:   {r.score.citation_quality.score}/5")
                lines.append(
                    f"    幻觉:       {'有' if r.score.hallucination_check.get('has_hallucinations') else '无'}"
                )
                lines.append("")
            elif r.error:
                lines.append(f"  主题: {r.topic[:80]}  错误: {r.error[:120]}")
                lines.append("")

        if scores:
            avg = sum(s.overall_score for s in scores) / len(scores)
            lines.append(f"  ** 平均总评分: {avg:.1f}/5 (n={len(scores)}) **")
            lines.append("")

    # 组件级摘要
    if report.component_results:
        lines.append("--- 组件级得分 ---")
        lines.append("")
        for r in report.component_results:
            lines.append(f"  主题: {r.topic[:80]}")
            if r.plan_score:
                lines.append(f"    计划:             {r.plan_score.overall_score:.1f}/5")
            if r.plan_reflection_score:
                prs = r.plan_reflection_score
                lines.append(f"    计划反思:")
                lines.append(f"      意图识别:       {prs.intent_recognition.score}/5")
                lines.append(f"      反馈吸收:       {prs.feedback_incorporation.score}/5")
                lines.append(f"      总评分:         {prs.overall_score:.1f}/5  (行为: {prs.actual_behavior})")
            if r.query_score:
                lines.append(f"    搜索查询:         {r.query_score.overall_score:.1f}/5")
            if r.plan_query_alignment_score:
                lines.append(f"    计划→查询:       {r.plan_query_alignment_score.overall_score:.1f}/5")
                if r.plan_query_alignment_score.missed_dimensions:
                    lines.append(f"      遗漏: {', '.join(r.plan_query_alignment_score.missed_dimensions[:3])}")
            if r.summarization_scores:
                avg_sum = sum(s.overall_score for s in r.summarization_scores) / len(
                    r.summarization_scores
                )
                lines.append(f"    摘要保真度:       {avg_sum:.1f}/5 (n={len(r.summarization_scores)})")
            if r.critique_score:
                lines.append(f"    反思:             {r.critique_score.overall_score:.1f}/5")
            if r.citation_score:
                cs = r.citation_score
                lines.append(f"    引用:             {cs.citation_accuracy_score}/5  (有效={cs.valid_citations}/{cs.total_citations}, 弱={cs.weak_citations}, 无效={cs.invalid_citations})")
                for ref in cs.per_citation[:3]:
                    if ref.status != "valid":
                        lines.append(f"      [{ref.status}] {ref.url[:60]} — {ref.reason[:80]}")
            if r.error:
                lines.append(f"    错误: {r.error[:120]}")
            lines.append("")

    return "\n".join(lines)


def save_eval_report(report: EvalReport, path: str = "eval_report.json") -> None:
    """将完整评估数据保存为 JSON 文件以供进一步分析。"""

    def _serialize(obj):
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, default=_serialize, ensure_ascii=False, indent=2)
    logger.info(f"完整评估报告已保存至 {path}")
