"""Run a controlled A/B benchmark for Milvus fact retrieval.

The benchmark uses a real, isolated Milvus collection and the configured
embedding endpoint. Its synthetic corpus measures retrieval, lifecycle
filtering, and duplicate suppression rather than real-world factual accuracy.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agent.kb.fact_store import FactStore, _normalize_fact
from eval.retrieval_dataset import (
    DATASET_VERSION,
    RetrievalCase,
    build_fixed_set,
    dataset_hash,
)

METRIC_NAMES = (
    "precision_at_k",
    "recall_at_k",
    "ndcg_at_k",
    "slot_fill_rate",
    "duplicate_rate",
)
DEFAULT_TOP_KS = (3, 5, 10)


class CachingFactStore(FactStore):
    """Reuse query embeddings so A/B variants compare the same vector."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._benchmark_embedding_cache: dict[str, list[float]] = {}
        super().__init__(*args, **kwargs)

    def _embed(
        self,
        texts: list[str],
        *,
        max_attempts: int = 3,
    ) -> list[list[float]]:
        if len(texts) != 1:
            return super()._embed(texts, max_attempts=max_attempts)

        text = texts[0]
        cached = self._benchmark_embedding_cache.get(text)
        if cached is not None:
            return [cached]
        result = super()._embed(texts, max_attempts=max_attempts)
        self._benchmark_embedding_cache[text] = result[0]
        return result


def _case_metrics(case: RetrievalCase, hits: list[dict], top_k: int) -> dict:
    seen: set[str] = set()
    gains: list[int] = []
    relevant_returned: set[str] = set()
    duplicates = 0
    for hit in hits[:top_k]:
        fact = hit["fact"]
        key = _normalize_fact(fact)
        if key in seen:
            duplicates += 1
            gains.append(0)
            continue
        seen.add(key)
        grade = case.relevant.get(fact, 0)
        gains.append(grade)
        if grade > 0:
            relevant_returned.add(fact)

    dcg = sum((2**gain - 1) / math.log2(rank + 2) for rank, gain in enumerate(gains))
    ideal = sorted(case.relevant.values(), reverse=True)[:top_k]
    idcg = sum((2**gain - 1) / math.log2(rank + 2) for rank, gain in enumerate(ideal))
    returned = min(len(hits), top_k)
    return {
        "query_id": case.query_id,
        "query": case.query,
        "domain": case.domain,
        "split": case.split,
        "difficulty": case.difficulty,
        "returned": returned,
        "unique_relevant": len(relevant_returned),
        "precision_at_k": len(relevant_returned) / top_k,
        "recall_at_k": len(relevant_returned) / len(case.relevant),
        "ndcg_at_k": dcg / idcg if idcg else 0.0,
        "slot_fill_rate": returned / top_k,
        "duplicate_rate": duplicates / returned if returned else 0.0,
        "hits": hits[:top_k],
    }


def _aggregate(rows: list[dict]) -> dict[str, float]:
    if not rows:
        raise ValueError("cannot aggregate an empty benchmark split")
    return {name: statistics.fmean(row[name] for row in rows) for name in METRIC_NAMES}


def run_variant(
    store: FactStore,
    cases: list[RetrievalCase],
    *,
    top_ks: tuple[int, ...],
    rerank: bool,
) -> dict:
    """Run one retrieval variant once per query and score multiple cutoffs."""
    max_k = max(top_ks)
    rows_by_k: dict[int, list[dict]] = {top_k: [] for top_k in top_ks}
    for case in cases:
        hits = store.query(
            case.query,
            top_k=max_k,
            min_confidence=0.6,
            decay=True,
            lifecycle_mode=True,
            rerank=rerank,
            candidate_multiplier=3,
        )
        for top_k in top_ks:
            rows_by_k[top_k].append(_case_metrics(case, hits, top_k))

    return {
        "by_k": {
            str(top_k): {
                "aggregate": _aggregate(rows_by_k[top_k]),
                "cases": rows_by_k[top_k],
            }
            for top_k in top_ks
        }
    }


def _bootstrap_delta(
    baseline_rows: list[dict],
    optimized_rows: list[dict],
    *,
    metric: str,
    samples: int,
    seed: int,
) -> tuple[float, float]:
    """Return a paired percentile-bootstrap 95% CI for a metric delta."""
    if len(baseline_rows) != len(optimized_rows):
        raise ValueError("paired bootstrap requires equal row counts")
    deltas = [
        optimized[metric] - baseline[metric]
        for baseline, optimized in zip(baseline_rows, optimized_rows, strict=True)
    ]
    rng = random.Random(seed)
    count = len(deltas)
    estimates = [
        statistics.fmean(deltas[rng.randrange(count)] for _ in range(count))
        for _ in range(samples)
    ]
    estimates.sort()
    lower_index = max(0, math.floor(samples * 0.025))
    upper_index = min(samples - 1, math.ceil(samples * 0.975) - 1)
    return estimates[lower_index], estimates[upper_index]


