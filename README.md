<h1 align="center">🔬 DeepResearch</h1>

<p align="center">
  <strong>可恢复、证据优先的多阶段深度研究 Agent</strong><br>
  <sub>融合多源与多媒体检索、事实级长期记忆、双重 Critic 审查和可回查引用</sub>
</p>

<p align="center">
  <a href="#-项目亮点">项目亮点</a> ·
  <a href="#-研究链路">研究链路</a> ·
  <a href="#-系统架构">系统架构</a> ·
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-工程验证">工程验证</a> ·
  <a href="#-项目结构">项目结构</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/LangGraph-Multi--Stage%20Agent-1C3C3C" alt="LangGraph Multi-Stage Agent">
  <img src="https://img.shields.io/badge/Frontend-React%2019-61DAFB?logo=react&logoColor=black" alt="React 19">
  <img src="https://img.shields.io/badge/Retrieval-DashScope%20%2B%20OmniSeek-177D6B" alt="DashScope and OmniSeek retrieval">
  <img src="https://img.shields.io/badge/Memory-Milvus-00A1EA" alt="Milvus Fact Memory">
  <img src="https://img.shields.io/badge/Recovery-Redis%20Checkpoint-DC382D?logo=redis&logoColor=white" alt="Redis Checkpoint">
  <img src="https://img.shields.io/badge/Quality-make%20verify-brightgreen" alt="make verify">
</p>

<p align="center">
  <strong>问题输入</strong> → <strong>计划确认</strong> → <strong>多源检索</strong> → <strong>证据反思</strong> → <strong>审查修订</strong> → <strong>引用归一化</strong>
</p>

<p align="center">
  <img src="./docs/assets/deepresearch-ui-current.jpg" width="92%" alt="DeepResearch 当前研究工作台">
  <br>
  <sub>当前桌面端界面：研究问题、研究深度、模型选择和研究路径均在同一工作台内完成</sub>
</p>

---

## ✨ 项目亮点

![DeepResearch Agent 核心亮点](./docs/assets/deepresearch-highlights-v2.png)

| 🧭 **计划先行** | 🔎 **多源与多媒体检索** |
|---|---|
| 先生成研究计划，支持确认、反馈与重新规划，再进入正式检索。 | DashScope 与 OmniSeek 可按 `augment`、`fallback`、`only` 策略运行；结果统一去重，并保留图片及可转写媒体句柄。 |
| 🧠 **事实级长期记忆** | ✍️ **Writer/Critic 循环** |
| 从 Milvus 召回历史事实，对结果做生命周期过滤、质量重排和去重，再将新事实写回长期记忆。 | Research Critic 判断证据缺口；Writer Critic 对草稿进行审查并触发有限次修订。 |
| 🛡️ **来源与引用防护** | ♻️ **可恢复研究任务** |
| 只把已检索到的真实 URL 写入终稿；数字引用可直接回源，第三方来源显式标记，内部占位链接禁止跳转。 | Redis Checkpoint 持久化图状态和任务预算；前端使用可恢复流继续接收长任务结果。 |
| 📊 **可复现评测** | 🖥️ **可视化交互** |
| 提供 smoke/core/full 固定题集、离线聚合、输出契约、检索 A/B 与故障注入测试。 | 浅色研究工作台展示计划确认、实时路径、结构化 Markdown 报告、媒体证据和来源索引。 |

> 本项目采用事实级 Memory-Augmented RAG，而不是传统的上传文档问答 RAG。Milvus 保存提取后的事实记录，Redis 分别承担搜索缓存与任务 Checkpoint。

### 当前交互流程

1. 在欢迎页输入研究问题，选择研究深度和推理模型。
2. Agent 先返回研究计划；用户确认后才启动正式检索，也可以补充反馈要求重规划。
3. 研究过程中实时展示查询生成、来源汇集、证据反思和终稿整理等节点。
4. 最终报告以结构化 Markdown 展示；数字引用打开真实来源，报告末尾追加系统核验的来源索引。
5. OmniSeek 返回图片、音频或视频句柄时，报告会追加经过 URL 校验的多媒体证据区。

