"""Deterministic output-contract and Writer-guard corpus tests."""

import json
import os
from pathlib import Path

import pytest

from eval.output_contract import (
    find_internal_leftovers,
    load_guard_corpus,
    score_e2e_file,
    score_guard_case,
    score_report_contract,
    summarize_guard_results,
)
from eval.run_groundedness import main as groundedness_main
from eval.run_guard_eval import main as guard_eval_main

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = BACKEND_ROOT / "eval" / "guard_corpus.json"
BASELINE_E2E = BACKEND_ROOT / "eval_runs" / "e2e_baseline_basic5_v1.json"
GUARDS_V3_E2E = BACKEND_ROOT / "eval_runs" / "e2e_guardfix_basic5_v3.json"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("安全修复时间缩短[ID 0-0]。", ["[ID 0-0]"]),
        ("工厂数量上升[来源id/3-1]。", ["[来源id/3-1]"]),
        ("审批仍未落地[ID/3-2]。", ["[ID/3-2]"]),
        ("见[材料-02]继续分析。", ["[材料-02]"]),
        ("未替换 https://search.com/id/0-0 链接。", ["https://search.com/id/0-0"]),
        ("正常引用[央行报告](https://pbc.gov.cn/a)不应命中。", []),
    ],
)
def test_internal_leftover_patterns(text: str, expected: list[str]) -> None:
    assert find_internal_leftovers(text) == expected


def test_grounded_url_rate_ignores_urls_present_in_sources() -> None:
    report = (
        "# Report\n\n见[真源](https://real.example/a)"
        "和[伪造](https://fake.example/b)。"
    )
    score = score_report_contract(
        report,
        [{"value": "https://real.example/a", "short_url": "https://search.com/id/0-0"}],
        topic="demo",
    )

    assert score.citation_count == 2
    assert score.unique_url_count == 2
    assert score.unknown_urls == ["https://fake.example/b"]
    assert score.grounded_url_rate == pytest.approx(0.5)


def test_guard_corpus_has_stable_coverage() -> None:
    cases = load_guard_corpus(CORPUS_PATH)
    ids = [case["id"] for case in cases]
    categories = {case["category"] for case in cases}

    assert len(cases) >= 36
    assert len(ids) == len(set(ids))
    assert {
        "truncation",
        "missing_heading",
        "unknown_url",
        "new_named_term",
        "empty_or_fence",
        "missing_outline_section",
        "unsupported_entity",
        "internal_leftover",
        "valid_control",
    }.issubset(categories)
    assert any(not case["should_reject"] for case in cases)
    assert any(case["check"] == "contract" for case in cases)


def test_guard_corpus_matches_current_writer_and_contract_rules() -> None:
    cases = load_guard_corpus(CORPUS_PATH)
    results = [score_guard_case(case) for case in cases]
    summary = summarize_guard_results(results)

    assert summary["accuracy"] == 1.0
    assert summary["false_positive_rate"] == 0.0
    assert summary["recall"] == 1.0
    assert summary["failures"] == []


def test_guard_scoring_never_inherits_external_checkpoint_backend(monkeypatch) -> None:
    monkeypatch.setenv("CHECKPOINT_BACKEND", "redis")
    case = load_guard_corpus(CORPUS_PATH)[0]

    score_guard_case(case)

    assert os.environ["CHECKPOINT_BACKEND"] == "redis"


def test_historical_e2e_replay_keeps_known_contract_gap() -> None:
    baseline = score_e2e_file(BASELINE_E2E)
    guards_v3 = score_e2e_file(GUARDS_V3_E2E)

    assert len(baseline) == 5
    assert len(guards_v3) == 5
    assert all(item.unknown_url_count == 0 for item in baseline)
    assert all(item.leftover_count == 0 for item in baseline)
    assert sum(item.leftover_count for item in guards_v3) > 0
    assert sum(item.unknown_url_count for item in guards_v3) > 0


def test_offline_eval_outputs_use_repository_relative_paths(tmp_path) -> None:
    guard_output = tmp_path / "guard.json"
    grounded_output = tmp_path / "grounded.json"

    assert guard_eval_main(["--output", str(guard_output)]) == 0
    assert groundedness_main(["--output", str(grounded_output)]) == 0

    guard_payload = json.loads(guard_output.read_text(encoding="utf-8"))
    grounded_payload = json.loads(grounded_output.read_text(encoding="utf-8"))
    recorded_paths = [guard_payload["corpus"]] + [
        item["path"] for item in grounded_payload["inputs"]
    ]

    assert recorded_paths == [
        "eval/guard_corpus.json",
        "eval_runs/e2e_baseline_basic5_v1.json",
        "eval_runs/e2e_guardfix_basic5_v3.json",
    ]
    assert all(not path.startswith("/") for path in recorded_paths)
