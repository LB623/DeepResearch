"""Tests for the deterministic retrieval benchmark metrics."""

import pytest

from eval.retrieval_dataset import DATASET_VERSION, dataset_hash
from eval.run_retrieval_benchmark import (
    RetrievalCase,
    _bootstrap_delta,
    _case_metrics,
    build_fixed_set,
)


def test_fixed_set_has_frozen_scale_and_balanced_splits():
    facts, cases = build_fixed_set(now=1_800_000_000)

    assert len(facts) == 1_000
    assert len(cases) == 100
    assert sum(case.split == "dev" for case in cases) == 30
    assert sum(case.split == "test" for case in cases) == 70
    assert all(len(case.relevant) == 5 for case in cases)

    domains = {case.domain for case in cases}
    assert domains == {
        "historical",
        "market_data",
        "product_info",
        "strategy",
        "technology",
    }
    assert all(sum(case.domain == domain for case in cases) == 20 for domain in domains)


def test_fixed_set_hash_excludes_materialized_timestamps():
    first_facts, first_cases = build_fixed_set(now=1_800_000_000)
    second_facts, second_cases = build_fixed_set(now=1_900_000_000)

    assert DATASET_VERSION == "retrieval-controlled-v2"
    assert dataset_hash(first_facts, first_cases) == dataset_hash(
        second_facts, second_cases
    )


def test_fixed_set_uses_unique_ids_and_expected_challenge_roles():
    facts, _ = build_fixed_set(now=1_800_000_000)

    assert len({fact["fact_id"] for fact in facts}) == 1_000
    assert len({fact["source_url"] for fact in facts}) == 1_000
    assert sum("duplicate-exact" in fact["fact_id"] for fact in facts) == 100
    assert sum("duplicate-format" in fact["fact_id"] for fact in facts) == 100
    assert sum("-stale" in fact["fact_id"] for fact in facts) == 100
    assert sum("-conflict" in fact["fact_id"] for fact in facts) == 100
    assert sum("-neighbor" in fact["fact_id"] for fact in facts) == 100


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


def test_paired_bootstrap_delta_is_deterministic_and_paired():
    baseline = [{"ndcg_at_k": value} for value in (0.1, 0.3, 0.5, 0.7)]
    optimized = [{"ndcg_at_k": value + 0.2} for value in (0.1, 0.3, 0.5, 0.7)]

    first = _bootstrap_delta(
        baseline,
        optimized,
        metric="ndcg_at_k",
        samples=500,
        seed=42,
    )
    second = _bootstrap_delta(
        baseline,
        optimized,
        metric="ndcg_at_k",
        samples=500,
        seed=42,
    )

    assert first == second
    assert first[0] == pytest.approx(0.2)
    assert first[1] == pytest.approx(0.2)
