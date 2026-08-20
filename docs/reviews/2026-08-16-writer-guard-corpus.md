# Writer 输出契约对抗评测

- 时间：`2026-08-20T08:40:02.024968+00:00`
- 语料：`eval/guard_corpus.json`
- 样本数：39
- 方法：用现有 `_polish_rejection_reason` / `_draft_rejection_reason` / `_unsupported_named_terms` 和确定性契约函数打分，不调用模型

## 汇总

- 该拒召回率：`100.0%`
- 不该拒误伤率：`0.0%`
- 判定准确率：`100.0%`

| 类别 | n | 召回率 | 误伤率 | 准确率 |
|---|---:|---:|---:|---:|
| empty_or_fence | 4 | 100.0% | n/a | 100.0% |
| internal_leftover | 4 | 100.0% | n/a | 100.0% |
| missing_heading | 4 | 100.0% | n/a | 100.0% |
| missing_outline_section | 3 | 100.0% | n/a | 100.0% |
| new_named_term | 5 | 100.0% | n/a | 100.0% |
| truncation | 4 | 100.0% | n/a | 100.0% |
| unknown_url | 4 | 100.0% | n/a | 100.0% |
| unsupported_entity | 3 | 100.0% | n/a | 100.0% |
| valid_control | 8 | n/a | 0.0% | 100.0% |

## 失败样本

无。

## 边界

- `contract` 类样本测量终稿回放规则，不要求现有 polish 拒绝函数已经覆盖内部占位。
- 召回率和误伤率按语料标签计算；标签与实现不一致时记为失败样本，不改标签凑数。
- 历史 E2E 里的内部占位能被契约规则抓到，但当前 polish 拒绝函数并不会因此拒稿。这是已知缺口，不是语料造分。
