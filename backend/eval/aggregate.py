"""Offline aggregation for E2E eval JSON.

This command does not call an LLM, web search, Milvus, or embedding service.
It only reads already-written eval reports.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCORE_DIMENSIONS = (
    "factual_accuracy",
    "information_coverage",
    "logical_structure",
    "timeliness",
    "citation_quality",
)

SMALL_N_CASES = 30
SMALL_N_GROUP = 5
Z_95 = 1.959963984540054


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def _case_key(row: dict[str, Any]) -> str:
    case_id = str(row.get("case_id") or "").strip()
    if case_id:
        return case_id
    return str(row.get("topic") or "").strip()


def _flatten_results(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path)
    rows: list[dict[str, Any]] = []
    fallback_run_id = ""
    run_ids = data.get("run_ids") or []
    if isinstance(run_ids, list) and len(run_ids) == 1:
        fallback_run_id = str(run_ids[0])
    elif not run_ids:
        fallback_run_id = path.stem

    for row in data.get("e2e_results") or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item["_source_file"] = str(path)
        if not item.get("run_id"):
            item["run_id"] = fallback_run_id
        if not item.get("case_id"):
            item["case_id"] = _case_key(item)
        rows.append(item)
    return rows


def _overall_score(row: dict[str, Any]) -> float | None:
    score = row.get("score") or {}
    if not isinstance(score, dict):
        return None
    value = score.get("overall_score")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _dimension_score(row: dict[str, Any], name: str) -> float | None:
    score = row.get("score") or {}
    if not isinstance(score, dict):
        return None
    bucket = score.get(name) or {}
    if isinstance(bucket, dict) and isinstance(bucket.get("score"), (int, float)):
        return float(bucket["score"])
    if isinstance(bucket, (int, float)):
        return float(bucket)
    return None


def _has_hallucination(row: dict[str, Any]) -> bool | None:
    score = row.get("score") or {}
    if not isinstance(score, dict):
        return None
    check = score.get("hallucination_check") or {}
    if not isinstance(check, dict) or "has_hallucinations" not in check:
        return None
    return bool(check.get("has_hallucinations"))


def _is_success(row: dict[str, Any]) -> bool:
    return not row.get("error") and _overall_score(row) is not None


def wilson_interval(k: int, n: int, z: float = Z_95) -> list[float] | None:
    if n <= 0:
        return None
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n) / denom
    return [max(0.0, center - margin), min(1.0, center + margin)]


def mean_std(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "std": None, "n": 0}
    mean = statistics.fmean(values)
    std = statistics.stdev(values) if len(values) >= 2 else 0.0
    return {"mean": mean, "std": std, "n": len(values)}


def _warnings_for(n_cases: int, n_scores: int, groups: dict[str, dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if n_scores < SMALL_N_CASES:
        warnings.append(
            f"小样本：成功评分数 n={n_scores} < {SMALL_N_CASES}，"
            "均值、幻觉率和胜率方差很大，不能外推到扩展集或产品总体。"
        )
    if n_cases <= 5:
        warnings.append(
            "当前结果至多覆盖历史 smoke/5 题规模；禁止改写成 0/50、0/100 "
            "或“扩展集幻觉率为 0”。"
        )
    for group_name, buckets in groups.items():
        for key, stats in buckets.items():
            n = int(stats.get("n") or 0)
            if 0 < n < SMALL_N_GROUP:
                warnings.append(
                    f"分组 {group_name}={key} 仅有 n={n} < {SMALL_N_GROUP}，"
                    "不要把该分层数字当作稳定结论。"
                )
    return warnings


def _group_stats(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = str(row.get(field) or "").strip() or "unknown"
        grouped[key].append(row)
    return {key: summarize_rows(group, include_groups=False) for key, group in sorted(grouped.items())}


def summarize_rows(rows: list[dict[str, Any]], *, include_groups: bool = True) -> dict[str, Any]:
    n_results = len(rows)
    n_error = sum(1 for row in rows if row.get("error"))
    scored = [row for row in rows if _is_success(row)]
    n_success = len(scored)
    overall_values = [_overall_score(row) for row in scored]
    overall_values = [value for value in overall_values if value is not None]
    overall = mean_std(overall_values)

    dimensions = {
        name: mean_std(
            [
                value
                for value in (_dimension_score(row, name) for row in scored)
                if value is not None
            ]
        )
        for name in SCORE_DIMENSIONS
    }

    hallu_flags = [_has_hallucination(row) for row in scored]
    hallu_known = [flag for flag in hallu_flags if flag is not None]
    hallu_count = sum(1 for flag in hallu_known if flag)
    hallu_n = len(hallu_known)
    hallu_rate = (hallu_count / hallu_n) if hallu_n else None

    unique_cases = sorted({_case_key(row) for row in rows if _case_key(row)})
    unique_runs = sorted({str(row.get("run_id") or "") for row in rows if row.get("run_id")})

    payload: dict[str, Any] = {
        "n_results": n_results,
        "n_success": n_success,
        "n_error": n_error,
        "n_cases": len(unique_cases),
        "n_runs": len(unique_runs),
        "run_ids": unique_runs,
        "overall": overall,
        "dimensions": dimensions,
        "hallucination_count": hallu_count,
        "hallucination_n": hallu_n,
        "hallucination_rate": hallu_rate,
        "hallucination_rate_ci95": wilson_interval(hallu_count, hallu_n) if hallu_n else None,
    }
    if include_groups:
        groups = {
            "tier": _group_stats(rows, "tier"),
            "domain": _group_stats(rows, "domain"),
            "difficulty": _group_stats(rows, "difficulty"),
        }
        payload["groups"] = groups
        payload["warnings"] = _warnings_for(len(unique_cases), n_success, groups)
        payload["case_ids"] = unique_cases
    return payload


def _per_case_mean(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = _case_key(row)
        if key:
            grouped[key].append(row)
    summary: dict[str, dict[str, Any]] = {}
    for key, group in grouped.items():
        scored = [row for row in group if _is_success(row)]
        scores = [_overall_score(row) for row in scored]
        scores = [value for value in scores if value is not None]
        hallu = [_has_hallucination(row) for row in scored]
        hallu_known = [flag for flag in hallu if flag is not None]
        topic = next((str(row.get("topic") or "") for row in group if row.get("topic")), "")
        summary[key] = {
            "case_id": key,
            "topic": topic,
            "n": len(scores),
            "mean": statistics.fmean(scores) if scores else None,
            "hallucination_any": any(hallu_known) if hallu_known else None,
            "tier": next((row.get("tier") or "" for row in group if row.get("tier")), ""),
            "domain": next((row.get("domain") or "" for row in group if row.get("domain")), ""),
            "difficulty": next(
                (row.get("difficulty") or "" for row in group if row.get("difficulty")),
                "",
            ),
        }
    return summary


def _match_case(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    left_id = str(left.get("case_id") or "").strip()
    right_id = str(right.get("case_id") or "").strip()
    if left_id and right_id and left_id == right_id:
        return True
    left_topic = str(left.get("topic") or "").strip()
    right_topic = str(right.get("topic") or "").strip()
    return bool(left_topic and right_topic and left_topic == right_topic)


def compare_ab(
    baseline_rows: list[dict[str, Any]],
    optimized_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline_cases = list(_per_case_mean(baseline_rows).values())
    optimized_cases = list(_per_case_mean(optimized_rows).values())
    used: set[int] = set()
    per_case: list[dict[str, Any]] = []
    wins = losses = ties = 0
    deltas: list[float] = []
    for left in baseline_cases:
        match_index = next(
            (
                index
                for index, right in enumerate(optimized_cases)
                if index not in used and _match_case(left, right)
            ),
            None,
        )
        if match_index is None:
            continue
        used.add(match_index)
        right = optimized_cases[match_index]
        if left["mean"] is None or right["mean"] is None:
            continue
        delta = right["mean"] - left["mean"]
        deltas.append(delta)
        if delta > 0:
            outcome = "win"
            wins += 1
        elif delta < 0:
            outcome = "loss"
            losses += 1
        else:
            outcome = "tie"
            ties += 1
        per_case.append(
            {
                "case_id": right["case_id"] or left["case_id"],
                "topic": right["topic"] or left["topic"],
                "tier": right["tier"] or left["tier"],
                "domain": right["domain"] or left["domain"],
                "difficulty": right["difficulty"] or left["difficulty"],
                "baseline": left["mean"],
                "optimized": right["mean"],
                "delta": delta,
                "outcome": outcome,
                "baseline_hallucination_any": left["hallucination_any"],
                "optimized_hallucination_any": right["hallucination_any"],
            }
        )
    n_paired = len(per_case)
    unpaired_baseline = [
        case["case_id"] or case["topic"]
        for case in baseline_cases
        if all(not _match_case(case, right) for right in optimized_cases)
    ]
    unpaired_optimized = [
        case["case_id"] or case["topic"]
        for index, case in enumerate(optimized_cases)
        if index not in used
    ]
    return {
        "n_paired": n_paired,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_rate": (wins / n_paired) if n_paired else None,
        "mean_delta": statistics.fmean(deltas) if deltas else None,
        "delta_std": statistics.stdev(deltas) if len(deltas) >= 2 else (0.0 if deltas else None),
        "per_case": per_case,
        "unpaired_baseline": unpaired_baseline,
        "unpaired_optimized": unpaired_optimized,
        "warnings": (
            [
                f"A/B 配对样本 n={n_paired} < {SMALL_N_CASES}，胜率和分数差不能外推到扩展集。"
            ]
            if n_paired < SMALL_N_CASES
            else []
        ),
    }


def aggregate_files(paths: list[Path]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(_flatten_results(path))
    summary = summarize_rows(rows)
    summary["files"] = [str(path) for path in paths]
    return summary


def format_summary(payload: dict[str, Any]) -> str:
    overall = payload.get("overall") or {}
    mean = overall.get("mean")
    std = overall.get("std")
    rate = payload.get("hallucination_rate")
    ci = payload.get("hallucination_rate_ci95")
    lines = [
        "E2E 离线聚合",
        f"- 文件数: {len(payload.get('files') or [])}",
        f"- 结果行: {payload.get('n_results')}  成功: {payload.get('n_success')}  "
        f"失败: {payload.get('n_error')}  唯一题目: {payload.get('n_cases')}",
        f"- 均分: {mean:.3f} ± {std:.3f}" if isinstance(mean, float) and isinstance(std, float) else "- 均分: n/a",
        (
            f"- 幻觉: {payload.get('hallucination_count')}/{payload.get('hallucination_n')}"
            + (f" ({rate:.1%})" if isinstance(rate, float) else "")
            + (f" CI95={ci[0]:.1%}–{ci[1]:.1%}" if ci else "")
        ),
    ]
    dimensions = payload.get("dimensions") or {}
    if dimensions:
        lines.append("- 维度均值:")
        for name in SCORE_DIMENSIONS:
            stats = dimensions.get(name) or {}
            value = stats.get("mean")
            if isinstance(value, float):
                lines.append(f"    {name}: {value:.3f}")
    for warning in payload.get("warnings") or []:
        lines.append(f"- 警告: {warning}")
    comparison = payload.get("comparison")
    if comparison:
        lines.append(
            "- A/B: "
            f"n_paired={comparison.get('n_paired')} "
            f"wins={comparison.get('wins')} "
            f"losses={comparison.get('losses')} "
            f"ties={comparison.get('ties')} "
            f"win_rate={comparison.get('win_rate')} "
            f"mean_delta={comparison.get('mean_delta')}"
        )
        for warning in comparison.get("warnings") or []:
            lines.append(f"- 警告: {warning}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="离线聚合 E2E 评测 JSON（不调用外部服务）",
    )
    parser.add_argument("files", nargs="*", help="一个或多个 E2E JSON 结果文件")
    parser.add_argument("--baseline", type=str, default=None, help="A/B 对照：baseline JSON")
    parser.add_argument("--optimized", type=str, default=None, help="A/B 对照：optimized JSON")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="保存聚合 JSON 的路径",
    )
    args = parser.parse_args(argv)

    if bool(args.baseline) != bool(args.optimized):
        parser.error("--baseline 与 --optimized 必须同时提供")
    paths = [Path(item) for item in args.files]
    if args.baseline and args.optimized:
        baseline_path = Path(args.baseline)
        optimized_path = Path(args.optimized)
        for path in (baseline_path, optimized_path, *paths):
            if not path.exists():
                parser.error(f"文件不存在：{path}")
        baseline_rows = _flatten_results(baseline_path)
        optimized_rows = _flatten_results(optimized_path)
        extra_rows: list[dict[str, Any]] = []
        for path in paths:
            extra_rows.extend(_flatten_results(path))
        payload = {
            "baseline": summarize_rows(baseline_rows),
            "optimized": summarize_rows(optimized_rows),
            "comparison": compare_ab(baseline_rows, optimized_rows),
            "files": [str(baseline_path), str(optimized_path), *[str(path) for path in paths]],
        }
        if extra_rows:
            payload["combined_extra"] = summarize_rows(extra_rows)
        payload["warnings"] = list(payload["baseline"].get("warnings") or []) + list(
            payload["optimized"].get("warnings") or []
        )
        text_source = {
            **payload["optimized"],
            "files": payload["files"],
            "warnings": payload["warnings"],
            "comparison": payload["comparison"],
        }
    else:
        if not paths:
            parser.error("请提供至少一个结果文件，或同时提供 --baseline 与 --optimized")
        for path in paths:
            if not path.exists():
                parser.error(f"文件不存在：{path}")
        payload = aggregate_files(paths)
        text_source = payload

    print(format_summary(text_source))
    if args.output:
        Path(args.output).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
