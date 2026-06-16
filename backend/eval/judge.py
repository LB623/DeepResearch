"""LLM-as-Judge：封装 OpenAI 兼容的 LLM 来对 agent 输出进行评分。"""

from __future__ import annotations

import json
import os
import traceback
from typing import Any

from agent.base_agent import Agent, JsonAgent
from agent.post import Post
from eval.prompts import (
    CITATION_JUDGE_INSTRUCTIONS,
    CRITIQUE_JUDGE_INSTRUCTIONS,
    E2E_JUDGE_INSTRUCTIONS,
    PLAN_JUDGE_INSTRUCTIONS,
    PLAN_QUERY_ALIGNMENT_JUDGE_INSTRUCTIONS,
    PLAN_REFLECTION_JUDGE_INSTRUCTIONS,
    QUERY_JUDGE_INSTRUCTIONS,
    SUMMARIZATION_JUDGE_INSTRUCTIONS,
)
from loguru import logger
from pydantic import BaseModel, Field


# ---------- 结构化 Judge 输出的 Pydantic 模式 ----------

class DimScore(BaseModel):
    score: int = Field(ge=1, le=5)
    reason: str


class E2EScore(BaseModel):
    factual_accuracy: DimScore
    information_coverage: DimScore
    logical_structure: DimScore
    timeliness: DimScore
    citation_quality: DimScore
    overall_score: float
    overall_assessment: str
    hallucination_check: dict


class PlanScore(BaseModel):
    requirement_coverage: DimScore
    question_clarity: DimScore
    structure_quality: DimScore
    overall_score: float
    missing_dimensions: list[str] = Field(default_factory=list)
    assessment: str


class QueryScore(BaseModel):
    coverage: DimScore
    independence: DimScore
    search_friendliness: DimScore
    overall_score: float
    missing_angles: list[str] = Field(default_factory=list)
    assessment: str


class SummarizationScore(BaseModel):
    factual_fidelity: DimScore
    key_info_extraction: DimScore
    source_attribution: DimScore
    overall_score: float
    hallucinations: list[str] = Field(default_factory=list)
    assessment: str


class CritiqueScore(BaseModel):
    sufficiency_judgment: DimScore
    gap_identification: DimScore
    follow_up_query_quality: DimScore
    overall_score: float
    is_sufficiency_correct: bool
    assessment: str


class CitationPerRef(BaseModel):
    """单条引用审计记录。"""
    url: str
    label: str = ""
    paragraph_summary: str = ""
    source_title: str = ""
    status: str = ""  # valid | weak | content_mismatch | url_not_found
    reason: str = ""


class CitationSummaryStats(BaseModel):
    valid_rate: float = 0.0
    most_common_issue: str = ""
    worst_offender_url: str = ""


class CitationScore(BaseModel):
    total_citations: int
    valid_citations: int
    weak_citations: int = 0
    invalid_citations: int
    per_citation: list[CitationPerRef] = Field(default_factory=list)
    citation_accuracy_score: int = Field(ge=1, le=5)
    summary_stats: CitationSummaryStats | None = None
    assessment: str


class PlanQueryAlignmentScore(BaseModel):
    coverage_consistency: DimScore
    plan_fidelity: DimScore
    structural_decomposition: DimScore
    overall_score: float
    covered_dimensions: list[str] = Field(default_factory=list)
    missed_dimensions: list[str] = Field(default_factory=list)
    cross_reference_table: list[dict] = Field(default_factory=list)
    assessment: str


class PlanReflectionScore(BaseModel):
    intent_recognition: DimScore
    feedback_incorporation: DimScore
    overall_score: float
    actual_behavior: str = ""
    assessment: str


def _safe_format(template: str, **kwargs) -> str:
    """将 *template* 中的 {key} 占位符替换为 *values*，保留所有其他花括号
    不变（安全处理嵌入的 JSON 示例和可能包含字面花括号字符的报告内容）。

    使用两阶段标记方法，使得某个值中包含另一个键的占位符字符串
    （例如报告中包含字面文本 ``{research_topic}``）不会被意外替换。
    """
    import uuid as _uuid
    markers: dict[str, str] = {}
    for key, value in kwargs.items():
        marker = f"__FMT_{_uuid.uuid4().hex}__"
        template = template.replace("{" + key + "}", marker)
        markers[marker] = str(value)
    for marker, value in markers.items():
        template = template.replace(marker, value)
    return template


# ---------- Judge 类 ----------

