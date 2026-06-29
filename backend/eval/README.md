# DeepResearch Agent 评估框架

## 目录

- [文件结构](#文件结构)
- [各模块职责](#各模块职责)
- [使用方式](#使用方式)
- [评估报告如何解读](#评估报告如何解读)
- [评分维度详解](#评分维度详解)
- [常见问题](#常见问题)

---

## 文件结构

```
backend/eval/
├── __init__.py          # 包说明
├── prompts.py           # Judge LLM 评分提示词模板（7 套）
├── judge.py             # LLM Judge 封装 + Pydantic 评分数据模型
├── evaluator.py         # 评估执行器：端到端 + 组件级评估
├── run_eval.py          # CLI 命令行入口
├── run_retrieval_benchmark.py # Milvus 检索组件确定性 A/B
├── test_set.json        # 测试用例集（5 个 topic）
└── README.md            # 本文档
```

---

## 各模块职责

### `prompts.py` — 评分提示词（核心资产）

定义了 8 套 Judge LLM 提示词模板，每套对应一个评分任务：

| 提示词常量 | 用途 |
|---|---|
| `E2E_JUDGE_INSTRUCTIONS` | 端到端：对最终研究报告做 5 维度评分 |
| `PLAN_JUDGE_INSTRUCTIONS` | 组件级：评估生成的研究计划质量 |
| `QUERY_JUDGE_INSTRUCTIONS` | 组件级：评估搜索查询的覆盖度/独立性/搜索友好性 |
| `PLAN_QUERY_ALIGNMENT_JUDGE_INSTRUCTIONS` | 组件级：评估 plan → queries 的衔接质量 |
| `SUMMARIZATION_JUDGE_INSTRUCTIONS` | 组件级：评估搜索结果摘要的忠实度（幻觉检测） |
| `CRITIQUE_JUDGE_INSTRUCTIONS` | 组件级：评估反思节点的充足性判断 |
| `CITATION_JUDGE_INSTRUCTIONS` | 组件级：逐条验证引用是否支撑段落论点 |
| `PLAN_REFLECTION_JUDGE_INSTRUCTIONS` | 组件级：评估需求澄清阶段的意图识别准确性和 replan 质量 |

所有提示词均要求 Judge LLM 输出结构化 JSON，通过 `Post.extract_pattern` 解析。

### `judge.py` — LLM Judge 封装

**`Judge` 类**：封装 LLM 调用（3 次重试），提供以下评估方法：

```python
judge = Judge(model_id="qwen3.7-max")

# 端到端
judge.evaluate_report(research_topic=..., search_sources=..., report=...)

# 组件级
judge.evaluate_plan(research_topic=..., plan=...)
judge.evaluate_queries(research_topic=..., queries=..., rationale=...)
judge.evaluate_plan_query_alignment(plan=..., queries=...)
judge.evaluate_plan_reflection(original_plan=..., user_feedback=..., new_plan=..., actual_behavior=..., expected_intent=...)
judge.evaluate_summarization(search_query=..., raw_search_results=..., summary=...)
judge.evaluate_critique(research_topic=..., summaries=..., is_sufficient=..., ...)
judge.evaluate_citations(sources=..., report=...)
```

**Pydantic 评分模型**：每个方法返回强类型 Pydantic 对象（见下方[评分维度详解](#评分维度详解)）。

### `evaluator.py` — 评估执行器

**`Evaluator` 类**：编排评估流程，核心逻辑：

1. **`run_e2e(topics)`** — 端到端评估
   - 对每个 topic 运行完整 agent 流水线
   - 收集最终报告 + 来源列表
   - 调用 Judge 做 5 维度评分

2. **`run_components(topics)`** — 组件级评估
   - 通过 `_invoke_agent_with_feedback()` 执行 agent 流水线，支持模拟用户反馈
   - 若 topic 配置了 `user_feedback`：Phase 1 生成 plan A → Phase 2 发送反馈走 LLM 意图识别 → 若触发 replan 则 Phase 3 确认并继续
   - 若未配置 feedback：沿用两阶段自动确认
   - 通过 monkey-patch 捕获原始搜索结果（用于摘要保真度评估）
   - 逐节点调用 Judge 评分

3. **`format_eval_report(report)`** — 生成可读文本摘要
4. **`save_eval_report(report, path)`** — 保存完整 JSON 报告

**关键设计决策**：
- Human-in-the-loop 的 plan 确认步骤：Phase 1 生成 plan，Phase 2 自动发送"需求确认"继续（无 feedback 时）；有 feedback 时走 LLM 意图识别路径，支持 replan 循环
- 原始搜索结果捕获：hook `WebSearchAgent.step()` 以获取摘要前的原始数据
- **需求澄清评估**：`TopicCfg` 有 `user_feedback` 和 `expected_intent` 字段，模拟用户在计划确认阶段的真实反馈，覆盖 LLM 意图识别和 replan 两条路径

### `run_eval.py` — CLI 入口

```bash
# 端到端评估所有测试用例
python -m eval.run_eval --mode e2e

# 组件级评估
python -m eval.run_eval --mode comp

# 全部模式
python -m eval.run_eval --mode all

# 单条 topic 快速测试
python -m eval.run_eval --mode e2e --topic "2025年AI芯片市场趋势"

# 指定 judge 模型 + 保存结果
python -m eval.run_eval --mode all --judge-model qwen3.7-max --output results.json

# 覆盖所有 topic 的搜索参数（用于对比不同 effort 水平）
python -m eval.run_eval --mode all --initial-queries 5 --max-loops 10

# 单条 topic 指定参数
python -m eval.run_eval --mode e2e --topic "..." --initial-queries 3 --max-loops 3

# 单条 topic + 模拟用户反馈（测试需求澄清阶段）
python -m eval.run_eval --mode comp --topic "2025年AI芯片市场趋势" \
  --feedback "请增加对开源模型的竞争分析" --expected-intent replan

# 模拟确认场景
python -m eval.run_eval --mode comp --topic "..." \
  --feedback "看起来很全面，可以开始了" --expected-intent proceed
```

### Milvus 检索组件 A/B

该 benchmark 使用隔离 Milvus collection、真实 embedding 和带人工相关性标签的
受控固定集，对比原始 Top-K 与质量感知重排。它不调用 Judge，指标不受 LLM 评分随机性影响。

```bash
cd backend
../.venv/bin/python -m eval.run_retrieval_benchmark \
  --collection eval_retrieval_rerank \
  --output eval_runs/retrieval_rerank.json \
  --report ../docs/reviews/milvus-retrieval-rerank-ab.md
```

默认在结束时删除隔离 collection；调试时可追加 `--keep-collection`。

### `test_set.json` — 测试用例集

10 个测试用例（5 个基础 + 5 个带用户反馈的需求澄清测试），覆盖不同领域和难度：

**基础测试用例（5 个）**：

| 领域 | 难度 | queries | loops | 例 |
|---|---|---|---|---|
| 科技 | medium | 3 | 3 | 2024-2025年全球AI编程助手市场竞争格局 |
| 金融 | medium | 3 | 3 | 2025年人民币汇率走势分析 |
| 科技+政策 | medium | 3 | 3 | 特斯拉FSD中美技术进展和监管对比 |
| 产业政策 | high | 5 | 10 | 全球半导体供应链重构趋势 |
| 技术方法论 | low | 1 | 1 | 规范驱动开发SDD与AGENTS.md的关系 |

**需求澄清测试用例（5 个）**，通过 `user_feedback` 和 `expected_intent` 字段模拟用户在计划确认阶段的反馈：

| 场景 | user_feedback | expected_intent |
|---|---|---|
| 明确确认 | "看起来很全面，可以开始了" | proceed |
| 明确纠正 | "不要分析中国市场，改为分析东南亚市场" | replan |
| 补充需求 | "方向对的，但请再加入对开源模型竞争的分析" | replan |
| 极简确认 | "可以" | proceed |
| 否定反馈 | "这个计划完全不对，我需要技术分析不是市场分析" | replan |

每个 topic 包含 `expected_key_facts`（预期关键事实），用于人工对照检查，以及可选的 `initial_search_query_count` / `max_research_loops` 覆盖默认值（2/2）。

---

## 使用方式

### 前置条件

1. 确保 `backend/.env` 已配置 `APP_TOKEN` 和 `LLM_BASE_URL`
2. 确保 `backend` 包已安装：`cd backend && pip install -e .`

### 典型工作流

```bash
cd backend

# 第一步：快速验证 —— 单条 topic 端到端
python -m eval.run_eval --mode e2e --topic "2025年AI芯片市场趋势"

# 第二步：完整测试集
python -m eval.run_eval --mode all

# 第三步：查看报告
cat eval_report_20260529_143000.json
```

### 输出文件

每次运行会生成两个输出：

1. **终端显示**（`format_eval_report`）— 包含每道 topic 的各维度得分和平均分
2. **JSON 完整报告**（`eval_report_YYYYMMDD_HHMMSS.json`）— 包含所有评分细节、`per_citation` 逐条记录、`cross_reference_table` 等

### 自定义测试集

编辑 `test_set.json`，按相同格式添加 topic：

```json
{
  "topics": [
    {
      "topic": "你的研究课题",
      "domain": "领域",
      "difficulty": "easy|medium|hard",
      "expected_key_facts": ["关键事实1", "关键事实2"]
    }
  ]
}
```

也可以不依赖文件，直接 `--topic` 传入。

---

## 评估报告如何解读

### 端到端报告得分（e2e）

输出示例：

```
--- End-to-End Report Scores ---

  Topic: 2024-2025年全球AI编程助手市场...
    Overall: 3.4/5
    Factual Accuracy: 4/5
    Info Coverage:    3/5
    Logical Structure: 4/5
    Timeliness:       3/5
    Citation Quality:  3/5
    Hallucinations:    None

  ** Average overall score: 3.4/5 (n=5) **
```

**得分含义**：

| 分数 | 含义 |
|---|---|
| 4.0-5.0 | 优秀：报告质量接近人工撰写 |
| 3.0-3.9 | 合格：可用，但有明确改进空间 |
| 2.0-2.9 | 较差：存在明显问题，需要调整 Agent 配置 |
| 1.0-1.9 | 不可用：基本事实错误或结构严重缺陷 |

**`Hallucinations` 字段**：标记是否存在无来源支撑的陈述。若为 YES，查看 JSON 报告中的 `hallucination_check.details`。

### 组件级得分（comp）

输出示例：

```
--- Component-Level Scores ---

  Topic: 2024-2025年全球AI编程助手市场...
    Plan:         3.7/5
    Queries:      4.0/5
    Plan→Query:   3.7/5
      Missed: 风险研判维度, 信息源偏好
    Summarisation: 3.5/5 (n=3)
    Critique:     4.0/5
    Citations:    3/5  (valid=6/10, weak=1, invalid=3)
      [content_mismatch] https://search.com/id/2-1 — 段落讨论Y策略，但来源是关于Z技术的
      [url_not_found] https://fake-url.com — 该URL不在来源列表中
    Plan Reflection:
      Intent Recognition:   4/5
      Feedback Incorporation: 4/5
      Overall: 4.0/5  (behavior: replan_then_proceed)
```

**链路诊断**：

| 得分模式 | 诊断 | 建议 |
|---|---|---|
| Plan 低，Queries 高 | 计划写得差但查询不错 | 优化 `plan_instructions` 提示词 |
| Plan 高，Queries 低 | 计划合理但查询未有效分解 | 优化 `query_writer_instructions` 提示词 |
| Plan→Query 低 | 计划和查询之间有断裂 | 检查查询是否遵循了计划的边界约束 |
| Summarisation 低 | 摘要存在幻觉或遗漏关键信息 | 优化 `web_searcher_instructions` 提示词 |
| Critique 低 | 反思判断不准（过早终止 or 过度搜索） | 优化 `reflection_instructions` 或调整 `max_research_loops` |
| Citations 低 | 引用格式问题或串联错误 | 检查 URL 映射逻辑（`resolve_urls`） |
| Plan Reflection 低 | 意图识别不准或 replan 未吸收反馈 | 优化 `plan_reflection_instructions` 提示词或检查 `PlanReflection` schema |

---

## 评分维度详解

### 端到端：5 维度

| 维度 | 满分 | 评估要点 |
|---|---|---|
| **事实准确性** | 5 | 陈述是否有来源支撑？是否有虚构信息？ |
| **信息覆盖度** | 5 | 是否覆盖研究主题的所有关键方面？ |
| **逻辑结构** | 5 | 报告组织是否清晰？论证是否连贯？ |
| **时效性** | 5 | 是否使用了最新信息？ |
| **引用质量** | 5 | 引用是否恰当标注？来源是否可信？ |

### 组件级：Plan

| 维度 | 评估要点 |
|---|---|
| **需求覆盖率** | 是否覆盖了 5 大关键要素（分析对象/对手策略/风险研判/时空边界/输出格式）？ |
| **问题清晰度** | 追问是否精准、具体、有引导性？ |
| **结构合理性** | 计划是否清晰可执行？ |

### 组件级：Plan Reflection（需求澄清）

评估系统在计划确认阶段对用户反馈的处理质量。仅当 topic 配置了 `user_feedback` 和 `expected_intent` 时执行。

| 维度 | 评估要点 |
|---|---|
| **意图识别准确性** | 是否根据用户反馈正确判断了用户意图（确认继续 or 需要修改计划）？ |
| **反馈吸收质量** | 若触发 replan，新计划是否真正回应了用户的具体关切？是针对性修改还是表面改动？若正确判断用户确认（未 replan），本维度默认满分 |
| **计划连贯性** | 若 replan，新计划是否保持良好结构和可执行性？是否在解决用户关切时保留了原计划的合理部分？ |

`actual_behavior` 字段记录系统的实际行为：
- `direct_proceed` — 用户反馈包含硬编码关键字（"需求确认"/"开始研究"），直接继续
- `llm_proceed` — 通过 LLM 意图识别判断用户满意，继续执行
- `replan_then_proceed` — LLM 识别用户不满意，触发 replan 后继续

### 组件级：Plan → Query 衔接

| 维度 | 评估要点 |
|---|---|
| **覆盖一致性** | 计划中的关键维度是否都有对应的搜索查询？ |
| **计划忠实度** | 查询是否遵循计划的边界（时间/媒体/分析重点）？ |
| **结构化拆解** | 查询是对计划的细化还是简单照搬标题？ |

`cross_reference_table` 字段展示了每个计划维度到查询的映射关系：
- `full` — 该维度有对应查询
- `partial` — 部分覆盖
- `missed` — 完全遗漏

### 组件级：Queries

| 维度 | 评估要点 |
|---|---|
| **覆盖度** | 查询是否覆盖了研究主题的不同维度？ |
| **独立性** | 各查询之间是否减少冗余？ |
| **搜索友好性** | 查询是否适合搜索引擎（关键词具体，非笼统）？ |

### 组件级：Summarisation

| 维度 | 评估要点 |
|---|---|
| **事实保真度** | 总结中的陈述是否能在搜索结果中找到支撑？ |
| **关键信息提取** | 是否提取了最相关的信息？ |
| **来源标注** | 是否正确标注信息来源？ |

`hallucinations` 字段列出总结中无法在原始搜索结果中找到对应的事实陈述。

### 组件级：Critique

| 维度 | 评估要点 |
|---|---|
| **充足性判断** | `is_sufficient` 的判断是否正确？ |
| **差距识别** | `knowledge_gap` 描述是否准确指出了缺失的信息？ |
| **后续查询质量** | `follow_up_queries` 是否能有效弥补差距？ |

`is_sufficiency_correct` 是 Judge 对反思节点判断的元评价（True/False）。

### 组件级：Citations（逐条验证）

每个引用被标记为以下状态之一：

| 状态 | 含义 |
|---|---|
| `valid` | URL 存在，且段落论点与来源内容相关 |
| `weak` | URL 存在且相关，但引用方式笼统（如整段只末尾一个引用） |
| `content_mismatch` | URL 存在，但段落论点与来源内容不相关或矛盾 |
| `url_not_found` | URL 不在来源列表中（可能是虚构的或 URL 映射错误） |

JSON 报告中 `per_citation` 数组包含每条引用的 `paragraph_summary`（段落概括）、`source_title`（来源标题）、`status`、`reason`，可直接定位问题引用。

---

## 常见问题

### Q: 为什么每次运行分数不一样？

**A:** 三个随机性来源：
1. 网络搜索结果每次不同
2. Agent LLM 生成有随机性
3. Judge LLM 评分也有随机性

**建议**：对重要评估跑 3 次取平均；更关注趋势（改提示词后分数是否上升）而非绝对值。

### Q: Judge 模型应该用哪个？

**A:** 推荐用可用模型中最强的（如 `qwen3.7-max`），避免用 Judge 去评分自己生成的报告（如果 Agent 也用同一个模型）。可设 `EVAL_MODEL` 环境变量：
```bash
export EVAL_MODEL=qwen3.7-max
```

### Q: Agent 需要 .env 吗？

**A:** 是的。Agent 的 web search 和 LLM 调用都依赖 `APP_TOKEN`、`LLM_BASE_URL`、`MCP_APP_ID`。评估脚本会自动加载 `.env`。

### Q: 为什么组件评估里 Plan→Query 有时没有分数？

**A:** 只有在 plan 和 queries 都存在且非空时才会执行 plan→query alignment 评估。如果 agent 的 plan 节点因为 `plan_status` 被跳过而没生成 plan，该项就为空。

### Q: Plan Reflection 评分什么时候出现？

**A:** 仅当 topic 配置了 `user_feedback` 和 `expected_intent` 字段时才会执行 plan reflection 评估。如果没有配置这两个字段（如基础测试用例），该项不会出现在报告中，agent 使用两阶段自动确认流程。

### Q: 引用逐条检查为什么不总是出现？

**A:** 仅当最终报告包含引用标记（`[label](url)` 格式）且来源列表非空时才执行。如果报告很短或没有引用，该项分数不会出现在报告中。

### Q: 如何将评估加入 CI？

**A:** 组件级评估虽然侧重对各节点的独立评分，但评估过程仍然需要运行完整的 agent 管道（包括网络搜索和 LLM 调用），因此 CI 环境需要配置好 `APP_TOKEN`、`LLM_BASE_URL`、`MCP_APP_ID` 等环境变量和网络访问权限。如条件允许，可在 CI 中运行：
```bash
python -m eval.run_eval --mode comp --topic "xxx" --output ci_report.json
```
然后解析 JSON 中的各维度 `overall_score` 做阈值检查。如果 CI 环境不具备完整的网络条件，建议仅在本地开发环境中运行评估。
