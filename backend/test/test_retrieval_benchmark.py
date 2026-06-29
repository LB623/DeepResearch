"""Tests for the deterministic retrieval benchmark metrics."""

import pytest

from eval.run_retrieval_benchmark import (
    RetrievalCase,
    _case_metrics,
    build_fixed_set,
)


def test_fixed_set_has_eight_queries_and_unique_relevance_labels():
    facts, cases = build_fixed_set()

    assert len(facts) == 48
    assert len(cases) == 8
    assert all(len(case.relevant) == 3 for case in cases)


def test_case_metrics_penalize_duplicate_relevant_hit():
    case = RetrievalCase(query="q", relevant={"fact-a": 3, "fact-b": 2})
    hits = [
        {"fact": "fact-a"},
        {"fact": "fact-a"},
        {"fact": "fact-b"},
    ]

    metrics = _case_metrics(case, hits, top_k=3)

    assert metrics["precision_at_k"] == pytest.approx(2 / 3)
    assert metrics["recall_at_k"] == 1.0
    assert metrics["duplicate_rate"] == pytest.approx(1 / 3)
    assert metrics["ndcg_at_k"] < 1.0
