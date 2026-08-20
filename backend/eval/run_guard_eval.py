"""Score the fixed Writer-guard corpus. No external services are used."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from eval.output_contract import (
    load_guard_corpus,
    score_guard_case,
    summarize_guard_results,
)

DEFAULT_CORPUS = Path(__file__).with_name("guard_corpus.json")
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _portable_path(path: Path) -> str:
    """Keep committed eval evidence free of workstation-specific paths."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(BACKEND_ROOT))
    except ValueError:
        return str(path)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def format_guard_report(payload: dict) -> str:
    summary = payload["summary"]
    lines = [
        "# Writer 输出契约对抗评测",
        "",
        f"- 时间：`{payload['timestamp']}`",
        f"- 语料：`{payload['corpus']}`",
        f"- 样本数：{summary['n']}",
        "- 方法：用现有 `_polish_rejection_reason` / `_draft_rejection_reason` / "
        "`_unsupported_named_terms` 和确定性契约函数打分，不调用模型",
        "",
        "## 汇总",
        "",
        f"- 该拒召回率：`{_pct(summary['recall'])}`",
        f"- 不该拒误伤率：`{_pct(summary['false_positive_rate'])}`",
        f"- 判定准确率：`{_pct(summary['accuracy'])}`",
        "",
        "| 类别 | n | 召回率 | 误伤率 | 准确率 |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summary["by_category"]:
        lines.append(
            "| {category} | {n} | {recall} | {fpr} | {acc} |".format(
                category=row["category"],
                n=row["n"],
                recall=_pct(row["recall"]),
                fpr=_pct(row["false_positive_rate"]),
                acc=_pct(row["accuracy"]),
            )
        )
    lines.extend(["", "## 失败样本", ""])
    failures = summary.get("failures") or []
    if not failures:
        lines.append("无。")
    else:
        for item in failures:
            lines.append(
                f"- `{item['case_id']}` ({item['category']}/{item['check']}): "
                f"should_reject={item['should_reject']} rejected={item['rejected']} "
                f"reason={item['reason']!r}"
            )
    lines.extend(
        [
            "",
            "## 边界",
            "",
            "- `contract` 类样本测量终稿回放规则，不要求现有 polish 拒绝函数已经覆盖内部占位。",
            "- 召回率和误伤率按语料标签计算；标签与实现不一致时记为失败样本，不改标签凑数。",
            "- 历史 E2E 里的内部占位能被契约规则抓到，但当前 polish 拒绝函数并不会因此拒稿。这是已知缺口，不是语料造分。",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Writer guard corpus")
    parser.add_argument("--corpus", type=str, default=str(DEFAULT_CORPUS))
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--report", type=str, default=None)
    args = parser.parse_args(argv)

    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        print(f"missing corpus: {corpus_path}", file=sys.stderr)
        return 2

    cases = load_guard_corpus(corpus_path)
    results = [score_guard_case(case) for case in cases]
    summary = summarize_guard_results(results)
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "corpus": _portable_path(corpus_path),
        "summary": summary,
    }
    text = format_guard_report(payload)
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
