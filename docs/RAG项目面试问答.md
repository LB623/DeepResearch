# DeepResearch 项目 RAG 面试问答

## 项目定位

这个项目可以定位为：

**一个面向 Deep Research Agent 的事实级 Memory-Augmented RAG 系统：用 Milvus 存储研究过程中抽取的 facts，在下一轮研究 query 生成前做语义召回，用已有事实增强搜索规划。**

它不是传统“上传文档问答型 RAG”，而是面向研究型 Agent 的长期知识记忆系统。

## 1. 你这个项目里的 RAG 是怎么设计的？

答：

我这个项目不是传统“上传文档问答型 RAG”，而是一个 **Deep Research 场景下的事实级 RAG / 记忆增强 RAG**。

整体流程是：

```text
用户研究需求
-> 生成研究计划
-> 进入 ResearchAgent
-> 查询 Milvus 中已有相关 facts
-> 把 facts 注入 query 生成 prompt
-> 生成搜索 query
-> Web 搜索
-> LLM 汇总搜索结果
-> FactExtractor 抽取结构化事实
-> 写入 Milvus
-> WriterAgent 基于搜索摘要生成报告
```

也就是说，Milvus 里的知识主要用于 **增强搜索 query 规划**，帮助系统避免重复搜索、补充历史上下文，而不是直接拿来生成最终答案。

## 2. 你的 RAG 属于哪种检索？

答：

主要是 **事实级语义向量检索**，也可以叫 **Memory-Augmented RAG** 或 **Agentic RAG 中的记忆检索模块**。

它的特点是：

```text
检索对象：LLM 抽取出的 fact，不是原始文档 chunk
检索方式：embedding + Milvus + COSINE 相似度
增强位置：query 生成阶段，而不是最终回答阶段
过滤逻辑：confidence、新鲜度、fact_category 生命周期
```

所以它不是标准的文档 QA RAG，而是面向研究型 Agent 的长期知识记忆。

## 3. 为什么你没有用传统文档 chunk RAG？

答：

因为项目目标不是做“文档问答”，而是做“自动深度研究报告”。

如果直接存网页 chunk，会有几个问题：

- 网页搜索结果噪声很大，chunk 里会包含很多无关内容。
- 报告研究更需要可验证的结论性事实，而不是长文本片段。
- 多轮研究时，复用的是“已有事实”，不是原文全文。
- 存 fact 可以降低 token 成本，也方便做置信度、时效性、来源管理。

所以我选择：

```text
搜索结果 -> LLM 摘要 -> FactExtractor 抽取 facts -> Milvus 存 facts
```

而不是：

```text
网页正文 -> 切 chunk -> 存向量库
```

## 4. 为什么不用关键词检索或者 BM25？

答：

当前项目里的 facts 是短文本、语义浓缩后的事实，很多时候用户 query 和 fact 不会有明显关键词重合。

例如 Milvus 里可能有 fact：

```text
DeepSeek 正在组建 Harness 团队，目标是对标 Claude Code。
```

用户可能问：

```text
国内大模型厂商在 AI 编程智能体方向有什么布局？
```

这两个文本关键词重合不高，但语义相关。BM25 主要依赖词面匹配，容易漏召回；向量检索更适合这种语义泛化场景。

另外，中文 + 英文混合技术词也会让 BM25 依赖分词质量，比如：

```text
AI编程助手 / 代码智能体 / Code Harness / Claude Code
```

当然，BM25 不是没价值。后续更好的方案是做 **Hybrid Retrieval**：

```text
向量检索召回语义相关 facts
+
BM25 召回强关键词、产品名、人名、版本号
+
metadata filter
+
reranker 重排
```

## 5. Milvus 里存的是什么数据？

答：

Milvus collection 叫 `research_facts`，每条数据是一条结构化事实。核心字段包括：

```python
{
    "vector": embedding,
    "fact_text": "事实文本",
    "source_url": "来源 URL",
    "research_topic": "来源研究主题",
    "confidence": 0.0-1.0,
    "fact_category": "market_data/product_info/strategy/technology/historical",
    "created_at": timestamp
}
```

其中：

- `vector` 用于语义检索。
- `fact_text` 是实际召回内容。
- `source_url` 用于溯源。
- `confidence` 用于过滤低质量事实。
- `fact_category` 和 `created_at` 用于时效性管理。

## 6. 你的 RAG 如何保证召回内容不过时？

答：

我做了 facts 生命周期管理。不同类型的事实有不同 TTL：

```text
market_data: 7 天
product_info: 30 天
strategy: 90 天
technology: 180 天
historical: 永不过期
```

比如市场份额、价格、排名变化很快，所以 `market_data` 只保留 7 天；而历史事件和技术原理变化慢，不应该频繁过期。

查询时会根据模式做过滤或置信度衰减：

```text
freshness 模式：按任务新鲜度统一过滤
lifecycle 模式：按 fact_category 分类别过滤
inform 模式：只提示年龄，不过滤
off 模式：完全关闭时效控制
```

## 7. RAG 召回结果具体怎么进入 Agent？

答：

在 `ResearchAgent._generate_queries()` 中，系统会先根据研究主题查询 Milvus：

