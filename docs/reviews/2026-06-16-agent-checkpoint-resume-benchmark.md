# Agent Checkpoint Resume Benchmark

- 生成时间: 2026-06-16T10:57:39.802339
- Benchmark 类型: failure injection / deterministic harness test
- Checkpoint backend: memory

## 场景

在 ResearchAgent 已完成查询生成和并行 WebSearch 后，在 critique 节点注入一次瞬时失败。
对比从头重跑与同 `thread_id` checkpoint resume 的重复搜索成本。

## 汇总结果

| 指标 | Restart | Resume | 变化 |
|---|---:|---:|---:|
| WebSearch 调用数 | 6 | 3 | -50.0% |
| Query generation 调用数 | 2 | 1 | -50.0% |
| Critique 调用数 | 2 | 2 | +0.0% |
| 最终 executed_queries | 3 | 3 | +0.0% |

## Resume 证据

- 失败后 checkpoint pending node: `['critique']`
- Restart error: `RuntimeError: injected transient critique failure`
- Resume error: `RuntimeError: injected transient critique failure`

## 简历可用表述

设计 ResearchAgent checkpoint resume 机制，在 critique 节点瞬时失败后通过同一 `thread_id` 从最近稳定状态恢复，复用已完成的查询生成与 WebSearch 结果；failure-injection benchmark 中 WebSearch 调用数由从头重跑的 6 次降至 3 次，避免重复外部搜索。