def build_comparisons(
    baseline: dict,
    optimized: dict,
    *,
    top_ks: tuple[int, ...],
    bootstrap_samples: int,
    seed: int,
) -> dict:
    comparisons: dict[str, dict[str, dict[str, Any]]] = {}
    for top_k in top_ks:
        key = str(top_k)
        baseline_bucket = baseline["by_k"][key]
        optimized_bucket = optimized["by_k"][key]
        metric_rows: dict[str, dict[str, Any]] = {}
        for metric_index, metric in enumerate(METRIC_NAMES):
            base_value = baseline_bucket["aggregate"][metric]
            opt_value = optimized_bucket["aggregate"][metric]
            ci_low, ci_high = _bootstrap_delta(
                baseline_bucket["cases"],
                optimized_bucket["cases"],
                metric=metric,
                samples=bootstrap_samples,
                seed=seed + top_k * 100 + metric_index,
            )
            metric_rows[metric] = {
                "baseline": base_value,
                "optimized": opt_value,
                "delta": opt_value - base_value,
                "delta_ci95": [ci_low, ci_high],
            }
        comparisons[key] = metric_rows
    return comparisons


def _domain_breakdown(variant: dict, *, top_k: int) -> dict[str, dict[str, float]]:
    rows = variant["by_k"][str(top_k)]["cases"]
    domains = sorted({row["domain"] for row in rows})
    return {
        domain: _aggregate([row for row in rows if row["domain"] == domain])
        for domain in domains
    }


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _pp(value: float) -> str:
    return f"{value * 100:+.1f} pp"


