# DeepResearch 工程加固设计

- 状态：Implemented
- 日期：2026-07-28
- 范围：日志安全、持久化降级、统一验证、依赖与框架迁移、Agent 预算、前端测试与性能
- 实施方式：文档先行，按垂直切片执行 TDD；每个阶段独立可验证、可回滚

## 1. 背景

DeepResearch 已具备完整的 LangGraph 研究链路、Redis Checkpoint、Milvus
事实记忆、固定题集评测和 React 流式界面。当前工程基线如下：

| 项目 | 当前结果 |
|---|---|
| 后端测试 | 275 passed，4 skipped，12 warnings |
| 前端构建 | 通过；主 JS 612.81 KB，gzip 192.49 KB |
| 前端 ESLint | 7 errors，4 warnings |
| 后端 mypy | 40 errors |
| 后端 Ruff | 全量规则 658 条；源码有 10 个明确 F 类错误 |
| CI | 无 |
| 后端锁文件 | 无 |
| 前端测试 | 无 |

本设计不重写 Agent 架构，优先修复会影响隐私、恢复语义、升级安全和持续交付的工程缺口。

## 2. 目标与非目标

### 2.1 目标

1. 默认不把研究内容、凭据或内部异常写入可长期保存的日志或返回客户端。
2. 持久化依赖失败时，运行语义明确：生产失败关闭，开发降级必须显式开启。
3. 建立一个根目录稳定验证入口，并在 CI 中执行同一套非变更型检查。
4. 消除当前 Pydantic、LangGraph 弃用警告，锁定可复现的后端依赖集合。
5. 为长时间研究任务增加搜索次数、token、墙钟时间和无进展停止条件。
6. 覆盖前端关键用户路径，并降低首次加载体积。

### 2.2 非目标

- 本轮不实现用户系统、RBAC、租户隔离或完整生产鉴权。
- 不迁移 Milvus Collection schema，不改写已有事实数据。
- 不修改 Prompt 质量策略和历史 Benchmark 结论。
- 不把真实 LLM、Web Search、Milvus 端到端评测放入每次 CI。
- 不处理或提交根目录现有的 `output/`、`tmp/`。

## 3. 影响面地图

| 维度 | 文件/系统 | 动作 | 验证 | 状态 |
|---|---|---|---|---|
| HTTP 契约 | `backend/src/agent/app.py` | 安全错误响应；请求日志只保留元数据 | FastAPI TestClient 正负向测试 | 必须修改 |
| 日志契约 | `backend/src/agent/logger.py` | 递归脱敏；正文日志默认关闭 | 捕获 Loguru sink，证明秘密不可见 | 必须修改 |
| Checkpoint | `backend/src/agent/checkpoint.py` | Redis 失败默认抛错，内存降级显式开启 | `get_checkpointer()` 配置契约测试 | 必须修改 |
| Milvus 生命周期 | `backend/src/agent/sub_agents/research_agent.py`、新增 provider | 移除永久 `False` sentinel，增加冷却后重连 | Provider 公共接口 + 可控时钟测试 | 必须修改 |
| 搜索缓存 | `backend/src/agent/search_cache.py` | 保留内存降级，因为缓存不是持久状态 | 现有缓存测试 | 已检查，不改语义 |
| 验证入口 | 根 `Makefile` | 统一后端、前端验证命令 | `make verify` | 必须新增 |
| CI | `.github/workflows/verify.yml` | Python 3.11、Node、后端与前端门禁 | GitHub Actions 与本地同命令 | 必须新增 |
| Python 配置 | `backend/pyproject.toml` | 收敛 lint/typecheck 基线，增加依赖范围 | Ruff、mypy、pytest | 必须修改 |
| 依赖锁定 | `backend/uv.lock` | 使用 uv 生成并冻结依赖 | `uv lock --check --project backend` | 必须新增 |
| LangGraph | 主图、Research/Writer 子图 | `config_schema` 迁移为 `context_schema` | 编译、调用与 warnings-as-errors | 必须修改 |
| Pydantic | `backend/src/agent/configuration.py` | `Field(metadata=...)` 迁移为标准字段描述 | 配置 schema 与 warning 测试 | 必须修改 |
| Agent State | `state.py`、各节点 | 增加预算计数和停止原因 | 路由及图级行为测试 | 必须修改 |
| 前端契约 | `App.tsx`、`InputForm.tsx`、`lib/api.ts` | 补类型、关键交互测试、错误降级测试 | Vitest + Testing Library | 必须修改 |
| 前端构建 | `vite.config.ts`、报告视图加载边界 | 延迟加载重组件或显式分包 | `npm run build` 体积结果 | 必须修改 |
| 运行配置 | `.env.example`、README | 记录新安全、持久化和预算变量 | 文档命令和实际字段一致 | 必须修改 |
| Agent 上下文 | 根 `AGENTS.md` | 项目地图、边界、默认验证、付费评测说明 | health context check | 必须新增 |

## 4. 公共测试 seams

