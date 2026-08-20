#!/usr/bin/env python
"""DeepResearch Agent 评估框架的 CLI 入口。

用法:
  # 在所有测试主题上运行端到端评估
  python -m eval.run_eval --mode e2e

  # 对单个主题进行端到端评估
  python -m eval.run_eval --mode e2e --topic "你的研究主题"

  # 组件级评估
  python -m eval.run_eval --mode comp

  # 两种模式都运行
  python -m eval.run_eval --mode all

  # 指定 judge 模型
  python -m eval.run_eval --mode e2e --judge-model qwen3.7-max

  # 输出到文件
  python -m eval.run_eval --mode all --output eval_results.json
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime
from pathlib import Path

from eval.dataset import DatasetMeta, load_dataset, with_runtime_overrides
from eval.evaluator import (
    EvalReport,
    Evaluator,
    TopicCfg,
    apply_cfg_metadata,
    format_eval_report,
    save_eval_report,
)


def load_test_set(path: str = "test_set.json") -> list[TopicCfg]:
    """从 JSON 文件加载测试主题，保留 case_id 等数据集元数据。

    每个主题可以指定可选的 ``initial_search_query_count`` 和
    ``max_research_loops`` 字段；如果未提供，则使用默认值（2 / 2）。
    """
    try:
        return load_dataset(path, strict=False).cases
    except FileNotFoundError:
        full_path = Path(__file__).parent / path
        print(f"测试集未找到：{full_path}，使用默认主题。")
        return [
            TopicCfg(topic="2024-2025年全球AI编程助手市场的主要玩家和竞争格局分析"),
            TopicCfg(topic="2025年人民币汇率走势分析及主要影响因素"),
        ]


def main(argv=None, evaluator_factory=Evaluator) -> int:
    parser = argparse.ArgumentParser(
        description="DeepResearch Agent 评估运行器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["e2e", "comp", "all"],
        default="e2e",
        help="评估模式：e2e（端到端）、comp（组件级）、all（两者都运行）",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="要评估的单个研究主题（覆盖测试集）",
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default=None,
        help="Judge LLM 的模型 ID（默认使用环境变量 EVAL_MODEL 或最后一个可用模型）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="保存完整 JSON 评估报告的路径",
    )
    parser.add_argument(
        "--test-set",
        type=str,
        default="test_set.json",
        help="测试集 JSON 文件的路径（相对于 eval/ 目录）",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="跳过测试集前 N 个主题，便于分批运行（默认 0）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多运行 N 个主题，便于控制 E2E 评测成本",
    )
    parser.add_argument(
        "--tier",
        type=str,
        default=None,
        choices=["smoke", "core", "full"],
        help="按嵌套分层筛选：smoke⊂core⊂full（在 offset/limit 之前应用）",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="重复运行次数；每次使用独立 run_id，仍按 case_id 聚合",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="运行 ID 前缀；重复运行时自动追加 -r1/-r2",
    )
    parser.add_argument(
        "--initial-queries",
        type=int,
        default=None,
        help="覆盖所有主题的 initial_search_query_count",
    )
    parser.add_argument(
        "--max-loops",
        type=int,
        default=None,
        help="覆盖所有主题的 max_research_loops",
    )
    parser.add_argument(
        "--feedback",
        type=str,
        default=None,
        help="模拟用户在计划确认阶段的反馈（仅用于单主题模式）",
    )
    parser.add_argument(
        "--expected-intent",
        type=str,
        default=None,
        choices=["proceed", "replan"],
        help="预期系统行为：proceed（确认并继续）或 replan（修改计划）",
    )

    args = parser.parse_args(argv)

    if args.offset < 0:
        parser.error("--offset 必须大于或等于 0")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit 必须大于 0")
    if args.repeat < 1:
        parser.error("--repeat 必须大于或等于 1")

    meta = DatasetMeta()
    if args.topic:
        cfgs = [TopicCfg(
            topic=args.topic,
            user_feedback=args.feedback,
            expected_intent=args.expected_intent,
        )]
    else:
        try:
            loaded = load_dataset(
                args.test_set,
                tier=args.tier,
                offset=args.offset,
                limit=args.limit,
                strict=None,
            )
        except FileNotFoundError:
            print(
                f"测试集未找到：{Path(__file__).parent / args.test_set}，"
                "使用默认主题。"
            )
            loaded = None
            cfgs = [
                TopicCfg(topic="2024-2025年全球AI编程助手市场的主要玩家和竞争格局分析"),
                TopicCfg(topic="2025年人民币汇率走势分析及主要影响因素"),
            ]
        except ValueError as exc:
            parser.error(str(exc))
        else:
            cfgs = loaded.cases
            meta = loaded.meta

    if not cfgs:
        print("没有可评估的主题。请使用 --topic 或确保测试集存在。")
        return 1

    cfgs = with_runtime_overrides(
        cfgs,
        initial_queries=args.initial_queries,
        max_loops=args.max_loops,
    )

    print(f"正在以 '{args.mode}' 模式评估 {len(cfgs)} 个主题...")
    if args.tier:
        print(f"分层: {args.tier}")
    if args.repeat > 1:
        print(f"重复: {args.repeat} 次（独立 run_id）")
    print("主题:")
    for c in cfgs:
        extra = ""
        if c.user_feedback:
            extra = f", 反馈='{c.user_feedback[:50]}...', 预期意图={c.expected_intent}"
        identity = f"{c.case_id} " if c.case_id else ""
        print(
            f"  - {identity}{c.topic[:100]}  "
            f"(查询数={c.initial_search_query_count}, "
            f"循环数={c.max_research_loops}{extra})"
        )
    print()

    evaluator = evaluator_factory(judge_model_id=args.judge_model)
    base_run_id = args.run_id or uuid.uuid4().hex[:12]
    run_ids: list[str] = []
    report = EvalReport(
        timestamp=datetime.now().isoformat(),
        dataset=meta.name,
        frozen_at=meta.frozen_at,
        as_of=meta.as_of,
        tier=args.tier or "",
        test_set=args.test_set if not args.topic else "",
    )

    try:
        for repeat_index in range(args.repeat):
            run_id = (
                f"{base_run_id}-r{repeat_index + 1}"
                if args.repeat > 1
                else base_run_id
            )
            run_ids.append(run_id)
            if args.repeat > 1:
                print("=" * 60)
                print(f"  重复 {repeat_index + 1}/{args.repeat}  run_id={run_id}")
                print("=" * 60)
            if args.mode in ("e2e", "all"):
                print("=" * 60)
                print("  运行端到端评估...")
                print("=" * 60)
                results = evaluator.run_e2e(cfgs)
                for result, cfg in zip(results, cfgs, strict=True):
                    apply_cfg_metadata(result, cfg, run_id=run_id)
                report.e2e_results.extend(results)

            if args.mode in ("comp", "all"):
                print()
                print("=" * 60)
                print("  运行组件级评估...")
                print("=" * 60)
                results = evaluator.run_components(cfgs)
                for result, cfg in zip(results, cfgs, strict=True):
                    apply_cfg_metadata(result, cfg, run_id=run_id)
                report.component_results.extend(results)
    finally:
        evaluator.close()

    report.run_ids = run_ids

    # 打印摘要
    print()
    print(format_eval_report(report))

    # 如果指定了输出路径则保存完整 JSON 报告
    output_path = args.output or f"eval_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_eval_report(report, output_path)

    has_errors = any(result.error for result in report.e2e_results) or any(
        result.error for result in report.component_results
    )
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
