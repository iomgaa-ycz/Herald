# 011: Draft Prompt 模板定型

## 元信息
- 状态: in_progress
- 创建: 2026-03-27
- 更新: 2026-03-27
- 负责人: Codex

## 1.1 摘要

本轮目标是为 `DraftPES` 补齐三份 phase 级 Prompt 模板：`draft_plan.j2`、`draft_execute.j2`、`draft_summarize.j2`。重点不是打通完整运行链路，而是先把三阶段各自应该看到什么上下文、输出什么内容、如何体现 Herald2 的 `agent` / `task` 分离约束定型下来。

与参考项目不同，本项目已经在架构层将 Agent 人格与任务上下文解耦，因此模板必须显式区分：`agent` 负责执行风格与偏好，`task_spec` / `schema` / `solution` 负责任务目标、slot 契约与工件状态，二者不能混写。

## 1.2 审查点（Review Required）

| # | 决策项 | 当前倾向 | 说明 |
|---|--------|----------|------|
| 1 | 模板是否依赖 `_macros.j2` | 否 | 当前仓库无该文件；本轮保持模板自包含，避免额外依赖 |
| 2 | 模板是否显式渲染 `agent` | 是 | 需要体现 agent/task 分离，避免 Agent 人格被隐式吞掉 |
| 3 | 模板是否要求外部 md 工件齐备 | 否 | 本轮按用户要求，不以缺少 md 为阻塞条件 |
| 4 | `draft_plan` 输出形态 | 结构化 Markdown | 便于人看与后续解析，不强绑 JSON |
| 5 | 是否联动修改 `prompt_spec.yaml` | 否 | 本轮只定型计划与三份 `.j2`，注册接线留到后续 |

## 1.3 已核实基线

- 已核实：现有 PromptManager 通过 `operation + phase` 选择模板，模板目录为 `config/prompts/templates/`
- 已核实：当前只有 `default_plan/default_execute/default_summarize` 三份默认模板，尚无 `draft_*.j2`
- 已核实：`BasePES.build_prompt_context()` 已注入 `agent`、`solution`、`parent_solution`、`workspace`、`execution_log`
- 已核实：Herald2 的 `Workspace.summary()` 当前稳定提供 `workspace_root/data_dir/working_dir/logs_dir/db_path`
- 已核实：当前仓库没有 `_macros.j2`，若直接照搬参考模板会引入新的缺失依赖
- 已核实：006 已明确 `agent` 与任务执行解耦，Prompt 模板需反映该边界

## 1.4 拟议变更（Proposed Changes）

### A. 新增 Draft Plan 模板

- [NEW] `config/prompts/templates/draft_plan.j2`
  - 渲染 `static_fragments_text`
  - 显式展示 `agent` 信息与角色边界
  - 展示 `task_spec` / `schema` / `parent_solution` / `allowed_tools`
  - 要求模型输出“所有 slot 的描述态方案”，而不是代码
  - 明确说明：缺少外部说明文档时不得阻塞，需做最小可行假设

### B. 新增 Draft Execute 模板

- [NEW] `config/prompts/templates/draft_execute.j2`
  - 渲染 `static_fragments_text`
  - 显式展示 `agent` 信息与角色边界
  - 展示 `task_spec`、`workspace`、`solution.plan_summary`、`solution.genes`、`recent_error`、`template_content`、`allowed_tools`
  - 明确要求：把描述态方案实现为可运行代码，优先 MVP baseline
  - 强调实现围绕工作目录、指标方向和当前 gene 执行，不把 agent prompt 当作任务规格

### C. 新增 Draft Summarize 模板

- [NEW] `config/prompts/templates/draft_summarize.j2`
  - 渲染 `static_fragments_text`
  - 显式展示 `agent` 信息与角色边界
  - 展示 `task_spec`、`solution.plan_summary`、`solution.execute_summary`、`solution.metrics`、`solution.fitness`、`solution.status`、`execution_log`
  - 要求先提炼高价值经验，再给出最终总结
  - 强调区分“观察 / 推断 / 建议”，为下一轮演化沉淀可复用结论

### D. 明确不做（Out of Scope）

- [NO-CHANGE] `config/prompts/prompt_spec.yaml`
- [NO-CHANGE] `_macros.j2`
- [NO-CHANGE] `core/pes/draft.py` phase 响应解析逻辑
- [NO-CHANGE] 任意 md 工件生成或补齐
- [NO-CHANGE] DraftPES 端到端跑通

## 1.5 验证计划（Verification Plan）

1. 文件存在性
   - `config/prompts/templates/draft_plan.j2` 存在
   - `config/prompts/templates/draft_execute.j2` 存在
   - `config/prompts/templates/draft_summarize.j2` 存在

2. 语法冒烟
   - 用最小 Jinja `Environment(loader=FileSystemLoader(...))` 加载三份模板
   - 使用最小上下文执行 `render()`，确认不存在 Jinja 语法错误

3. 内容核对
   - `draft_plan` 含 `agent/task` 分离说明
   - `draft_execute` 含工作空间与 gene/plan 信息
   - `draft_summarize` 含指标、fitness、状态与经验沉淀要求

## 2. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 三份模板已生成，但尚未注册进 `prompt_spec.yaml` | 在计划和交付说明中明确“本轮只定型模板，不接线” |
| 未来上下文字段与当前模板字段名不完全一致 | 模板尽量使用条件渲染与保守 fallback，降低耦合 |
| 参考项目依赖 `_macros.j2`，本项目暂未提供 | 保持模板自包含，后续若重复片段增多再抽宏 |

## 3. 当前结论

建议按本计划执行。本轮以最小成本把 Draft 三阶段 Prompt 的信息架构先定下来，优先确保模板内容正确表达 Herald2 的架构边界，而不是过早追求 Prompt 复用抽象。