以下 seam 是 TDD 的稳定观察边界。确认后，测试只通过这些边界观察行为，不断言私有函数调用次数或内部实现顺序。

| Seam | 公共边界 | 需要证明的行为 |
|---|---|---|
| S1 HTTP/日志 | FastAPI `app`、`log_request_details()` 产生的日志事件 | 正常响应不变；秘密被脱敏；默认不记录消息正文；500 不暴露内部异常 |
| S2 Checkpoint | `get_checkpointer()`、`make_thread_config()` | Redis 失败默认终止；显式配置后才允许内存降级；稳定 `thread_id` 不变 |
| S3 Fact Store 可用性 | 新的 `FactStoreProvider.get()` | 首次失败返回不可用；冷却期不抖动；冷却后自动重连 |
| S4 工程验证 | 根目录 `make verify` 的退出码 | 同一命令覆盖 pytest、Ruff、mypy、前端 lint/test/build |
| S5 框架配置 | `Configuration.from_runnable_config()`、已编译 LangGraph | 配置值保持兼容；构图不再产生弃用 warning |
| S6 Agent 预算 | 已编译 Research Graph 的输入/输出状态 | 达到搜索、token、时间或无进展上限后停止，并写入稳定 `budget_stop_reason` |
| S7 前端用户流 | 浏览器 DOM：欢迎页、模型加载、提交、计划确认、取消和错误态 | 用户可完成关键路径；失败有可理解的降级；不依赖组件内部 state |
| S8 构建产物 | `npm run build` 输出 | 首屏主 chunk 小于 500 KB；报告渲染代码延迟加载 |

外部 LLM、DashScope、Redis、Milvus、浏览器时间属于系统边界，可以用固定响应或可控时钟替代。项目自身模块不互相 mock。

## 5. 设计决策

### 5.1 日志安全

#### 默认行为

- HTTP 中间件只记录：请求方法、路径、状态码、耗时和 request ID。
- 不记录 query string、Authorization header、Cookie 或完整请求正文。
- `LOG_REQUEST_BODY=1` 仅用于本地诊断；开启后仍必须递归脱敏。
- 脱敏键名不区分大小写，至少覆盖：
  `authorization`、`cookie`、`api_key`、`apikey`、`token`、`secret`、
  `password`、`credential`。
- `messages`、`prompt`、`query`、`content` 默认只记录类型、数量或字符数。

#### 错误响应

`/api/models` 的成功响应保持不变：

```json
{"models": []}
```

失败时返回稳定、无内部细节的结构：

```json
{
  "error": {
    "code": "MODEL_LIST_UNAVAILABLE",
    "message": "模型列表暂时不可用"
  }
}
```

异常类型和 traceback 只进入服务端日志。

### 5.2 持久化降级语义

#### Checkpoint

- `CHECKPOINT_BACKEND=redis` 时，Redis 初始化失败默认抛出异常。
- `CHECKPOINT_FALLBACK_TO_MEMORY=1` 时才允许开发环境使用 `InMemorySaver`。
- `.env.example` 明确写出默认值 `0`。
- `memory` 和 `none` 继续作为显式测试/本地模式。
- Search Cache 的内存降级保持不变，因为它只影响性能，不承诺任务恢复。

#### Milvus

现有全局 `False` sentinel 会让一次启动期故障永久禁用 KB。改为
`FactStoreProvider`：

- `get()` 成功时缓存 `FactStore`。
- 失败时记录 `next_retry_at`，冷却期内返回 `None`。
- 到达 `next_retry_at` 后重新创建连接。
- `KB_RECONNECT_INTERVAL_SECONDS` 默认 30 秒。
- 研究链路在 KB 不可用时继续工作，但日志只记录结构化故障类型。

### 5.3 `make verify` 与 CI

根目录提供：

```text
make backend-test
make backend-lint
make backend-typecheck
make frontend-lint
make frontend-test
make frontend-build
make verify
```

`make verify` 是唯一默认交付门禁，必须是非变更型命令。

CI 触发：

- `pull_request`
- 推送到 `main`

CI 不启动 Redis/Milvus，不调用真实付费 API。后端测试继续使用当前 fixture 的
`CHECKPOINT_BACKEND=none` 和系统边界替身。

### 5.4 框架迁移与依赖锁定

#### Pydantic

将 `Field(metadata={"description": ...})` 改为
`Field(description=...)`。这是 schema 元数据修复，不改变环境变量或 RunnableConfig
优先级。

#### LangGraph

当前安装版本中 `config_schema` 只是 `context_schema` 的弃用别名，因此迁移为：

```python
StateGraph(OverallState, context_schema=Configuration)
```

节点继续通过 `RunnableConfig` 读取现有 `configurable` 字段，避免同时改变前端提交契约。

#### 依赖策略

- 使用已安装的 uv 生成 `backend/uv.lock`。
- 直接依赖声明当前已验证的最低版本，并限制到下一主版本之前。
- 明确声明代码直接导入的 `pydantic`。
- CI 使用：

```bash
uv sync --project backend --extra dev --frozen
uv run --project backend pytest
```

