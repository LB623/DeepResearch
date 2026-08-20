# 固定 E2E 评测集扩容与可信度改造

- 日期：2026-08-19
- 数据集：`backend/eval/test_set_e2e.json`（`e2e_fixed_v2`，冻结 `2026-06-30`）
- 本文件记录规模判断、草案缺陷和简历口径。**没有在本轮运行任何付费 E2E。**

## 规模判断

DeepResearch 单题包含多轮 LLM、Web Search、Writer-Critic 和 Judge。历史 5 题在 `2 queries / 2 loops` 下单变体约 34 分钟。扩展题多为 3–4 循环，单题可能 10–20 分钟；正式结论还要 A/B × 重复运行。

| 层 | 题数 | 用途 | 单变体成本（量级） | 正式 A/B（2 变体 × 3 重复） |
|---|---:|---|---|---|
| smoke | 5 | 日常回归 + 历史可复现 | 35–90 分钟 | 约 3–9 小时 |
| core | 30 | 默认正式 benchmark | 约 5–8 小时 | 约 30–48 小时 |
| full | 100 | 覆盖目录，分批/单次画像 | 约 16–30 小时（单次） | 不作为默认 3 重复 A/B |

30 是成对 A/B 报告均值、胜率和幻觉率的最低可解释样本，并能让 8 个领域、10 个能力维在 core 内都出现。50 作为 core 会把正式 A/B 推到约 50 小时以上。100 只作为 catalog，补齐长尾检索、跨语言原文、拒答和口径冲突。

## 50 题草案主要缺陷

`test_set_e2e_50.json` 题目本身多数不是换皮题，但作为正式集不合格：

1. `case_id` / `domain` / `difficulty` / `evaluation_focus` 没有进入加载器和 E2E JSON。
2. 没有 `tier`；文案写 001–020 是 core，字段不存在。
3. `domain` 近 49 个细类，无法分层统计。
4. `evaluation_focus` 开放中文标签，无法按能力聚合。
5. `difficulty` 几乎等于 query/loop 预算。
6. 错误前提、显式数字冲突、跨语言原文、长尾检索、证据不足拒答覆盖不足。
7. AI / 能源 / 医学扎堆。
8. 没有重复运行、离线聚合、胜率、标准差、置信区间和小样本警告。

## 本轮实现

- 权威集 100 题，`e2e-001` … `e2e-100`。前 5 题 topic 与查询预算与 `test_set_basic_5.json` 完全一致。
- 8 个一级领域，10 个受控能力标签。
- CLI：`--tier`、`--offset`、`--limit`、`--repeat`、独立 `run_id`。
- 离线 `python -m eval.aggregate`：样本数、成功/失败、均分与标准差、五维均值、幻觉率、按 tier/domain/difficulty 分组、A/B 逐题胜率与分数差、小样本警告。
- 历史只有 `topic` 的 JSON 可按题目文本回退配对。

## 分层分布（构建时）

以 `test_set_e2e.json` 为准。core 不是 001–020 切片，而是按能力覆盖打标的 30 题。full 新增 50 题补缺口，禁止“换年份/换地区”复制。

## 可写进简历

- 构建了分层固定 E2E 评测集：smoke 5 / core 30 / full 100，元数据进入运行结果和离线聚合。
- Prompt Quality Guards 在历史 5 题固定集上将幻觉从 3/5 降到 0/5（v3），平均分 4.36 → 4.24；只能表述为降低幻觉并加强事实约束，不能表述为整体质量提升。

## 不能写

- 0/50、0/100，或“扩展集幻觉率为 0”。
- 已在 30 题或 100 题上完成正式 A/B。
- 质量全面提升。

## 必须等真实评测才能更新

core / full 均分、标准差、幻觉率、逐题胜率、分层指标，以及任何“扩展集上的 A/B 结论”。

## 正式 A/B 命令

历史 5 题复现（与 2026-06-18 对齐的 2/2 预算，3 次重复）：

```bash
cd backend
PROMPT_QUALITY_GUARDS=0 ../.venv/bin/python -m eval.run_eval --mode e2e \
  --test-set test_set_e2e.json --tier smoke \
  --initial-queries 2 --max-loops 2 --repeat 3 \
  --output eval_runs/e2e_baseline_smoke_r3.json

PROMPT_QUALITY_GUARDS=1 ../.venv/bin/python -m eval.run_eval --mode e2e \
  --test-set test_set_e2e.json --tier smoke \
  --initial-queries 2 --max-loops 2 --repeat 3 \
  --output eval_runs/e2e_guards_smoke_r3.json

../.venv/bin/python -m eval.aggregate \
  --baseline eval_runs/e2e_baseline_smoke_r3.json \
  --optimized eval_runs/e2e_guards_smoke_r3.json \
  --output eval_runs/e2e_smoke_ab_summary.json
```

正式 core（原生每题预算，3 次重复；两变体只改 `PROMPT_QUALITY_GUARDS`）：

```bash
cd backend
PROMPT_QUALITY_GUARDS=0 ../.venv/bin/python -m eval.run_eval --mode e2e \
  --test-set test_set_e2e.json --tier core --repeat 3 \
  --output eval_runs/e2e_baseline_core_r3.json

PROMPT_QUALITY_GUARDS=1 ../.venv/bin/python -m eval.run_eval --mode e2e \
  --test-set test_set_e2e.json --tier core --repeat 3 \
  --output eval_runs/e2e_guards_core_r3.json

../.venv/bin/python -m eval.aggregate \
  --baseline eval_runs/e2e_baseline_core_r3.json \
  --optimized eval_runs/e2e_guards_core_r3.json \
  --output eval_runs/e2e_core_ab_summary.json
```