class Judge:
    """调用 LLM 并传入评分提示词，解析结果返回的薄封装层。"""

    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or os.getenv("EVAL_MODEL", os.getenv("JUDGE_MODEL", ""))
        if not self.model_id:
            # 回退到可用模型列表中的最后一个模型
            from agent.configuration import get_judge_model_id
            self.model_id = get_judge_model_id()
        logger.info(f"Judge 已初始化，模型={self.model_id}")

    def _call(self, prompt: str) -> dict[str, Any]:
        """调用 LLM 并返回解析后的 JSON。"""
        import sys as _sys

        agent = Agent(model_id=self.model_id)
        last_raw = ""
        for attempt in range(3):
            try:
                raw = agent(prompt)
                last_raw = raw
                json_str = Post.extract_pattern(raw, pattern="json")
                result = json.loads(json_str)
                _sys.stderr.write(f"[Judge] 第 {attempt + 1} 次尝试成功，"
                                  f"解析出 {len(result)} 个顶层键\n")
                return result
            except Exception:
                _sys.stderr.write(
                    f"[Judge] 第 {attempt + 1} 次尝试失败\n"
                    f"  raw[:500]: {last_raw[:500]}\n"
                    f"  错误: {traceback.format_exc()}\n"
                )
                continue
        _sys.stderr.write("[Judge] 全部 3 次尝试均失败，返回 {}\n")
        return {}

    # -- 端到端 --

    def evaluate_report(
        self, *, research_topic: str, search_sources: str, report: str
    ) -> E2EScore:
        prompt = _safe_format(E2E_JUDGE_INSTRUCTIONS,
            research_topic=research_topic,
            search_sources=search_sources,
            report=report,
        )
        result = self._call(prompt)
        return E2EScore(**result) if result else None

    # -- 组件级 --

    def evaluate_plan(self, *, research_topic: str, plan: str) -> PlanScore:
        prompt = _safe_format(PLAN_JUDGE_INSTRUCTIONS,
            research_topic=research_topic,
            plan=plan[:8000],  # 为安全起见截断
        )
        result = self._call(prompt)
        return PlanScore(**result) if result else None

    def evaluate_queries(
        self, *, research_topic: str, queries: list[str], rationale: str
    ) -> QueryScore:
        prompt = _safe_format(QUERY_JUDGE_INSTRUCTIONS,
            research_topic=research_topic,
            queries=json.dumps(queries, ensure_ascii=False, indent=2),
            rationale=rationale,
        )
        result = self._call(prompt)
        return QueryScore(**result) if result else None

    def evaluate_summarization(
        self, *, search_query: str, raw_search_results: str, summary: str
    ) -> SummarizationScore:
        prompt = _safe_format(SUMMARIZATION_JUDGE_INSTRUCTIONS,
            search_query=search_query,
            raw_search_results=raw_search_results[:12000],
            summary=summary[:8000],
        )
        result = self._call(prompt)
        return SummarizationScore(**result) if result else None

    def evaluate_critique(
        self,
        *,
        research_topic: str,
        summaries: str,
        is_sufficient: bool,
        knowledge_gap: str,
        follow_up_queries: list[str],
    ) -> CritiqueScore:
        prompt = _safe_format(CRITIQUE_JUDGE_INSTRUCTIONS,
            research_topic=research_topic,
            summaries=summaries[:12000],
            is_sufficient=is_sufficient,
            knowledge_gap=knowledge_gap,
            follow_up_queries=json.dumps(follow_up_queries, ensure_ascii=False),
        )
        result = self._call(prompt)
        return CritiqueScore(**result) if result else None

    def evaluate_citations(self, *, sources: str, report: str) -> CitationScore:
        prompt = _safe_format(CITATION_JUDGE_INSTRUCTIONS,
            sources=sources[:12000],
            report=report[:12000],
        )
        result = self._call(prompt)
        return CitationScore(**result) if result else None

    def evaluate_plan_query_alignment(
        self, *, plan: str, queries: list[str]
    ) -> PlanQueryAlignmentScore:
        prompt = _safe_format(PLAN_QUERY_ALIGNMENT_JUDGE_INSTRUCTIONS,
            plan=plan[:8000],
            queries=json.dumps(queries, ensure_ascii=False, indent=2),
        )
        result = self._call(prompt)
        return PlanQueryAlignmentScore(**result) if result else None

    def evaluate_plan_reflection(
        self, *,
        original_plan: str,
        user_feedback: str,
        new_plan: str,
        actual_behavior: str,
        expected_intent: str,
    ) -> PlanReflectionScore:
        prompt = _safe_format(PLAN_REFLECTION_JUDGE_INSTRUCTIONS,
            original_plan=original_plan[:8000],
            user_feedback=user_feedback,
            new_plan=new_plan[:8000] if new_plan else "(未发生重新计划，系统判断用户已确认并直接继续执行)",
            actual_behavior=actual_behavior,
            expected_intent=expected_intent,
        )
        result = self._call(prompt)
        return PlanReflectionScore(**result) if result else None
