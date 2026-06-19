"""用于评估 DeepResearch Agent 输出的 Judge 提示词。

在两个层级进行评估：
  - 组件级：各个节点输出
  - 端到端：最终研究报告质量
"""

# ============================================================
# 端到端报告评估
# ============================================================

E2E_JUDGE_INSTRUCTIONS = """# 任务说明
你是一个专业的科研评审专家。现在你需要对一份AI生成的研究报告进行质量评估。

# 评分维度
请从以下5个维度对报告进行评分，每个维度1-5分：

1. **事实准确性 (Factual Accuracy)**
   - 报告中的陈述是否能被提供的搜索来源支撑？
   - 是否存在虚构的数据、事件或引用？
   - 引用是否真实可查？
   - 5分: 所有关键陈述均有来源支撑，无幻觉
   - 1分: 大量无依据的陈述或明显错误

2. **信息覆盖度 (Information Coverage)**
   - 是否覆盖了研究主题的所有关键方面？
   - 是否遗漏了重要维度？
   - 5分: 全面覆盖主题所有关键维度
   - 1分: 仅涉及极少数方面，遗漏严重

3. **逻辑结构 (Logical Structure)**
   - 报告组织是否清晰？论证是否连贯？
   - 标题层级是否合理？各部分之间是否有逻辑递进？
   - 5分: 结构严谨，逻辑清晰，层层递进
   - 1分: 结构混乱，逻辑断裂

4. **时效性 (Timeliness)**
   - 是否使用了最新信息？
   - 数据和案例是否为近期？
   - 是否考虑了当前时间背景？
   - 5分: 信息均在近期，充分体现时效性
   - 1分: 信息陈旧，未考虑时效性

5. **引用质量 (Citation Quality)**
   - 引用是否恰当标注？
   - 来源是否可信（权威媒体、学术来源 vs 个人博客）？
   - 引用格式是否规范？
   - 5分: 引用规范，来源可信，标注清晰
   - 1分: 无引用或引用来源为不可信来源

# 输出格式
请输出一个标准的JSON对象，包含以下字段：

```json
{
  "factual_accuracy": {"score": 4, "reason": "..."},
  "information_coverage": {"score": 3, "reason": "..."},
  "logical_structure": {"score": 4, "reason": "..."},
  "timeliness": {"score": 3, "reason": "..."},
  "citation_quality": {"score": 4, "reason": "..."},
  "overall_score": 3.6,
  "overall_assessment": "对报告的整体评价，包括主要优点和需要改进的方面",
  "hallucination_check": {
    "has_hallucinations": false,
    "details": "如果没有幻觉则为空字符串，如果有则列出具体幻觉内容"
  }
}
```

# 研究主题
{research_topic}

# 搜索来源（用于判断事实准确性）
{search_sources}

# 待评估的报告
{report}

# 输出"""


# ============================================================
# 组件级：计划生成
# ============================================================

PLAN_JUDGE_INSTRUCTIONS = """# 任务说明
评估AI生成的研究计划的合理性。研究计划应该在开始搜索前帮助澄清用户需求。

# 评分维度
1. **需求覆盖率 (Requirement Coverage)**: 是否覆盖了5大关键要素？(1-5分)
2. **问题清晰度 (Question Clarity)**: 追问是否精准、具体、有引导性？(1-5分)
3. **结构合理性 (Structure Quality)**: 计划是否清晰可执行？(1-5分)

# 输出格式
```json
{
  "requirement_coverage": {"score": 4, "reason": "..."},
  "question_clarity": {"score": 4, "reason": "..."},
  "structure_quality": {"score": 3, "reason": "..."},
  "overall_score": 3.67,
  "missing_dimensions": ["维度1", "维度2"],
  "assessment": "整体评价..."
}
```

# 研究主题
{research_topic}

# 生成的计划
{plan}

# 输出"""


# ============================================================
# 组件级：搜索查询质量
# ============================================================

QUERY_JUDGE_INSTRUCTIONS = """# 任务说明
评估AI为研究主题生成的搜索查询质量。

# 评分维度
1. **覆盖度 (Coverage)**: 查询是否覆盖了研究主题的不同维度？(1-5分)
2. **独立性 (Independence)**: 各查询之间是否尽量减少冗余？(1-5分)
3. **搜索友好性 (Search-friendliness)**: 查询是否适合搜索引擎（关键词、具体而非笼统）？(1-5分)

# 输出格式
```json
{
  "coverage": {"score": 4, "reason": "..."},
  "independence": {"score": 4, "reason": "..."},
  "search_friendliness": {"score": 3, "reason": "..."},
  "overall_score": 3.67,
  "missing_angles": ["角度1", "角度2"],
  "assessment": "整体评价..."
}
```

# 研究主题
{research_topic}

# 生成的搜索查询
{queries}

# 查询生成的理由
{rationale}

# 输出"""


