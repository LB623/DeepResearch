"""Offline schema and loader tests for the layered E2E fixed set."""

import json
from collections import Counter, defaultdict
from pathlib import Path

from eval.dataset import (
    CANONICAL_AS_OF,
    CANONICAL_DATASET_NAME,
    CANONICAL_E2E_SET,
    CANONICAL_FROZEN_AT,
    DIFFICULTIES,
    DOMAINS,
    EVALUATION_FOCUS,
    RISK_FLAGS,
    case_in_tier,
    load_basic_five,
    load_dataset,
    validate_canonical_dataset,
)
from eval.run_eval import load_test_set


def test_frozen_json_matches_builder():
    from eval._gen_e2e_set import build

    path = Path(__file__).parents[1] / "eval" / CANONICAL_E2E_SET
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == build()


def test_canonical_e2e_set_is_frozen_layered_and_unique():
    loaded = load_dataset(CANONICAL_E2E_SET, strict=True)
    data = {
        "name": loaded.meta.name,
        "frozen_at": loaded.meta.frozen_at,
        "as_of": loaded.meta.as_of,
        "topics": loaded.raw_topics,
    }
    validate_canonical_dataset(data)

    assert loaded.meta.name == CANONICAL_DATASET_NAME
    assert loaded.meta.frozen_at == CANONICAL_FROZEN_AT
    assert loaded.meta.as_of == CANONICAL_AS_OF
    assert [cfg.case_id for cfg in loaded.cases] == [f"e2e-{i:03d}" for i in range(1, 101)]
    assert len({cfg.topic for cfg in loaded.cases}) == 100
    assert Counter(cfg.tier for cfg in loaded.cases)["smoke"] == 5
    assert sum(1 for cfg in loaded.cases if case_in_tier(cfg.tier, "core")) == 30
    assert sum(1 for cfg in loaded.cases if case_in_tier(cfg.tier, "full")) == 100


def test_canonical_e2e_set_uses_small_controlled_vocabs():
    loaded = load_dataset(CANONICAL_E2E_SET, strict=True)
    domains = Counter(cfg.domain for cfg in loaded.cases)
    difficulties = Counter(cfg.difficulty for cfg in loaded.cases)

    assert set(domains) == set(DOMAINS)
    assert max(domains.values()) <= 20
    assert min(domains.values()) >= 8
    assert set(difficulties) <= set(DIFFICULTIES)
    assert 8 <= difficulties["easy"] <= 25
    assert 40 <= difficulties["medium"] <= 65
    assert 20 <= difficulties["hard"] <= 40

    core = [cfg for cfg in loaded.cases if case_in_tier(cfg.tier, "core")]
    core_focus = {flag for cfg in core for flag in cfg.evaluation_focus}
    assert core_focus == set(EVALUATION_FOCUS)
    assert all(set(cfg.evaluation_focus) <= set(EVALUATION_FOCUS) for cfg in loaded.cases)
    assert all(set(cfg.risk_flags) <= set(RISK_FLAGS) for cfg in loaded.cases)
    assert all(1 <= len(cfg.evaluation_focus) <= 3 for cfg in loaded.cases)
    assert all(cfg.as_of == CANONICAL_AS_OF for cfg in loaded.cases)
    assert all(cfg.required_aspects for cfg in loaded.cases)
    assert all(cfg.source_expectations.get("languages") for cfg in loaded.cases)


def test_difficulty_is_not_a_pure_function_of_query_and_loop_budget():
    loaded = load_dataset(CANONICAL_E2E_SET, strict=True)
    by_budget: dict[tuple[int, int], set[str]] = defaultdict(set)
    for cfg in loaded.cases:
        by_budget[(cfg.initial_search_query_count, cfg.max_research_loops)].add(
            cfg.difficulty
        )

    mixed = {key: values for key, values in by_budget.items() if len(values) > 1}
    hard_with_short_loops = [
        cfg.case_id
        for cfg in loaded.cases
        if cfg.difficulty == "hard" and cfg.max_research_loops <= 3
    ]
    medium_with_two_loops = [
        cfg.case_id
        for cfg in loaded.cases
        if cfg.difficulty == "medium" and cfg.max_research_loops == 2
    ]

    assert mixed
    assert hard_with_short_loops
    assert medium_with_two_loops


def test_canonical_set_preserves_historical_basic_five_topics_and_budgets():
    basic = load_basic_five()
    loaded = load_dataset(CANONICAL_E2E_SET, strict=True)

    assert [cfg.topic for cfg in loaded.cases[:5]] == [item["topic"] for item in basic]
    assert [cfg.initial_search_query_count for cfg in loaded.cases[:5]] == [
        item["initial_search_query_count"] for item in basic
    ]
    assert [cfg.max_research_loops for cfg in loaded.cases[:5]] == [
        item["max_research_loops"] for item in basic
    ]
    assert [cfg.case_id for cfg in loaded.cases[:5]] == [
        "e2e-001",
        "e2e-002",
        "e2e-003",
        "e2e-004",
        "e2e-005",
    ]
    assert all(cfg.tier == "smoke" for cfg in loaded.cases[:5])


def test_loader_and_run_eval_carry_case_metadata():
    loaded = load_dataset(CANONICAL_E2E_SET, tier="smoke")
    via_run_eval = load_test_set(CANONICAL_E2E_SET)

    assert [cfg.case_id for cfg in loaded.cases] == [f"e2e-{i:03d}" for i in range(1, 6)]
    assert via_run_eval[0].case_id == "e2e-001"
    assert via_run_eval[0].domain in DOMAINS
    assert via_run_eval[0].evaluation_focus
    assert via_run_eval[15].case_id == "e2e-016"
    assert "false_premise" in via_run_eval[15].evaluation_focus

    core = load_dataset(CANONICAL_E2E_SET, tier="core")
    assert len(core.cases) == 30
    sliced = load_dataset(CANONICAL_E2E_SET, tier="core", offset=10, limit=5)
    assert [cfg.case_id for cfg in sliced.cases] == [
        cfg.case_id for cfg in core.cases[10:15]
    ]
