# Learnings

## [LRN-20260618-001] best_practice

**Priority**: high
**Status**: resolved
**Area**: tools

### 内容
LangGraph 子图不会可靠地把父图 `configurable` 参数转换为业务 state 字段。评测 CLI 虽显示每题的 query/loop 参数，实际子图仍可能使用默认值，导致报告中的实验配置与真实执行不一致。重复调用 `asyncio.run()` 还会在异步 HTTP 客户端清理时关闭其 event loop。

### 建议修复
评测器应把关键实验参数同时显式写入研究 state，并用同一个 `asyncio.Runner` 完成一批任务，结束时统一关闭。评测日志必须核对 Agent 实际生成查询数和循环数，不能只相信 CLI 回显。

### 元数据
- Source: task_review
- Pattern-Key: eval-config-state-propagation

---

## [LRN-20260618-002] best_practice

**Priority**: medium
**Status**: resolved
**Area**: tools

### 内容
pytest 的 autouse fixture 在测试模块导入完成后才执行。若模块导入时编译 LangGraph 并初始化 Redis checkpointer，在 fixture 中设置 `CHECKPOINT_BACKEND=none` 已经太晚，会让测试收集阶段等待外部连接。

### 建议修复
对导入期依赖的测试环境变量，应在 `conftest.py` 模块顶层设置；需要覆盖不同 backend 的测试再通过 monkeypatch 和 cache clear 显式切换。

### 元数据
- Source: error
- Pattern-Key: pytest-import-time-environment

---

## [LRN-20260619-001] best_practice

**Priority**: high
**Status**: resolved
**Area**: testing

### 内容
LLM E2E 评测中的单题针对性复测只能验证局部修复是否生效，不能替代完整固定集结果。本轮 FSD 针对性复测为 4.8/5，但完整固定集同题为 4.0/5；SDD 分别为 4.6/5 和 4.0/5，表明检索、生成和 Judge 均存在明显运行方差。

### 建议修复
验收和简历指标必须来自同一固定题集、相同参数下的完整运行；针对性重跑仅作为诊断证据。需要估计真实收益时，应运行多个重复样本并报告均值、标准差、逐题胜率和幻觉率，禁止用单题最好结果替换固定集结果。

### 元数据
- Source: task_review
- Pattern-Key: targeted-eval-fixed-set-variance

---