---

## 🔄 研究链路

![DeepResearch Agent 研究链路](./docs/assets/deepresearch-research-flow.png)

---

## 🏗️ 系统架构

![DeepResearch Agent 系统架构](./docs/assets/deepresearch-system-architecture.svg)

### 核心数据边界

- **Milvus**：跨任务长期事实记忆与语义召回。
- **Redis Search Cache**：短期缓存网页搜索结果，减少重复外部调用。
- **LangGraph Checkpoint**：保存任务图状态，用于失败恢复和任务续跑。

### 失败与降级语义

| 依赖 | 失败时行为 |
|---|---|
| Redis Search Cache | 自动降级为进程内缓存；只影响跨进程复用和重启后命中率。 |
| Redis Checkpoint | 默认失败关闭（fail closed），避免把不可恢复的任务误报为可恢复。仅本地开发可显式设置 `CHECKPOINT_FALLBACK_TO_MEMORY=1`。 |
| Milvus 事实记忆 | 不中断当前研究；暂停长期记忆读写，并按 `KB_RECONNECT_INTERVAL_SECONDS` 定期重连。 |
| OmniSeek 检索 | 与现有 DashScope 检索隔离；单次超时或协议错误只记录安全错误类型，并保留其他提供方的结果。未配置时自动使用 DashScope。 |

Web Search 次数、LLM token、墙钟时间和无进展轮数等单任务预算记录在 LangGraph state 中，因此从 Checkpoint 恢复不会重置预算。
环境变量中的预算值同时是服务端上限：请求可通过 `configurable` 降低预算，但不能将其提高到服务端上限之上。

---

## 🧰 技术栈

| 模块 | 技术 |
|---|---|
| Agent 编排 | LangGraph、LangChain |
| 后端 | Python 3.11+、FastAPI、LangGraph API |
| 模型与检索接入 | OpenAI-compatible API、DashScope Application、OmniSeek MCP（可选） |
| 长期记忆 | Milvus、PyMilvus、Embedding API |
| 缓存与恢复 | Redis、langgraph-checkpoint-redis |
| 前端 | React 19、TypeScript、Vite、Tailwind CSS |
| 评测 | Pytest、LLM-as-Judge、固定题集 A/B Benchmark |

---

## 🚀 快速开始

### 环境要求

- Python `3.11+`
- Node.js `22`
- Docker 与 Docker Compose
- OpenAI-compatible LLM 和 Embedding 服务
- 至少一个检索提供方：DashScope Application 或自托管 OmniSeek MCP

### 1. 安装依赖

进入项目根目录后执行：

```bash
python3.11 -m pip install uv==0.11.1
UV_PROJECT_ENVIRONMENT="$PWD/.venv" \
  uv sync --project backend --extra dev --frozen

cd frontend
npm ci
cd ..
```

### 2. 启动 Milvus 与 Redis

```bash
docker compose -f infrastructure/milvus/docker-compose.yml up -d
docker compose -f infrastructure/redis/docker-compose.yml up -d
```

Checkpoint 使用 Redis Search 索引，因此必须使用 Redis Stack；普通
`redis:7-alpine` 不支持 `FT._LIST`，不能用于 `CHECKPOINT_BACKEND=redis`。
如果本机已有启用 Redis Search 的兼容服务，可跳过第二条命令。

如需启用多源感知检索，再启动独立的 OmniSeek sidecar：

```bash
make omniseek-up
curl -fsS http://127.0.0.1:8765/healthz
```

镜像固定到 OmniSeek `v0.2.0` 的多架构 OCI digest，端口只绑定本机回环地址。
`make omniseek-up` 会先以当前宿主用户在
`infrastructure/omniseek/data/credentials/omniseek_http.json` 安静生成独立 bearer token，
再启动容器；token 不会进入 Docker 日志，原生 Linux 上也不会产生 `0600 root:root`
导致后端不可读的问题。仓库内运行时会自动发现该文件；其他部署布局可设置
`OMNISEEK_TOKEN_FILE`。凭证目录已被 Git 忽略，不要把 token 提交到仓库。

