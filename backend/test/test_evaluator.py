"""Regression tests for evaluation harness state/config propagation."""

import json

from langchain_core.messages import AIMessage

from eval import run_eval
from eval.evaluator import E2EResult, Evaluator, TopicCfg
from eval.judge import Judge


def test_evaluator_passes_topic_limits_into_research_state():
    evaluator = Evaluator()
    calls: list[tuple[dict, dict]] = []

    def fake_invoke(state: dict, config: dict) -> dict:
        calls.append((state, config))
        if len(calls) == 1:
            return {
                "plan": "# Plan",
                "plan_messages": [],
                "run_started_at": 123.0,
                "llm_token_count": 42,
                "web_search_call_count": 1,
                "no_progress_rounds": 0,
                "budget_stop_reason": "",
            }
        return {
            "messages": [AIMessage(content="# Report\n\n" + "complete " * 30)],
            "sources_gathered": [],
        }

    evaluator._invoke_graph = fake_invoke
    cfg = TopicCfg(
        topic="fixed limits",
        initial_search_query_count=1,
        max_research_loops=1,
    )

    try:
        evaluator._invoke_agent_with_feedback(cfg)

        research_state = calls[1][0]
        assert research_state["initial_search_query_count"] == 1
        assert research_state["max_research_loops"] == 1
        assert research_state["research_loop_count"] == 0
        assert research_state["run_started_at"] == 123.0
        assert research_state["llm_token_count"] == 42
        assert research_state["web_search_call_count"] == 1
    finally:
        evaluator.close()


def test_evaluator_preserves_latest_writer_draft_when_budget_stops():
    evaluator = Evaluator()
    calls = 0

    def fake_invoke(state: dict, config: dict) -> dict:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "plan": "# Plan\n\n" + "planning " * 30,
                "plan_messages": [],
            }
        return {
            "messages": [AIMessage(content="# Plan\n\n" + "planning " * 30)],
            "report_draft": "# Latest draft\n\n" + "evidence " * 30,
            "sources_gathered": [],
            "budget_stop_reason": "token_limit",
        }

    evaluator._invoke_graph = fake_invoke

    try:
        result = evaluator._invoke_agent_with_feedback(
            TopicCfg(topic="preserve partial report")
        )
    finally:
        evaluator.close()

    assert result["report"].startswith("# Latest draft")


def test_judge_retries_when_e2e_score_is_missing_required_field(monkeypatch):
    responses = [
        {
            "factual_accuracy": {"score": 4, "reason": "accurate"},
            "information_coverage": {"score": 4, "reason": "covered"},
            "logical_structure": {"score": 4, "reason": "clear"},
            "timeliness": {"score": 4, "reason": "current"},
            "citation_quality": {"score": 4, "reason": "cited"},
            "overall_score": 4.0,
            "overall_assessment": "good",
        },
        {
            "factual_accuracy": {"score": 4, "reason": "accurate"},
            "information_coverage": {"score": 4, "reason": "covered"},
            "logical_structure": {"score": 4, "reason": "clear"},
            "timeliness": {"score": 4, "reason": "current"},
            "citation_quality": {"score": 4, "reason": "cited"},
            "overall_score": 4.0,
            "overall_assessment": "good",
            "hallucination_check": {
                "has_hallucinations": False,
                "details": "",
            },
        },
    ]
    prompts: list[str] = []

    class FakeJudgeBoundary:
        def __init__(self, model_id=None):
            self.model_id = model_id

        def __call__(self, prompt: str) -> str:
            prompts.append(prompt)
            return f"```json\n{json.dumps(responses.pop(0))}\n```"

    monkeypatch.setattr("eval.judge.Agent", FakeJudgeBoundary)

    score = Judge(model_id="judge-test").evaluate_report(
        research_topic="topic",
        search_sources="[]",
        report="# report",
    )

    assert score.hallucination_check["has_hallucinations"] is False
    assert len(prompts) == 2
    assert "上一次输出未通过结构校验" in prompts[1]