# ============================================================
# 组件级：搜索结果摘要保真度
# ============================================================

SUMMARIZATION_JUDGE_INSTRUCTIONS = """# 任务说明
评估AI对搜索结果的总结是否忠实于原始内容。重点检查是否存在**幻觉**（总结中出现搜索结果中不存在的事实）。

# 评分维度
1. **事实保真度 (Factual Fidelity)**: 总结中的陈述是否能在搜索结果中找到支撑？(1-5分)
2. **关键信息提取 (Key Info Extraction)**: 是否提取了搜索结果中最相关的信息？(1-5分)
3. **来源标注 (Source Attribution)**: 是否正确标注了信息来源？(1-5分)

# 输出格式
```json
{
  "factual_fidelity": {"score": 4, "reason": "..."},
  "key_info_extraction": {"score": 4, "reason": "..."},
  "source_attribution": {"score": 3, "reason": "..."},
  "overall_score": 3.67,
  "hallucinations": ["幻觉1", "幻觉2"],
  "assessment": "整体评价..."
}
```

# 搜索主题
{search_query}

# 原始搜索结果
{raw_search_results}

# AI生成的总结
{summary}

# 输出"""


# ============================================================
# 组件级：反思 / 充足性判断质量
# ============================================================

CRITIQUE_JUDGE_INSTRUCTIONS = """# 任务说明
评估AI对信息收集进度的反思是否正确。核心判断：AI对"信息是否充足"的判断是否合理。

# 评分维度
1. **充足性判断准确度 (Sufficiency Judgment)**: is_sufficient的判断是否正确？(1-5分)
2. **差距识别 (Gap Identification)**: 如果判断为不充足，knowledge_gap描述是否准确？(1-5分)
3. **后续查询质量 (Follow-up Query Quality)**: follow_up_queries是否能有效弥补知识差距？(1-5分)

# 输出格式
```json
{
  "sufficiency_judgment": {"score": 4, "reason": "..."},
  "gap_identification": {"score": 4, "reason": "..."},
  "follow_up_query_quality": {"score": 3, "reason": "..."},
  "overall_score": 3.67,
  "is_sufficiency_correct": true,
  "assessment": "整体评价..."
}
```

# 研究主题
{research_topic}

# 已收集的所有信息摘要
{summaries}

# AI的反思结果
is_sufficient: {is_sufficient}
knowledge_gap: {knowledge_gap}
follow_up_queries: {follow_up_queries}

# 输出"""


# ============================================================
# 组件级：引用准确性
# ============================================================

CITATION_JUDGE_INSTRUCTIONS = """# 任务说明
你是一个严格的学术审稿人。你需要逐条核查研究报告中每一个引用标记，判断：
1. 该引用URL是否真实存在于来源列表中
2. 该引用所在段落的论点是否与来源标题/内容相符（即引用是否支撑了段落论点）

# 具体操作
- 先扫描报告，提取所有引用标记（格式如 `[label](url)` 或 `[label](https://...)`）
- 对每个引用，定位其所在的段落（该引用前后最近的完整段落）
- 在来源列表中查找该URL
- 判断：该段落的论点是否与来源的label或title语义相关

# 判断标准
- **有效引用 (valid)**: URL在来源列表中，且段落论点与来源标题/内容明显相关
- **无效-URL不存在 (url_not_found)**: URL不在来源列表中
- **无效-内容不支撑 (content_mismatch)**: URL存在，但段落论点与来源内容不相关或矛盾
- **弱引用 (weak)**: URL存在且相关，但引用的方式过于笼统（如整段只有一个引用标记放在末尾，而段落包含多个独立事实）

# 输出格式
```json
{
  "total_citations": 10,
  "valid_citations": 6,
  "weak_citations": 1,
  "invalid_citations": 3,
  "per_citation": [
    {
      "url": "https://search.com/id/1-0",
      "label": "[来源标签]",
      "paragraph_summary": "引用所在段落的简要概括（1句话）",
      "source_title": "来源列表中的标题",
      "status": "valid",
      "reason": "段落讨论X，来源正是关于X的报道，引用恰当"
    },
    {
      "url": "https://search.com/id/2-1",
      "label": "[另一个标签]",
      "paragraph_summary": "段落讨论Y策略",
      "source_title": "来源列表中对应的标题",
      "status": "content_mismatch",
      "reason": "段落讨论Y策略，但来源内容是关于Z技术的，两者不相关"
    },
    {
      "url": "https://fake-url.com",
      "label": "[虚构来源]",
      "paragraph_summary": "...",
      "source_title": "（未找到）",
      "status": "url_not_found",
      "reason": "该URL不在提供的来源列表中"
    }
  ],
  "citation_accuracy_score": 3,
  "summary_stats": {
    "valid_rate": 0.6,
    "most_common_issue": "url_not_found",
    "worst_offender_url": "https://fake-url.com"
  },
  "assessment": "整体评价：6/10个引用有效，2个URL不在列表中，1个……"
}
```

# 来源列表
{sources}

# 研究报告（全文）
{report}

# 注意
`citation_accuracy_score` 必须是 1 到 5 的整数评分，不要使用 10 分制、百分制或 0-100 分。

# 输出"""