需要轮换 token 时执行 `make omniseek-rotate-token`；该命令会使现有客户端连接失效并重建 sidecar。

### 3. 配置环境变量

以仓库中的完整模板创建 `backend/.env`：

```bash
cp backend/.env.example backend/.env
```

然后按实际部署替换模型、检索与存储配置。下面同时展示 DashScope 与 OmniSeek；如果使用
`OMNISEEK_MODE=only`，可以不配置 DashScope：

```dotenv
# 研究模型 / 推理模型
RESEARCH_LLM_MODEL=your-research-model
RESEARCH_LLM_API_KEY=your-api-key
RESEARCH_LLM_BASE_URL=https://your-llm-endpoint/v1

REASONING_LLM_MODEL=your-reasoning-model
REASONING_LLM_API_KEY=your-api-key
REASONING_LLM_BASE_URL=https://your-llm-endpoint/v1

# DashScope 应用与网页搜索
MCP_API_KEY=your-dashscope-api-key
MCP_APP_ID=your-web-search-application-id

# 可选 OmniSeek sidecar；token 取自首次启动生成的 omniseek_http.json
OMNISEEK_MCP_URL=http://127.0.0.1:8765/mcp
OMNISEEK_TOKEN_FILE=../infrastructure/omniseek/data/credentials/omniseek_http.json
OMNISEEK_MODE=augment
OMNISEEK_RESULT_LIMIT=5
OMNISEEK_WAIT_SECONDS=3
OMNISEEK_REQUEST_TIMEOUT_SECONDS=12
OMNISEEK_MAX_CONCURRENCY=8
DASHSCOPE_MAX_CONCURRENCY=8
SEARCH_PROVIDER_TIMEOUT_SECONDS=30

# Redis 搜索缓存与任务检查点
REDIS_URL=redis://localhost:6379/0
CHECKPOINT_BACKEND=redis
CHECKPOINT_REDIS_URL=redis://localhost:6379/0
CHECKPOINT_FALLBACK_TO_MEMORY=0

# Milvus 事实记忆
MILVUS_URI=http://localhost:19530
MILVUS_COLLECTION=research_facts

# OpenAI 兼容的向量嵌入服务
EMBEDDING_BASE_URL=https://your-embedding-endpoint/v1
EMBEDDING_API_KEY=your-embedding-api-key
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIM=1024

# 单任务研究预算
NUMBER_OF_INITIAL_QUERIES=2
MAX_RESEARCH_LOOPS=2
MAX_WEB_SEARCH_CALLS=20
MAX_OMNISEEK_CALLS=4
MAX_TOTAL_TOKENS=120000
MAX_ELAPSED_SECONDS=900
MAX_NO_PROGRESS_ROUNDS=2
MAX_WRITER_REVISIONS=3

# 事实记忆生命周期与重连
KB_RECONNECT_INTERVAL_SECONDS=30
KB_LIFECYCLE_MODE=freshness
KB_RERANK_ENABLED=1
KB_RERANK_CANDIDATE_MULTIPLIER=3

# 默认不记录请求正文
LOG_REQUEST_BODY=0
```

`OMNISEEK_MODE` 和 `OMNISEEK_SOURCES` 是服务端部署策略，不接受客户端
`RunnableConfig` 覆盖。`OMNISEEK_SOURCES` 最多配置 16 个名称；留空时由 OmniSeek
profile 决定可用源。`only` 模式在凭证缺失、配置非法或预算耗尽时会停止检索，绝不
把查询隐式发送给 DashScope。

搜索次数预算随 LangGraph checkpoint 持久化，约束的是已提交的逻辑调用。外部 MCP
调用、Milvus 写入与 Redis checkpoint 无法跨系统原子提交；若进程恰好在外部副作用
完成后、checkpoint 提交前崩溃，恢复可能重放该节点。对严格计费或 exactly-once 有要求
的部署仍应在外部服务侧使用幂等键或独立的持久调用账本。

> `EMBEDDING_DIM` 必须与 Embedding 模型的实际输出维度及 Milvus Collection 维度一致。
> `backend/.env.example` 是配置项的唯一完整清单，其中还包含可选模型列表、Web Search 限流和生命周期模式说明。

