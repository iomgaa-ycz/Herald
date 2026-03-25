# 007: 定义首个 `kaggle_master` Agent

## 元信息
- 状态: draft
- 创建: 2026-03-25
- 更新: 2026-03-25
- 负责人: Codex

## 1.1 摘要

基于 006 已完成的 Agent/任务分离基础设施，定义首个符合当前注册标准的 `kaggle_master` Agent。此次工作只处理 Agent 侧配置与注册兼容性，不涉及任务定义、PES 行为变更，也不把 Agent Prompt 设计本身作为交付目标。

## 1.2 审查点（Review Required）

| # | 决策项 | 当前倾向 | 说明 |
|---|--------|----------|------|
| 1 | 首个 Agent 是否命名为 `kaggle_master` | ✓ | 已确认 |
| 2 | 是否保留现有 `aggressive/balanced/conservative` | 否 | 已确认全部移除 |
| 3 | 本次是否设计 Agent Prompt 内容 | 否 | 仅在当前注册标准要求时提供占位文件 |
| 4 | 本次是否修改任务定义或 PES | 否 | Agent 与任务解耦，本次只定义 Agent |
| 5 | 是否引入复杂 Agent 元数据（能力标签/工具白名单/温度偏好） | 否 | 已确认保持最小配置 |

## 1.3 拟议变更（Proposed Changes）

### Agent 配置

- [NEW] `config/agents/kaggle_master.yaml`
  - 按当前 `AgentRegistry.load()` 标准定义 `name`、`display_name`、`prompt_file`
- [NEW] `config/agents/prompts/kaggle_master.md`
  - 仅提供注册所需文件
  - 内容采用最小可用占位，不在本次任务中设计 Persona 细节
- [DELETE] `config/agents/aggressive.yaml`
- [DELETE] `config/agents/balanced.yaml`
- [DELETE] `config/agents/conservative.yaml`
- [DELETE] `config/agents/prompts/aggressive.md`
- [DELETE] `config/agents/prompts/balanced.md`
- [DELETE] `config/agents/prompts/conservative.md`

### Agent 数据模型

- [MODIFY] `core/agent/profile.py::AgentProfile`
  - 保持现有三字段最小模型不变
  - 不新增任何复杂 Agent 元数据

### 注册兼容性

- [MODIFY] `core/agent/registry.py::list_all`
  - 若删除旧 Agent 后测试或实现依赖固定列表，需同步更新
- [MODIFY] `core/agent/registry.py::load`
  - 仅在删除旧配置后暴露出兼容性问题时修正
  - 不扩展加载协议，继续遵守现有 `yaml + prompt_file` 约定

### 非目标项

- [NO-CHANGE] `core/events/dispatcher.py`
- [NO-CHANGE] `core/events/types.py`
- [NO-CHANGE] `core/pes/base.py`
- [NO-CHANGE] `config/prompts/prompt_spec.yaml`
- [NO-CHANGE] `config/prompts/templates/*.j2`
  - 原因：本次不处理任务定义与 Prompt 注入策略，只定义 Agent 实体

### 测试

- [MODIFY] `tests/unit/test_agent_registry.py`
  - 改为断言 `kaggle_master` 可加载
  - `list_all()` 预期调整为仅包含 `kaggle_master`
- [MODIFY] `tests/integration/test_dispatch_flow.py`
  - 如当前集成测试依赖 `aggressive`，替换为 `kaggle_master`
  - 仅验证主链路能加载该 Agent，不扩大测试目标

### 文档

- [MODIFY] `docs/architecture.md`
  - 补一条最小说明：Agent 目前是独立于任务定义的可加载实体
- [MODIFY] `docs/TD.md`
  - 补 `AgentProfile/AgentRegistry` 当前最小配置协议说明

## 1.4 验证计划（Verification Plan）

1. 单元测试
   - `tests/unit/test_agent_registry.py` 通过
   - 验证 `kaggle_master` 可加载、Prompt 文件可读、缓存逻辑正常
   - 验证 `list_all()` 结果与清理后的配置目录一致
2. 集成测试
   - `tests/integration/test_dispatch_flow.py` 通过
   - 验证 `TaskDispatchEvent -> TaskExecuteEvent -> BasePES.run()` 主链路在 `kaggle_master` 下仍可用
3. 人工抽检
   - 检查 `config/agents/` 下仅保留 `kaggle_master`
   - 检查没有引入多余元数据与任务侧改动

## 2. 实施边界

- 本次只做“首个独立 Agent 定义”
- 不做多 Agent 策略选择
- 不做 Agent Prompt 设计优化
- 不做 Agent 能力评分、历史表现反馈、动态 Prompt 拼装
- 不做任何任务侧或 PES 侧行为设计

## 3. 风险与缓解

- 风险 1：当前注册协议强依赖 `prompt_file`，即使本次不做 Prompt 设计，也必须提供文件
  - 缓解：提供最小占位 Prompt 文件，先满足注册标准
- 风险 2：删除旧实验人格后，测试仍引用旧名称
  - 缓解：同步更新单测与集成测试中的 Agent 名称
- 风险 3：误把 Agent 定义和任务定义耦合到一起
  - 缓解：明确标记任务侧文件为非目标项，不修改 PES/Prompt 模板

## 4. 待审核结论

建议批准执行，按 MVP 只定义 `kaggle_master` 一个 Agent，并清理旧实验人格；任务定义与 Prompt 策略保持不动。
