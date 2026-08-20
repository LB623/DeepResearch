"""Offline aggregation tests. These never call paid eval services."""

import json

import pytest

from eval.aggregate import compare_ab, main, summarize_rows, wilson_interval


def _score(overall: float, *, hallucinated: bool = False, **dims: int) -> dict:
    payload = {
        "factual_accuracy": {"score": dims.get("factual_accuracy", 4)},
        "information_coverage": {"score": dims.get("information_coverage", 4)},
        "logical_structure": {"score": dims.get("logical_structure", 4)},
        "timeliness": {"score": dims.get("timeliness", 4)},
        "citation_quality": {"score": dims.get("citation_quality", 4)},
        "overall_score": overall,
        "hallucination_check": {
            "has_hallucinations": hallucinated,
            "details": "",
        },
    }
    return payload


def _row(
    case_id: str,
    topic: str,
    overall: float,
    *,
    run_id: str = "r1",
    tier: str = "core",
    domain: str = "ai_tech",
    difficulty: str = "medium",
    hallucinated: bool = False,
    error: str | None = None,
) -> dict:
    row = {
        "case_id": case_id,
        "topic": topic,
        "run_id": run_id,
        "tier": tier,
        "domain": domain,
        "difficulty": difficulty,
        "error": error,
        "score": None if error else _score(overall, hallucinated=hallucinated),
    }
    return row


def test_wilson_interval_is_wide_for_five_successes():
    interval = wilson_interval(0, 5)
    assert interval is not None
    assert interval[0] == 0.0
    assert interval[1] > 0.4


def test_summarize_rows_reports_mean_std_hallucinations_and_groups():
    rows = [
        _row("e2e-001", "t1", 4.0, tier="smoke", domain="ai_tech", difficulty="medium"),
        _row(
            "e2e-002",
            "t2",
            5.0,
            tier="smoke",
            domain="finance_macro",
            difficulty="easy",
            hallucinated=True,
        ),
        _row(
            "e2e-003",
            "t3",
            3.0,
            tier="core",
            domain="policy_law",
            difficulty="hard",
            error="boom",
        ),
        _row(
            "e2e-001",
            "t1",
            5.0,
            run_id="r2",
            tier="smoke",
            domain="ai_tech",
            difficulty="medium",
        ),
    ]

    summary = summarize_rows(rows)

    assert summary["n_results"] == 4
    assert summary["n_success"] == 3
    assert summary["n_error"] == 1
    assert summary["n_cases"] == 3
    assert summary["n_runs"] == 2
    assert summary["overall"]["mean"] == pytest.approx(14 / 3)
    assert summary["overall"]["std"] == pytest.approx(0.5773502691896257)
    assert summary["hallucination_count"] == 1
    assert summary["hallucination_n"] == 3
    assert summary["hallucination_rate"] == 1 / 3
    assert summary["groups"]["tier"]["smoke"]["n_success"] == 3
    assert any("小样本" in warning for warning in summary["warnings"])
    assert any("历史 smoke/5" in warning for warning in summary["warnings"])


def test_compare_ab_pairs_by_case_id_and_reports_win_rate():
    baseline = [
        _row("e2e-001", "t1", 4.0, run_id="b1"),
        _row("e2e-001", "t1", 5.0, run_id="b2"),
        _row("e2e-002", "t2", 4.0, run_id="b1", hallucinated=True),
        _row("e2e-003", "t3", 3.0, run_id="b1"),
    ]
    optimized = [
        _row("e2e-001", "t1", 5.0, run_id="o1"),
        _row("e2e-001", "t1", 5.0, run_id="o2"),
        _row("e2e-002", "t2", 3.0, run_id="o1"),
        _row("e2e-003", "t3", 3.0, run_id="o1"),
    ]

    comparison = compare_ab(baseline, optimized)
    by_id = {row["case_id"]: row for row in comparison["per_case"]}

    assert comparison["n_paired"] == 3
    assert comparison["wins"] == 1
    assert comparison["losses"] == 1
    assert comparison["ties"] == 1
    assert comparison["win_rate"] == 1 / 3
    assert by_id["e2e-001"]["delta"] == 0.5
    assert by_id["e2e-002"]["delta"] == -1.0
    assert by_id["e2e-003"]["delta"] == 0.0
    assert any("A/B 配对样本" in warning for warning in comparison["warnings"])


def test_aggregate_cli_merges_batches_and_historical_topic_only_files(tmp_path):
    batch_a = {
        "run_ids": ["batch-a"],
        "e2e_results": [
            _row("e2e-001", "alpha", 4.0, run_id="batch-a", tier="smoke"),
            _row("e2e-002", "beta", 5.0, run_id="batch-a", tier="smoke"),
        ],
    }
    batch_b = {
        "run_ids": ["batch-b"],
        "e2e_results": [
            _row("e2e-001", "alpha", 5.0, run_id="batch-b", tier="smoke"),
        ],
    }
    historical = {
        "timestamp": "2026-06-18",
        "e2e_results": [
            {
                "topic": "alpha",
                "score": _score(3.8, hallucinated=True),
                "error": None,
            }
        ],
    }
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_h = tmp_path / "hist.json"
    path_a.write_text(json.dumps(batch_a), encoding="utf-8")
    path_b.write_text(json.dumps(batch_b), encoding="utf-8")
    path_h.write_text(json.dumps(historical), encoding="utf-8")
    output = tmp_path / "summary.json"

    exit_code = main([str(path_a), str(path_b), "-o", str(output)])
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["n_results"] == 3
    assert payload["n_cases"] == 2
    assert payload["n_success"] == 3

    ab_output = tmp_path / "ab.json"
    exit_code = main(
        [
            "--baseline",
            str(path_h),
            "--optimized",
            str(path_a),
            "--output",
            str(ab_output),
        ]
    )
    ab_payload = json.loads(ab_output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert ab_payload["comparison"]["n_paired"] == 1
    assert ab_payload["comparison"]["per_case"][0]["topic"] == "alpha"
    assert ab_payload["comparison"]["per_case"][0]["delta"] == pytest.approx(0.2)