生产部署验收或排查连通性时，可执行 KB 就绪检查：

```bash
cd backend
../.venv/bin/python -m agent.kb.preflight
cd ..
```

命令会分别检查 Milvus 与 Embedding，并在任一依赖不可用时返回非零退出码。这是部署就绪探针，不是运行时的强制启动门禁：Milvus 暂时不可用时，Agent 仍可继续研究并在冷却期后重连。Embedding 检查会发送一条固定探针文本，可能产生一次极小的 API 调用费用。

启用 OmniSeek 后，使用真实 MCP 初始化、鉴权和固定检索请求验收服务：

```bash
cd backend
../.venv/bin/python -m agent.retrieval_preflight
cd ..
```

该探针不输出 token、查询正文、响应正文或内部异常，只输出文档数与来源名；检索会产生真实外部网络请求。

如需验收图片和音视频句柄是否能进入最终报告，参见
[多媒体检索测试](docs/multimodal-search-test.md)。

### 4. 启动应用

分别在两个终端运行：

```bash
# 终端 1：启动 LangGraph 后端
./run_backend.sh
```

```bash
# 终端 2：启动 React 前端
./run_frontend.sh
```

默认地址：

- 🌐 Web UI: [http://localhost:5173/app/](http://localhost:5173/app/)
- 🔗 LangGraph API: [http://localhost:2024](http://localhost:2024)
- 🧩 LangGraph Studio: [https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024](https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024)

---

## 📊 工程验证

项目保留固定题集、原始 JSON 结果和评测报告。以下结果只代表对应实验范围，不外推为通用生产指标。

| 验证项 | 结果 | 说明 |
|---|---|---|
| 查询去重 A/B | 状态查询重复率 `50% → 0%` | 10 个固定主题均成功完成；平均状态查询数 `6 → 3` |
| Checkpoint 故障恢复 | Web Search 调用 `6 → 3` | Critique 节点故障后恢复，最终执行查询数保持为 3 |
| Prompt Quality Guards | 幻觉题数 `3/5 → 0/5` | 事实约束增强，但固定集均分 `4.36 → 4.24`，综合质量仍需优化 |
| Milvus 质量重排 | NDCG@5 `24.6% → 39.4%` | 70 个冻结查询、1,000 条受控事实；重复率 `29.4% → 0%` |
| Writer 对抗语料 | 39/39 判定正确 | 确定性输出契约语料；不调用模型，不代表线上报告整体质量 |

详细报告：

- [查询去重 Benchmark](./docs/reviews/2026-06-16-agent-harness-benchmark.md)
- [Checkpoint Resume Benchmark](./docs/reviews/2026-06-16-agent-checkpoint-resume-benchmark.md)
- [Prompt Quality Guards E2E A/B](./docs/reviews/2026-06-18-prompt-quality-guards-e2e-ab.md)
- [Milvus 检索重排 A/B](./docs/reviews/2026-08-16-milvus-retrieval-rerank-v2.md)
- [Writer 输出契约对抗评测](./docs/reviews/2026-08-16-writer-guard-corpus.md)
- [固定 E2E 评测集设计与成本边界](./docs/reviews/2026-08-19-e2e-fixed-set.md)

### 运行测试与评测

```bash
# 默认交付门禁：锁文件、后端测试/lint/typecheck、前端 lint/test/build
make verify

# 单独运行后端单元测试与回归测试
make backend-test

# 固定题集端到端与组件级评测
cd backend
../.venv/bin/python -m eval.run_eval \
  --mode e2e \
  --test-set test_set_e2e.json \
  --tier smoke \
  --output eval_runs/local_eval.json

# 不调用外部服务的 Writer 输出契约对抗评测
../.venv/bin/python -m eval.run_guard_eval

# 查询去重 A/B 基准测试
../.venv/bin/python -m eval.run_benchmark --variant both

# Checkpoint 故障注入基准测试
../.venv/bin/python -m eval.run_resume_benchmark
```

> 端到端评测会调用真实 LLM、Web Search 和 Milvus。运行前请检查服务连通性、API 配额，并为评测使用独立的 Milvus Collection。
> `make verify` 不调用上述付费外部服务；CI 使用 `backend/uv.lock` 的 frozen 环境。

---

## 📁 项目结构

```text
DeepResearch/
├── backend/
│   ├── src/agent/
│   │   ├── graph.py                 # 主图：计划、研究、写作
│   │   ├── budget.py                # 单任务搜索/token/时间预算
│   │   ├── checkpoint.py            # Redis/Memory Checkpoint
│   │   ├── resume.py                # 任务恢复辅助接口
│   │   ├── retrieval.py             # DashScope/OmniSeek 协调、超时、去重与媒体结果
│   │   ├── retrieval_preflight.py   # OmniSeek MCP 检索验收探针
│   │   ├── multimodal_preflight.py  # 图片与音视频句柄验收探针
│   │   ├── sub_agents/
│   │   │   ├── research_agent.py    # 查询、检索、事实记忆、反思
│   │   │   └── writer_agent.py      # 大纲、草稿、审查、终稿
│   │   ├── kb/                       # Milvus 事实存储、就绪检查与重连
│   │   ├── search_cache.py          # Redis 搜索缓存
│   │   └── llm/llm.py               # OpenAI-compatible LLM
│   ├── eval/                         # 评测框架与 Benchmark
│   ├── eval_runs/                    # 固定集原始结果
│   └── test/                         # 单元与回归测试
├── frontend/                         # React + Vite Web UI
├── infrastructure/
│   ├── milvus/                       # Milvus Docker Compose
│   ├── omniseek/                     # 固定版本的 OmniSeek MCP sidecar
│   └── redis/                        # Redis Stack Docker Compose
├── docs/
│   ├── assets/                       # README 图片与架构图
│   ├── plans/                        # 已接受的工程设计与测试缝
│   └── reviews/                      # 工程验证报告
├── Makefile                         # 非付费交付门禁
├── run_backend.sh
└── run_frontend.sh
```

---

## 🎯 示例研究问题

```text
规范驱动开发（SDD）与 AGENTS.md 的关系是什么？
请结合工程实践、工具链、风险和真实案例生成一份带来源引用的研究报告。
```

---

## ⚠️ 当前边界

- Web Search 至少需要 DashScope Application 或自托管 OmniSeek MCP；两者同时配置时默认并行增强并去重。
- Milvus 保存提取后的事实记录，不保存原始文档 Chunk。
- 当前的“多媒体”指 Agent 能检索并展示 OmniSeek 返回的图片、音频和视频证据句柄，不等同于用户上传图片/视频后进行视觉问答。
- 引用归一化保证链接来自当次检索并阻断内部占位跳转，但不自动证明每个自然语言结论都被对应来源充分蕴含；关键结论仍需人工回查原始来源。
- Checkpoint 提供状态恢复而非跨 Redis、Milvus 与外部 MCP 的 exactly-once 事务；进程在外部副作用完成后崩溃时，节点仍可能被重放。
- Prompt Quality Guards 已增强事实约束，但覆盖度、时效性和来源分级仍需继续优化。
- 生产部署前需要补充鉴权、密钥管理、监控和更严格的安全策略。

---

## 第三方项目与致谢

本项目的多源及多媒体检索能力引用并集成了
[Battam1111/omniseek](https://github.com/Battam1111/omniseek)。OmniSeek 作为独立的
MCP sidecar 提供搜索结果、媒体资产和可转写媒体句柄；DeepResearch 负责调用边界、预算、
来源归一化、报告引用与前端呈现。

- 上游项目：[https://github.com/Battam1111/omniseek](https://github.com/Battam1111/omniseek)
- 上游许可证：[Apache License 2.0](https://github.com/Battam1111/omniseek/blob/main/LICENSE)
- 当前部署固定使用 OmniSeek `v0.2.0` OCI 镜像及其镜像摘要，以保证可复现性。

OmniSeek 的项目名称、源代码和商标归其原作者及贡献者所有；本项目与 OmniSeek 上游不存在
官方隶属或背书关系。
