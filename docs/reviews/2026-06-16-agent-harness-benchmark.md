# Agent Harness Benchmark

- 生成时间: 2026-06-16T09:53:55.503040
- 原始数据: `eval/benchmark_report_20260616.json`
- Benchmark 集: `backend/eval/benchmark_set.json`
- Run mode: `research-only`
- Query model: `deepseek-v4-flash`
- Reflection model: `deepseek-v4-flash`
- Citation Judge: disabled

## 问题

并行检索阶段把生成查询和已执行查询混写到累加型 `search_query` 状态，导致多轮任务中查询列表被重复累计，后续评估、引用追踪和成本分析都失真。

## 优化

将查询状态拆分为 `generated_queries`、`executed_queries` 和 `skipped_duplicate_queries`，并在 fan-out 和 follow-up 执行前做规范化去重。`QUERY_DEDUPE_ENABLED=0` 用于复现 baseline，默认开启优化。

## 汇总结果

| 指标 | Baseline | Optimized | 变化 |
|---|---:|---:|---:|
| 任务成功率 | 100.0% | 100.0% | +0.0pp |
| 状态查询重复率 | 50.0% | 0.0% | -50.0pp |
| 实际执行查询重复率 | 0.0% | 0.0% | +0.0pp |
| 平均状态查询数 | 6.00 | 3.00 | -50.0% |
| 平均执行查询数 | 3.00 | 3.00 | +0.0% |
| 平均 LLM 调用数 | 8.00 | 8.00 | +0.0% |
| 平均 total tokens | 29202.8 | 30084.9 | +3.0% |
| 平均 prompt chars | 40328.60 | 41279.90 | +2.4% |
| 引用有效率 | N/A | N/A | N/A |

## 单题结果

| Variant | Topic | Success | State Dup | Exec Dup | State Q | Exec Q | Loops | KB Before | KB After | LLM Calls | Error |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 2024-2025年全球AI编程助手市场竞争格局分析 | yes | 50.0% | 0.0% | 6 | 3 | 1 | 52 | 52 | 8 |  |
| baseline | 规范驱动开发 SDD 与 AGENTS.md 的关系 | yes | 50.0% | 0.0% | 6 | 3 | 1 | 52 | 52 | 8 |  |
| baseline | 2025年AI芯片市场趋势与主要玩家分析 | yes | 50.0% | 0.0% | 6 | 3 | 1 | 52 | 52 | 8 |  |
| baseline | 特斯拉 FSD 中美技术进展和监管政策对比 | yes | 50.0% | 0.0% | 6 | 3 | 1 | 52 | 181 | 8 |  |
| baseline | 全球半导体供应链重构趋势与中国企业影响 | yes | 50.0% | 0.0% | 6 | 3 | 1 | 181 | 181 | 8 |  |
| baseline | 开源大模型与闭源大模型在企业落地中的竞争分析 | yes | 50.0% | 0.0% | 6 | 3 | 1 | 181 | 181 | 8 |  |
| baseline | Agent Harness 工程方法：上下文管理、工具调用和状态恢复 | yes | 50.0% | 0.0% | 6 | 3 | 1 | 181 | 181 | 8 |  |
| baseline | RAG 系统评估方法：检索质量、答案忠实度和引用有效性 | yes | 50.0% | 0.0% | 6 | 3 | 1 | 181 | 181 | 8 |  |
| baseline | AI 搜索产品 Perplexity、ChatGPT Search、Google AI Over | yes | 50.0% | 0.0% | 6 | 3 | 1 | 181 | 181 | 8 |  |
| baseline | 大模型推理成本优化方法：缓存、路由、小模型蒸馏和批处理 | yes | 50.0% | 0.0% | 6 | 3 | 1 | 181 | 181 | 8 |  |
| optimized | 2024-2025年全球AI编程助手市场竞争格局分析 | yes | 0.0% | 0.0% | 3 | 3 | 1 | 181 | 181 | 8 |  |
| optimized | 规范驱动开发 SDD 与 AGENTS.md 的关系 | yes | 0.0% | 0.0% | 3 | 3 | 1 | 181 | 181 | 8 |  |
| optimized | 2025年AI芯片市场趋势与主要玩家分析 | yes | 0.0% | 0.0% | 3 | 3 | 1 | 181 | 181 | 8 |  |
| optimized | 特斯拉 FSD 中美技术进展和监管政策对比 | yes | 0.0% | 0.0% | 3 | 3 | 1 | 181 | 181 | 8 |  |
| optimized | 全球半导体供应链重构趋势与中国企业影响 | yes | 0.0% | 0.0% | 3 | 3 | 1 | 181 | 181 | 8 |  |
| optimized | 开源大模型与闭源大模型在企业落地中的竞争分析 | yes | 0.0% | 0.0% | 3 | 3 | 1 | 181 | 181 | 8 |  |
| optimized | Agent Harness 工程方法：上下文管理、工具调用和状态恢复 | yes | 0.0% | 0.0% | 3 | 3 | 1 | 181 | 181 | 8 |  |
| optimized | RAG 系统评估方法：检索质量、答案忠实度和引用有效性 | yes | 0.0% | 0.0% | 3 | 3 | 1 | 181 | 442 | 8 |  |
| optimized | AI 搜索产品 Perplexity、ChatGPT Search、Google AI Over | yes | 0.0% | 0.0% | 3 | 3 | 1 | 442 | 442 | 8 |  |
| optimized | 大模型推理成本优化方法：缓存、路由、小模型蒸馏和批处理 | yes | 0.0% | 0.0% | 3 | 3 | 1 | 442 | 442 | 8 |  |

## 简历可用表述

如果 10 题全部真实跑通，可将上表中的优化前后数据压缩为简历 bullet；如果存在 blocked/error，应只引用成功样本范围，并在报告中保留失败原因。
