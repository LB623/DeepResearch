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
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from eval.evaluator import (
    ComponentResult,
    E2EResult,
    EvalReport,
    Evaluator,
    TopicCfg,
    format_eval_report,
    save_eval_report,
)


def load_test_set(path: str = "test_set.json") -> list[TopicCfg]:
    """从 JSON 文件加载测试主题。

    每个主题可以指定可选的 ``initial_search_query_count`` 和
    ``max_research_loops`` 字段；如果未提供，则使用 Pydantic 默认值（2 / 2）。
    """
    full_path = Path(__file__).parent / path
    if not full_path.exists():
        print(f"测试集未找到：{full_path}，使用默认主题。")
        return [
            TopicCfg(topic="2024-2025年全球AI编程助手市场的主要玩家和竞争格局分析"),
            TopicCfg(topic="2025年人民币汇率走势分析及主要影响因素"),
        ]

    with open(full_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cfgs = []
    for item in data.get("topics", []):
        cfgs.append(TopicCfg(
            topic=item["topic"],
            initial_search_query_count=item.get("initial_search_query_count", 2),
            max_research_loops=item.get("max_research_loops", 2),
            user_feedback=item.get("user_feedback"),
            expected_intent=item.get("expected_intent"),
        ))
    return cfgs


def main():
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

    args = parser.parse_args()

    # 加载主题
    if args.topic:
        cfgs = [TopicCfg(
            topic=args.topic,
            user_feedback=args.feedback,
            expected_intent=args.expected_intent,
        )]
    else:
        cfgs = load_test_set(args.test_set)

    if not cfgs:
        print("没有可评估的主题。请使用 --topic 或确保 test_set.json 存在。")
        sys.exit(1)

    # 应用 CLI 覆盖参数
    if args.initial_queries is not None or args.max_loops is not None:
        for c in cfgs:
            if args.initial_queries is not None:
                c.initial_search_query_count = args.initial_queries
            if args.max_loops is not None:
                c.max_research_loops = args.max_loops

    print(f"正在以 '{args.mode}' 模式评估 {len(cfgs)} 个主题...")
    print(f"主题:")
    for c in cfgs:
        extra = ""
        if c.user_feedback:
            extra = f", 反馈='{c.user_feedback[:50]}...', 预期意图={c.expected_intent}"
        print(f"  - {c.topic[:100]}  (查询数={c.initial_search_query_count}, 循环数={c.max_research_loops}{extra})")
    print()

    evaluator = Evaluator(judge_model_id=args.judge_model)
    report = EvalReport(timestamp=datetime.now().isoformat())

    if args.mode in ("e2e", "all"):
        print("=" * 60)
        print("  运行端到端评估...")
        print("=" * 60)
        report.e2e_results = evaluator.run_e2e(cfgs)

    if args.mode in ("comp", "all"):
        print()
        print("=" * 60)
        print("  运行组件级评估...")
        print("=" * 60)
        report.component_results = evaluator.run_components(cfgs)

    # 打印摘要
    print()
    print(format_eval_report(report))

    # 如果指定了输出路径则保存完整 JSON 报告
    output_path = args.output or f"eval_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_eval_report(report, output_path)


if __name__ == "__main__":
    main()