# ============================================================
# 组件级：计划 → 查询对齐
# ============================================================

PLAN_QUERY_ALIGNMENT_JUDGE_INSTRUCTIONS = """# 任务说明
评估从研究计划到搜索查询的衔接质量。一个好的研究计划应该能自然地派生出覆盖全面的搜索查询。

# 评分维度
1. **覆盖一致性 (Coverage Consistency)**: 搜索查询是否覆盖了研究计划中列出的所有关键维度？(1-5分)
   - 5分: 计划中每个关键维度都有对应的搜索查询
   - 1分: 大部分计划维度在查询中没有体现

2. **计划忠实度 (Plan Fidelity)**: 搜索查询是否忠实于计划的边界定义（时间范围、媒体范围、分析重点等）？(1-5分)
   - 5分: 所有查询均遵循计划中的约束条件
   - 1分: 查询超出计划边界或忽略重要约束

3. **结构化拆解 (Structural Decomposition)**: 搜索查询是否对计划进行了合理的分解，而非简单照搬计划中的标题？(1-5分)
   - 5分: 查询将计划中的每个维度细化为可搜索的具体问题
   - 1分: 查询只是计划标题的简单复制

# 输出格式
```json
{
  "coverage_consistency": {"score": 4, "reason": "计划中有5个关键维度，查询覆盖了4个，遗漏了'风险研判'维度"},
  "plan_fidelity": {"score": 3, "reason": "计划要求聚焦2025年，但查询1和查询3未包含时间限定"},
  "structural_decomposition": {"score": 4, "reason": "查询基本合理拆解了计划维度，但查询2与查询3存在语义重叠"},
  "overall_score": 3.67,
  "covered_dimensions": ["维度1", "维度2"],
  "missed_dimensions": ["维度3"],
  "cross_reference_table": [
    {"plan_dimension": "核心分析对象-产品对比", "matching_queries": ["查询1", "查询3"], "coverage": "full"},
    {"plan_dimension": "对手策略维度", "matching_queries": ["查询2"], "coverage": "partial"},
    {"plan_dimension": "风险研判维度", "matching_queries": [], "coverage": "missed"}
  ],
  "assessment": "整体评价：计划到查询的衔接质量中等，主要问题是..."
}
```

# 研究计划
{plan}

# 生成的搜索查询
{queries}

# 输出"""


# ============================================================
# 组件级：计划反思 / 需求澄清
# ============================================================

PLAN_REFLECTION_JUDGE_INSTRUCTIONS = """# 任务说明
评估AI在需求澄清阶段对用户反馈的处理质量。用户在看到研究计划后给出了反馈，AI需要判断用户的意图（确认继续还是需要修改计划），并在必要时重新生成计划。

# 评分维度

1. **意图识别准确性 (Intent Recognition)**: AI是否正确识别了用户反馈的意图？（1-5分）
   - 用户表达了确认/满意 → AI应该继续执行
   - 用户提出了具体的修改要求或否定 → AI应该重新生成计划
   - 5分: 完全正确识别了用户意图
   - 1分: 完全误判了用户意图（用户要求修改却继续执行，或用户确认了却不必要地重新计划）

2. **反馈吸收质量 (Feedback Incorporation)**: 若发生了重新计划，新计划是否真正回应了用户的反馈？（1-5分）
   - 用户的每个具体关切是否在新计划中得到体现？
   - 修改是针对性调整还是敷衍的表面改动？
   - 新计划是否在解决用户关切的同时保留了原计划的合理部分？
   - 注意：若系统正确判断用户确认（未发生重新计划），本维度给5分（没有需要吸收的反馈，行为完全正确）

3. **计划连贯性 (Plan Coherence)**: 若发生重新计划，新计划是否保持了良好的结构和可执行性？若未发生重新计划，原计划本身是否已足够覆盖用户需要的澄清点？（1-5分）

# 输出格式
```json
{
  "intent_recognition": {"score": 4, "reason": "用户反馈中明确表达了'方向对的'表示基本满意..."},
  "feedback_incorporation": {"score": 4, "reason": "新计划中增加了相关维度，且保留了原计划的框架..."},
  "overall_score": 4.0,
  "actual_behavior": "replan_then_proceed",
  "assessment": "整体评价..."
}
```

# 背景信息

## 原始研究计划（用户反馈前的计划）
{original_plan}

## 用户反馈
{user_feedback}

## 系统行为
系统实际行为: {actual_behavior}
预期行为: {expected_intent}

## 重新生成的计划（若发生replan；若未replan则为空）
{new_plan}

# 输出"""