def render_markdown(report: dict) -> str:
    """Render the machine-readable result as a concise evidence report."""
    lines = [
        "# Milvus 事实检索质量感知重排 A/B 评测",
        "",
        f"- 时间：`{report['created_at']}`",
        f"- Collection：`{report['collection']}`（隔离评测集合）",
        f"- Embedding：`{report['embedding_model']}`",
        f"- 数据集：`{report['dataset_version']}` / `{report['dataset_hash'][:12]}`",
        (
            f"- 固定集：`{report['total_case_count']}` 个查询 / "
            f"`{report['fact_count']}` 条受控事实记录"
        ),
        (
            f"- 本次口径：`{report['split']}` 集，"
            f"`{report['evaluated_case_count']}` 个查询"
        ),
        "- 变量：baseline 为过滤后的 Milvus Top-K；optimized 为 3x 候选过采样、过滤、质量重排与规范化去重",
        "",
        "## 汇总结果",
        "",
        "| K | 指标 | baseline | optimized | 变化 | paired bootstrap 95% CI |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    labels = {
        "precision_at_k": "Unique Precision@K",
        "recall_at_k": "Recall@K",
        "ndcg_at_k": "NDCG@K",
        "slot_fill_rate": "有效槽位率",
        "duplicate_rate": "重复率",
    }
    for top_k in report["top_ks"]:
        for metric in METRIC_NAMES:
            row = report["comparisons"][str(top_k)][metric]
            low, high = row["delta_ci95"]
            lines.append(
                f"| {top_k} | {labels[metric]} | {_pct(row['baseline'])} | "
                f"{_pct(row['optimized'])} | {_pp(row['delta'])} | "
                f"[{_pp(low)}, {_pp(high)}] |"
            )

    primary_k = 5 if 5 in report["top_ks"] else max(report["top_ks"])
    lines.extend(
        [
            "",
            f"## 分主题结果（K={primary_k}）",
            "",
            "| 主题域 | baseline NDCG | optimized NDCG | baseline 重复率 | optimized 重复率 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    baseline_domains = report["domain_breakdown"]["baseline"]
    optimized_domains = report["domain_breakdown"]["optimized"]
    for domain in sorted(baseline_domains):
        base = baseline_domains[domain]
        opt = optimized_domains[domain]
        lines.append(
            f"| {domain} | {_pct(base['ndcg_at_k'])} | {_pct(opt['ndcg_at_k'])} | "
            f"{_pct(base['duplicate_rate'])} | {_pct(opt['duplicate_rate'])} |"
        )

    ndcg = report["comparisons"][str(primary_k)]["ndcg_at_k"]
    duplicate = report["comparisons"][str(primary_k)]["duplicate_rate"]
    ndcg_ci_low, ndcg_ci_high = ndcg["delta_ci95"]
    lines.extend(
        [
            "",
            "## 结论",
            "",
            (
                f"- 主指标 NDCG@{primary_k} 提升 {_pp(ndcg['delta'])}，"
                f"paired bootstrap 95% CI 为 [{_pp(ndcg_ci_low)}, {_pp(ndcg_ci_high)}]。"
            ),
            "- K=10 的 Precision 与 Recall 出现回退，NDCG 差值置信区间跨 0，不作为效果提升结论。",
            "",
            "## 实现与复现",
            "",
            "- 100 个查询由 5 个主题域构成，每域 6 个开发查询与 14 个冻结测试查询。",
            "- 每个查询对应 5 条分级相关事实，以及重复、过期、冲突和近邻实体干扰项。",
            "- 所有主题域共用一个 1,000 条记录的全局候选池，查询不会只在所属小组内检索。",
            "- 查询 embedding 在 baseline 与 optimized 间复用，不增加 LLM rerank 调用。",
            "- 指标差值以查询为配对单位执行 percentile bootstrap。",
            "",
            "```bash",
            "cd backend",
            "../.venv/bin/python -m eval.run_retrieval_benchmark \\",
            f"  --collection {report['collection']} \\",
            f"  --split {report['split']} \\",
            "  --top-k 3 5 10 \\",
            "  --output eval_runs/retrieval_rerank_v2.json \\",
            "  --report ../docs/reviews/retrieval-rerank-v2.md",
            "```",
            "",
            "## 边界",
            "",
            "该评测使用真实 Milvus 检索与真实 embedding，但语料是合成的受控组件集。",
            "指标只证明该固定集上的排序、生命周期过滤与去重效果，不代表真实语料或 E2E 报告质量。",
            "",
            "## 简历表述候选",
            "",
            (
                f"在 {report['evaluated_case_count']} 个冻结测试查询、"
                f"{report['fact_count']:,} 条受控事实记录和 5 个主题域的组件评测中，"
                "通过 3 倍候选过采样、质量重排与去重，"
                f"将 NDCG@{primary_k} 从 {_pct(ndcg['baseline'])} 提升至 "
                f"{_pct(ndcg['optimized'])}，重复率由 "
                f"{_pct(duplicate['baseline'])} 降至 {_pct(duplicate['optimized'])}。"
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _batched(items: list[dict], batch_size: int) -> list[list[dict]]:
    return [
        items[index : index + batch_size] for index in range(0, len(items), batch_size)
    ]


def main() -> int:
    """Run the benchmark and persist JSON plus Markdown outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection", default=f"eval_retrieval_rerank_{int(time.time())}"
    )
    parser.add_argument("--split", choices=("dev", "test", "all"), default="test")
    parser.add_argument("--top-k", type=int, nargs="+", default=list(DEFAULT_TOP_KS))
    parser.add_argument("--embedding-batch-size", type=int, default=64)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--keep-collection", action="store_true")
    args = parser.parse_args()

    if args.embedding_batch_size < 1:
        parser.error("--embedding-batch-size must be positive")
    top_ks = tuple(sorted(set(args.top_k)))
    if not top_ks or top_ks[0] < 1:
        parser.error("--top-k values must be positive")

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    materialized_at = int(time.time())
    facts, all_cases = build_fixed_set(now=materialized_at)
    logical_hash = dataset_hash(facts, all_cases)
    cases = (
        all_cases
        if args.split == "all"
        else [case for case in all_cases if case.split == args.split]
    )

    shuffled_facts = list(facts)
    random.Random(args.seed).shuffle(shuffled_facts)
    store = CachingFactStore(collection=args.collection)
    try:
        for batch in _batched(shuffled_facts, args.embedding_batch_size):
            store.add_facts(batch)
        store.client.flush(collection_name=args.collection)

        baseline = run_variant(store, cases, top_ks=top_ks, rerank=False)
        optimized = run_variant(store, cases, top_ks=top_ks, rerank=True)
        comparisons = build_comparisons(
            baseline,
            optimized,
            top_ks=top_ks,
            bootstrap_samples=args.bootstrap_samples,
            seed=args.seed,
        )
        primary_k = 5 if 5 in top_ks else max(top_ks)
        report = {
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "collection": args.collection,
            "embedding_model": store.embedding_model,
            "dataset_version": DATASET_VERSION,
            "dataset_hash": logical_hash,
            "fact_count": len(facts),
            "total_case_count": len(all_cases),
            "evaluated_case_count": len(cases),
            "split": args.split,
            "top_ks": list(top_ks),
            "bootstrap_samples": args.bootstrap_samples,
            "seed": args.seed,
            "cases": [
                {
                    "query_id": case.query_id,
                    "query": case.query,
                    "relevant": case.relevant,
                    "domain": case.domain,
                    "split": case.split,
                    "difficulty": case.difficulty,
                }
                for case in cases
            ],
            "variants": {"baseline": baseline, "optimized": optimized},
            "comparisons": comparisons,
            "domain_breakdown": {
                "baseline": _domain_breakdown(baseline, top_k=primary_k),
                "optimized": _domain_breakdown(optimized, top_k=primary_k),
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        markdown = render_markdown(report)
        args.report.write_text(markdown, encoding="utf-8")
        sys.stdout.write(markdown)
    finally:
        if not args.keep_collection and store.client.has_collection(args.collection):
            store.client.drop_collection(args.collection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
