# Milvus 事实检索质量感知重排 A/B 评测

- 时间：`2026-08-16T22:10:16+08:00`
- Collection：`eval_retrieval_rerank_v2_20260816`（隔离评测集合）
- Embedding：`bge-m3`
- 数据集：`retrieval-controlled-v2` / `2c92e5f40ab8`
- 固定集：`100` 个查询 / `1000` 条受控事实记录
- 本次口径：`test` 集，`70` 个查询
- 变量：baseline 为过滤后的 Milvus Top-K；optimized 为 3x 候选过采样、过滤、质量重排与规范化去重

## 汇总结果

| K | 指标 | baseline | optimized | 变化 | paired bootstrap 95% CI |
|---:|---|---:|---:|---:|---:|
| 3 | Unique Precision@K | 30.0% | 40.0% | +10.0 pp | [+3.3 pp, +16.7 pp] |
| 3 | Recall@K | 18.0% | 24.0% | +6.0 pp | [+2.0 pp, +10.0 pp] |
| 3 | NDCG@K | 19.3% | 30.2% | +10.9 pp | [+5.5 pp, +16.5 pp] |
| 3 | 有效槽位率 | 100.0% | 100.0% | +0.0 pp | [+0.0 pp, +0.0 pp] |
| 3 | 重复率 | 29.5% | 0.0% | -29.5 pp | [-35.7 pp, -22.9 pp] |
| 5 | Unique Precision@K | 33.1% | 46.6% | +13.4 pp | [+6.9 pp, +19.7 pp] |
| 5 | Recall@K | 33.1% | 46.6% | +13.4 pp | [+7.1 pp, +19.7 pp] |
| 5 | NDCG@K | 24.6% | 39.4% | +14.8 pp | [+9.3 pp, +20.3 pp] |
| 5 | 有效槽位率 | 100.0% | 100.0% | +0.0 pp | [+0.0 pp, +0.0 pp] |
| 5 | 重复率 | 29.4% | 0.0% | -29.4 pp | [-33.1 pp, -25.4 pp] |
| 10 | Unique Precision@K | 37.7% | 34.1% | -3.6 pp | [-7.0 pp, -0.4 pp] |
| 10 | Recall@K | 75.4% | 68.3% | -7.1 pp | [-14.0 pp, -0.9 pp] |
| 10 | NDCG@K | 41.5% | 46.0% | +4.5 pp | [-0.9 pp, +9.8 pp] |
| 10 | 有效槽位率 | 82.6% | 100.0% | +17.4 pp | [+16.0 pp, +18.9 pp] |
| 10 | 重复率 | 23.2% | 0.0% | -23.2 pp | [-24.6 pp, -21.6 pp] |

## 分主题结果（K=5）

| 主题域 | baseline NDCG | optimized NDCG | baseline 重复率 | optimized 重复率 |
|---|---:|---:|---:|---:|
| historical | 13.8% | 19.7% | 35.7% | 0.0% |
| market_data | 33.5% | 46.7% | 24.3% | 0.0% |
| product_info | 12.9% | 42.6% | 40.0% | 0.0% |
| strategy | 28.1% | 45.6% | 31.4% | 0.0% |
| technology | 34.7% | 42.2% | 15.7% | 0.0% |

## 结论

- 主指标 NDCG@5 提升 +14.8 pp，paired bootstrap 95% CI 为 [+9.3 pp, +20.3 pp]。
- K=10 的 Precision 与 Recall 出现回退，NDCG 差值置信区间跨 0，不作为效果提升结论。

## 实现与复现

- 100 个查询由 5 个主题域构成，每域 6 个开发查询与 14 个冻结测试查询。
- 每个查询对应 5 条分级相关事实，以及重复、过期、冲突和近邻实体干扰项。
- 所有主题域共用一个 1,000 条记录的全局候选池，查询不会只在所属小组内检索。
- 查询 embedding 在 baseline 与 optimized 间复用，不增加 LLM rerank 调用。
- 指标差值以查询为配对单位执行 percentile bootstrap。

```bash
cd backend
../.venv/bin/python -m eval.run_retrieval_benchmark \
  --collection eval_retrieval_rerank_v2_20260816 \
  --split test \
  --top-k 3 5 10 \
  --output eval_runs/retrieval_rerank_v2.json \
  --report ../docs/reviews/retrieval-rerank-v2.md
```

## 边界

该评测使用真实 Milvus 检索与真实 embedding，但语料是合成的受控组件集。
指标只证明该固定集上的排序、生命周期过滤与去重效果，不代表真实语料或 E2E 报告质量。

## 简历表述候选

在 70 个冻结测试查询、1,000 条受控事实记录和 5 个主题域的组件评测中，通过 3 倍候选过采样、质量重排与去重，将 NDCG@5 从 24.6% 提升至 39.4%，重复率由 29.4% 降至 0.0%。