升级依赖必须先更新 lock，再运行 `make verify`。

### 5.5 Agent 成本和停止预算

新增配置：

| 变量 | 默认值 | 含义 |
|---|---:|---|
| `MAX_WEB_SEARCH_CALLS` | 20 | 单任务最大网页搜索次数 |
| `MAX_TOTAL_TOKENS` | 120000 | 单任务累计 LLM token 上限 |
| `MAX_ELAPSED_SECONDS` | 900 | 单任务最长墙钟时间 |
| `MAX_NO_PROGRESS_ROUNDS` | 2 | 连续无新增查询/证据轮数 |

新增状态：

```text
run_started_at
web_search_call_count
llm_token_count
no_progress_rounds
evidence_fingerprint
budget_stop_reason
```

停止原因使用稳定枚举值：

```text
search_call_limit
token_limit
elapsed_time_limit
no_progress
```

设计约束：

- 并行 fan-out 前按剩余搜索预算截断，不在发起外部调用后才判断。
- 每个 LLM 节点把本次 usage 作为 state delta 返回，不能使用进程级全局计数做并发任务预算。
- 达到预算后停止继续搜索；Writer 使用已有证据生成报告，并在状态中保留停止原因。
- Checkpoint 恢复后预算计数继续累计，不能重新置零。
- Benchmark 可显式覆盖默认预算，历史题集不因默认值意外失效。

### 5.6 前端测试与性能

测试栈：

- Vitest
- jsdom
- Testing Library
- `@testing-library/user-event`

测试优先级：

1. 模型列表成功与网络失败降级。
2. 用户提交主题，配置映射为正确的查询数和循环数。
3. 计划生成后可确认继续研究。
4. 流式错误和取消操作可恢复。

性能策略：

- `ChatMessagesView`/Markdown 报告渲染改为 `React.lazy`，欢迎页不加载报告依赖。
- 必要时将 Markdown/Radix/LangGraph SDK 分成稳定 vendor chunk。
- 删除经源码扫描和构建确认未使用的直接依赖。
- 目标是首屏主 chunk 小于 500 KB；不通过单纯提高 warning 阈值掩盖问题。

## 6. 实施顺序

每个编号是一组独立红—绿循环，不一次性先写完所有测试。

1. S1 日志脱敏测试 → 最小实现 → HTTP 错误契约测试 → 最小实现。
2. S2 Checkpoint 失败关闭测试 → 最小实现。
3. S3 FactStoreProvider 冷却重连测试 → 最小实现 → 接入研究链路。
4. S4 新增 Make targets → 修复现有 lint/typecheck 基线 → CI 调用同一入口。
5. S5 Pydantic warning 测试 → 迁移；LangGraph warning 测试 → 迁移。
6. 生成 lock，使用 frozen 环境重新执行 S1—S5。
7. S6 依次实现搜索次数、墙钟、无进展、token 四个预算切片。
8. S7 依次补模型加载、提交、计划确认、取消/错误测试。
9. S8 延迟加载报告视图，比较构建产物。
10. 运行全量验证、health 检查并同步 README、`.env.example`、`AGENTS.md`。

## 7. 验收标准

### 功能与安全

- 测试日志中不出现提供的测试 secret、token、消息正文。
- API 500 响应不包含异常类型、路径或 traceback。
- Redis Checkpoint 不可用且未显式允许降级时，应用启动失败。
- Milvus 恢复后无需重启进程即可重新启用事实记忆。
- 四类预算均有独立停止测试，且 Checkpoint 状态保留停止原因。

### 工程质量

```bash
make verify
uv lock --check --project backend
bash ~/.codex/skills/health/scripts/check-maintainability.sh . summary
```

期望：

- 后端 pytest、Ruff、mypy 全部通过。
- 前端 lint、Vitest、build 全部通过。
- Pydantic/LangGraph 目标弃用 warning 为零。
- health 正确识别 backend/frontend 验证面。
- 前端首屏主 chunk 小于 500 KB。

## 8. 回滚策略

| 阶段 | 回滚方式 |
|---|---|
| 日志 | 恢复旧中间件；不回滚脱敏函数和安全错误结构 |
| Checkpoint | 本地显式设置 `CHECKPOINT_FALLBACK_TO_MEMORY=1`，生产不回滚失败关闭 |
| Milvus Provider | 切回无 KB 模式；不恢复永久 `False` sentinel |
| CI | 单独回滚 workflow，不删除本地 `make verify` |
| 框架迁移 | lock 文件固定旧版本；代码按对应 API 成对回滚 |
| Agent 预算 | 提高或显式覆盖预算；状态字段保持向后兼容 |
| 前端分包 | 回滚 lazy boundary，不回滚已建立的用户流测试 |

## 9. 实施结果

S1—S8 已按确认的公共 seams 实施。默认交付入口为 `make verify`；
后端使用 `backend/uv.lock` frozen 安装，前端主 chunk 由构建脚本强制限制在
500 KB 以下。真实 LLM/Web Search/Milvus 评测仍保持为显式付费操作，不进入
默认 CI。
