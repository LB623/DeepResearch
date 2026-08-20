from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import add_messages
from typing_extensions import Annotated


class OverallState(TypedDict):
    messages: Annotated[list, add_messages]
    plan: str
    plan_status: str
    plan_messages: Annotated[list, add_messages]
    search_query: Annotated[list, operator.add]
    generated_queries: Annotated[list, operator.add]
    executed_queries: Annotated[list, operator.add]
    skipped_duplicate_queries: Annotated[list, operator.add]
    web_search_result: Annotated[list, operator.add]
    sources_gathered: Annotated[list, operator.add]
    initial_search_query_count: int
    max_research_loops: int
    research_loop_count: int
    reasoning_model: str
    # WriterAgent 内部状态
    report_outline: str
    report_draft: str
    # ResearchAgent 循环控制
    is_sufficient: bool
    knowledge_gap: str
    follow_up_queries: Annotated[list, operator.add]
    number_of_ran_queries: int
    # Debate-loop state (Critic ↔ Writer revision cycle)
    critic_feedback: str
    critic_score: float
    ready_for_polish: bool
    revision_count: int
    max_revisions: int
    # KB lifecycle — set by Plan phase
    fresh_level: str     # "high" | "medium" | "low"
    # Per-run cost budget
    run_started_at: float
    web_search_call_count: Annotated[int, operator.add]
    omniseek_call_count: Annotated[int, operator.add]
    omniseek_failure_count: Annotated[int, operator.add]
    llm_token_count: Annotated[int, operator.add]
    no_progress_rounds: int
    evidence_fingerprint: str
    budget_stop_reason: str


class ReflectionState(TypedDict):
    is_sufficient: bool
    knowledge_gap: str
    follow_up_queries: Annotated[list, operator.add]
    research_loop_count: int
    number_of_ran_queries: int
    max_research_loops: int


class Query(TypedDict):
    query: str
    rationale: str


class QueryGenerationState(TypedDict):
    search_query: list[Query]
    generated_queries: list[str]
    executed_queries: list[str]
    skipped_duplicate_queries: list[str]
    web_search_call_count: int
    omniseek_call_count: int
    omniseek_failure_count: int
    llm_token_count: int
    budget_stop_reason: str


class WebSearchState(TypedDict):
    search_query: str
    id: int
    use_omniseek: bool


class FallbackSearchState(TypedDict):
    search_queries: list[str]
    start_id: int
    omniseek_remaining: int


class PlanState(TypedDict):
    plan: str


@dataclass(kw_only=True)
class SearchStateOutput:
    running_summary: str | None = field(default=None)  # Final report