```text
topic -> embedding -> Milvus search -> hits
```

然后把召回的 facts 拼成 `known_facts_text`，注入 query 生成 prompt：

```text
## 知识库中已有的相关事实
- [90%] xxx fact (来源: xxx)
- [80%] xxx fact (来源: xxx)
```

再让 query generator 基于这些已知事实生成搜索 query。

所以 RAG 增强点是：

```text
retrieved facts -> query planning prompt
```

不是：

```text
retrieved facts -> final answer prompt
```

## 8. Redis 和 Milvus 的区别是什么？

答：

Redis 是短期搜索缓存，Milvus 是长期事实知识库。

区别：

```text
Redis:
- 存 Web 搜索原始结果
- key 是 prompt + count 的 hash
- 默认 TTL 1 小时
- 目的是减少重复调用搜索 API

Milvus:
- 存 LLM 抽取出来的 facts
- 用 embedding 做语义检索
- 可长期复用
- 目的是增强后续研究任务
```

所以 Redis 不属于 RAG 知识库，它只是搜索缓存层。

## 9. 你的系统怎么降低幻觉？

答：

主要有几层控制：

- facts 必须来自搜索摘要，不是模型凭空生成。
- FactExtractor 要求每条 fact 带 `source_url`。
- 每条 fact 有 `confidence`，低置信度事实会被过滤。
- WriterAgent 写报告时主要基于本轮 `web_search_result`，不是直接依赖记忆 facts。
- Critic 会检查报告内容是否和 summaries 一致，发现无来源数据会要求修改。
- 最终润色阶段会校对 markdown 引用链接。

也就是说，Milvus 记忆用于辅助搜索规划，最终报告仍以本轮搜索证据为主，这能降低旧知识或错误记忆直接污染最终答案的风险。

## 10. 你的 RAG 有什么不足？怎么优化？

答：

当前版本主要不足有几个：

- **只有向量检索，没有 BM25**：对产品名、人名、版本号、政策文件这类精确关键词，BM25 会更稳。后续可以做 Hybrid Retrieval。
- **没有 reranker**：Milvus 返回的是向量相似度结果，可能语义相关但不一定最适合当前任务。可以加 cross-encoder reranker 或 LLM rerank。
- **事实去重还可以加强**：多次搜索可能抽取到相似 facts，后续可以基于 embedding 相似度或文本规范化做去重。
- **没有完整文档级证据链**：当前存的是 fact，不存原网页 chunk。如果要做严格审计，可以同时保存 chunk、网页标题、抓取时间和摘要版本。
- **召回只增强 query 生成**：目前 final report 主要用本轮搜索 summaries。后续可以让 WriterAgent 也读取高置信度 facts，但要加新鲜度和引用校验，避免旧知识污染。

## 11. 如果面试官问：你这个 RAG 最大亮点是什么？

答：

我觉得最大亮点是它不是简单文档问答，而是结合 Agent 工作流做了 **研究过程记忆**。

传统 RAG 是：

```text
问题 -> 检索 -> 回答
```

我的项目是：

```text
研究任务 -> 召回历史 facts -> 规划搜索 query -> 搜索新资料 -> 抽取新 facts -> 写入记忆 -> 生成报告
```

它形成了一个闭环：

```text
检索增强搜索规划
搜索产生新知识
新知识沉淀到向量库
后续任务继续复用
```

所以更接近 Agentic RAG，而不是普通 QA RAG。

## 12. 如果让你现场画架构，可以画这个

```text
                ┌──────────────────┐
                │ 用户研究需求       │
                └─────────┬────────┘
                          │
                          v
                ┌──────────────────┐
                │ Plan Agent        │
                │ 生成/确认研究计划  │
                └─────────┬────────┘
                          │
                          v
┌────────────────────────────────────────────┐
│ ResearchAgent                              │
│                                            │
│  ┌──────────────┐     ┌─────────────────┐ │
│  │ 查询 Milvus   │<────│ research_facts   │ │
│  └──────┬───────┘     │ facts 向量库      │ │
│         │             └─────────────────┘ │
│         v                                  │
│  ┌──────────────┐                         │
│  │ 生成搜索 query │                         │
│  └──────┬───────┘                         │
│         v                                  │
│  ┌──────────────┐                         │
│  │ Web Search    │── Redis cache           │
│  └──────┬───────┘                         │
│         v                                  │
│  ┌──────────────┐                         │
│  │ LLM 汇总摘要   │                         │
│  └──────┬───────┘                         │
│         v                                  │
│  ┌──────────────┐                         │
│  │ 抽取 facts    │                         │
│  └──────┬───────┘                         │
│         v                                  │
│  ┌──────────────┐                         │
│  │ 写入 Milvus   │                         │
│  └──────────────┘                         │
└────────────────────┬───────────────────────┘
                     v
             ┌──────────────────┐
             │ WriterAgent       │
             │ 基于 summaries 写报告 │
             └──────────────────┘
```

## 面试总结话术

**我的项目不是普通文档问答 RAG，而是 Deep Research Agent 中的事实级记忆 RAG：通过 Milvus 语义召回历史 facts，增强搜索 query 规划，并在研究过程中持续抽取新 facts 写回知识库，形成研究记忆闭环。**