def test_judge_exposes_provider_reported_token_usage(monkeypatch):
    payload = {
        "factual_accuracy": {"score": 4, "reason": "accurate"},
        "information_coverage": {"score": 4, "reason": "covered"},
        "logical_structure": {"score": 4, "reason": "clear"},
        "timeliness": {"score": 4, "reason": "current"},
        "citation_quality": {"score": 4, "reason": "cited"},
        "overall_score": 4.0,
        "overall_assessment": "good",
        "hallucination_check": {
            "has_hallucinations": False,
            "details": "",
        },
    }

    class FakeJudgeBoundary:
        def __init__(self, model_id=None):
            self.llm = type(
                "Usage",
                (),
                {"last_usage": {"total_tokens": 25}},
            )()

        def __call__(self, prompt: str) -> str:
            return f"```json\n{json.dumps(payload)}\n```"

    monkeypatch.setattr("eval.judge.Agent", FakeJudgeBoundary)
    judge = Judge(model_id="judge-test")

    judge.evaluate_report(
        research_topic="topic",
        search_sources="[]",
        report="# report",
    )

    assert judge.last_call_tokens == 25
    assert judge.total_tokens == 25


def test_evaluator_preserves_report_when_judge_scoring_fails():
    evaluator = Evaluator()
    evaluator._invoke_agent = lambda cfg: E2EResult(
        topic=cfg.topic,
        report="# Complete report",
        sources='[{"url":"https://example.com"}]',
    )

    class FailingJudge:
        def evaluate_report(self, **kwargs):
            raise ValueError("invalid judge schema")

    evaluator.judge = FailingJudge()

    try:
        result = evaluator.run_e2e([TopicCfg(topic="preserve artifacts")])[0]
    finally:
        evaluator.close()

    assert result.report == "# Complete report"
    assert result.sources == '[{"url":"https://example.com"}]'
    assert result.error == "ValueError: invalid judge schema"


def test_evaluator_reports_combined_agent_and_judge_tokens():
    evaluator = Evaluator()
    evaluator._invoke_agent = lambda cfg: E2EResult(
        topic=cfg.topic,
        report="# Complete report",
        sources="[]",
        llm_token_count=40,
    )

    class TokenJudge:
        total_tokens = 0

        def evaluate_report(self, **kwargs):
            self.total_tokens += 10
            return None

    evaluator.judge = TokenJudge()

    try:
        result = evaluator.run_e2e([TopicCfg(topic="combined budget")])[0]
    finally:
        evaluator.close()

    assert result.llm_token_count == 50
    assert result.judge_token_count == 10


def test_agent_result_carries_graph_budget_state():
    evaluator = Evaluator()
    evaluator._invoke_agent_with_feedback = lambda cfg: {
        "report": "# Complete report",
        "sources": "[]",
        "phase2_state": {
            "llm_token_count": 123,
            "budget_stop_reason": "token_limit",
        },
    }

    try:
        result = evaluator._invoke_agent(TopicCfg(topic="budget state"))
    finally:
        evaluator.close()

    assert result.llm_token_count == 123
    assert result.budget_stop_reason == "token_limit"


def test_evaluator_does_not_call_judge_after_agent_budget_stop():
    evaluator = Evaluator()
    evaluator._invoke_agent = lambda cfg: E2EResult(
        topic=cfg.topic,
        report="# Partial report",
        sources="[]",
        llm_token_count=50,
        budget_stop_reason="token_limit",
    )

    class ForbiddenJudge:
        total_tokens = 0

        def evaluate_report(self, **kwargs):
            raise AssertionError("Judge must not run after budget stop")

    evaluator.judge = ForbiddenJudge()

    try:
        result = evaluator.run_e2e([TopicCfg(topic="budget stop")])[0]
    finally:
        evaluator.close()

    assert result.score is None
    assert result.error == "Budget exhausted before Judge: token_limit"


def test_eval_cli_returns_nonzero_when_any_e2e_result_fails(tmp_path):
    class FailingEvaluator:
        def __init__(self, judge_model_id=None):
            self.judge_model_id = judge_model_id

        def run_e2e(self, cfgs):
            return [
                E2EResult(
                    topic=cfgs[0].topic,
                    report="# Preserved report",
                    error="JudgeError: invalid schema",
                )
            ]

        def close(self):
            return None

    output = tmp_path / "eval.json"
    exit_code = run_eval.main(
        [
            "--mode",
            "e2e",
            "--topic",
            "cli failure",
            "--output",
            str(output),
        ],
        evaluator_factory=FailingEvaluator,
    )

    assert exit_code == 1
    assert output.exists()
    assert "# Preserved report" in output.read_text(encoding="utf-8")
