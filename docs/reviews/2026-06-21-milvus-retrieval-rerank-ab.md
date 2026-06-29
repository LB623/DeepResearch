# Milvus 事实检索质量感知重排 A/B 评测

- 时间：`2026-06-21T10:56:47+08:00`
- Collection：`eval_retrieval_rerank_20260621`（隔离评测集合）
- Embedding：`bge-m3`
- 固定集：`8` 个查询 / `48` 条受控事实
- 变量：baseline 为 Milvus 原始 Top-K；optimized 为 3x 候选过采样 + 过滤 + 质量感知重排 + 去重

## 汇总结果

| 指标 | baseline | optimized | 变化 |
|---|---:|---:|---:|
| Precision@K | 66.7% | 83.3% | +16.7 pp |
| Recall@K | 66.7% | 83.3% | +16.7 pp |
| NDCG@K | 78.6% | 89.4% | +10.8 pp |
| 有效槽位率 | 95.8% | 100.0% | +4.2 pp |
| 重复率 | 31.2% | 0.0% | +31.2 pp |

## 逐查询结果

| 查询 | P@K baseline | P@K optimized | NDCG baseline | NDCG optimized |
|---|---:|---:|---:|---:|
| 2026 AI编程助手市场规模与增长率 | 66.7% | 100.0% | 81.8% | 100.0% |
| Milvus 2.6 向量检索与混合搜索能力 | 66.7% | 100.0% | 81.3% | 100.0% |
| 特斯拉FSD 2026年监管与产品进展 | 66.7% | 66.7% | 81.8% | 85.6% |
| 2026人民币汇率与央行政策变化 | 66.7% | 66.7% | 81.8% | 81.8% |
| 2026全球半导体供应链风险与产能布局 | 66.7% | 66.7% | 81.8% | 85.6% |
| 规范驱动开发 SDD 与 AGENTS.md 最佳实践 | 100.0% | 100.0% | 84.5% | 84.5% |
| Redis 搜索缓存一致性与失效策略 | 66.7% | 66.7% | 81.8% | 81.8% |
| LangGraph checkpoint 故障恢复与幂等执行 | 33.3% | 100.0% | 54.2% | 95.9% |

## 实现与复现

- 修复 COSINE 分数方向：Milvus 返回值越大越相似，不再执行 `1 - distance`。
- optimized 先取 `3 x top_k` 候选，再执行置信度/时效过滤，避免无效候选占坑。
- 按 `0.65 x relevance + 0.25 x confidence + 0.10 x freshness` 重排并做规范化去重。
- `KB_RERANK_ENABLED=0/1` 可切换历史基线与优化路径，不增加模型调用。

```bash
cd backend
../.venv/bin/python -m eval.run_retrieval_benchmark \
  --collection eval_retrieval_rerank_20260621 \
  --output eval_runs/retrieval_rerank_20260621.json \
  --report ../docs/reviews/2026-06-21-milvus-retrieval-rerank-ab.md
```

## 边界

该评测使用真实 Milvus 检索与真实 embedding，但语料是带人工相关性标签的受控组件集。
指标只证明检索组件在该固定集上的排序、回填和去重效果，不代表 E2E 报告质量提升。

## 简历表述

针对 Milvus 原始 Top-K 在时效过滤后候选不足、重复事实占位的问题，设计 3 倍候选过采样与相关度/置信度/新鲜度加权重排；在 8 查询、48 条事实固定组件集上，Precision@3 从 66.7% 提升至 83.3%，NDCG@3 从 78.6% 提升至 89.4%，重复率由 31.2% 降至 0%。
