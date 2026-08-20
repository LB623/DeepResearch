"""Replay finished E2E reports against the deterministic output contract.

This command does not call an LLM, web search, Milvus, or Redis.
It only reads historical E2E JSON and applies local regular-expression checks.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from eval.output_contract import score_e2e_file, summarize_contract_scores

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _portable_path(path: Path) -> str:
    """Keep committed eval evidence free of workstation-specific paths."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(BACKEND_ROOT))
    except ValueError:
        return str(path)


def _default_run_paths() -> list[tuple[str, Path]]:
    return [
        ("baseline", BACKEND_ROOT / "eval_runs" / "e2e_baseline_basic5_v1.json"),
        ("guards_v3", BACKEND_ROOT / "eval_runs" / "e2e_guardfix_basic5_v3.json"),
    ]


def format_contract_report(payload: dict) -> str:
    lines = [
        "# 输出契约回放评测",
        "",
        f"- 时间：`{payload['timestamp']}`",
        "- 方法：对历史 E2E 终稿做确定性检查，不调用 Judge / 搜索 / 向量库",
        "- 指标：引用 URL 是否落在当次 `sources_gathered`；是否残留内部占位引用",
        "",
        "## 汇总",
        "",
        "| 变体 | n | 引用 URL 可追溯率 | 含未知 URL 的题数 | 含内部占位的题数 | 未知 URL 总数 | 内部占位总数 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for summary in payload["summaries"]:
        rate = summary["mean_grounded_url_rate"]
        rate_text = "n/a" if rate is None else f"{rate:.1%}"
        lines.append(
            "| {label} | {n} | {rate} | {unknown_topics} | {leftover_topics} | "
            "{unknown_total} | {leftover_total} |".format(
                label=summary["label"],
                n=summary["n"],
                rate=rate_text,
                unknown_topics=summary["topics_with_unknown_url"],
                leftover_topics=summary["topics_with_leftover"],
                unknown_total=summary["total_unknown_urls"],
                leftover_total=summary["total_leftovers"],
            )
        )
    lines.extend(["", "## 逐题", ""])
    for summary in payload["summaries"]:
        lines.append(f"### {summary['label']}")
        lines.append("")
        lines.append("| 主题 | 引用数 | 唯一 URL | 可追溯率 | 未知 URL | 内部占位 | 结论章节 |")
        lines.append("|---|---:|---:|---:|---:|---:|:---:|")
        for row in summary["per_topic"]:
            rate = row["grounded_url_rate"]
            rate_text = "n/a" if rate is None else f"{rate:.1%}"
            lines.append(
                "| {topic} | {cites} | {unique} | {rate} | {unknown} | {leftover} | {conclusion} |".format(
                    topic=(row["topic"] or "")[:40],
                    cites=row["citation_count"],
                    unique=row["unique_url_count"],
                    rate=rate_text,
                    unknown=row["unknown_url_count"],
                    leftover=row["leftover_count"],
                    conclusion="是" if row["has_conclusion"] else "否",
                )
            )
        lines.append("")
    lines.extend(
        [
            "## 边界",
            "",
            "- 可追溯只检查 URL 是否出现在当次来源列表，不判断段落是否被来源蕴含。",
            "- 内部占位覆盖 `[ID 0-0]`、`[ID/3-1]`、`[来源id/3-1]`、`[材料-02]` 和未替换的 `search.com/id/...`。",
            "- 该回放使用既有评测产物，不证明新一次线上运行的质量。",
            "",
            "## 结论",
            "",
            "- 这套尺测的是终稿能不能回源，不是 Judge 均分。",
            "- 在同一份 5 题历史产物上，护栏 v3 的引用可追溯率低于 baseline，内部占位也更多。",
            "- 因此不能把幻觉题数下降写成“报告质量提升”；输出契约上的回退必须单独报告。",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay E2E reports against the output contract")
    parser.add_argument(
        "--input",
        action="append",
        nargs=2,
        metavar=("LABEL", "PATH"),
        help="Label and path of an e2e JSON report. Repeatable.",
    )
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--report", type=str, default=None)
    args = parser.parse_args(argv)

    pairs = args.input or []
    labeled_paths = [
        (label, Path(path)) for label, path in pairs
    ] or _default_run_paths()

    summaries = []
    for label, path in labeled_paths:
        if not path.exists():
            print(f"missing input: {path}", file=sys.stderr)
            return 2
        summaries.append(summarize_contract_scores(label, score_e2e_file(path)))

    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "inputs": [
            {"label": label, "path": _portable_path(path)}
            for label, path in labeled_paths
        ],
        "summaries": summaries,
    }
    text = format_contract_report(payload)
    print(text)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
