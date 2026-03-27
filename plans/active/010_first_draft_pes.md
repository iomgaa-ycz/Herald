# 008: 构建首个 DraftPES

## 元信息
- 状态: draft
- 创建: 2026-03-25
- 更新: 2026-03-25
- 负责人: Codex

## 1.1 摘要

基于当前仓库已具备的 `BasePES`、`PESConfig`、`PromptManager`、`HookManager`、`Workspace`、`HeraldDB` 骨架，落地第一个真实可跑的 `DraftPES`。本次目标是在 Herald2 现有抽象下打通 `draft -> plan/execute/summarize` 主链路，使用占位 `draft_*.j2` 保证可测试可运行，同时接入真实多轮 agent coding 与真实竞赛执行能力；若执行中发现必须扩展 `BasePES` 通用能力，将单独报告后再动。

## 1.2 审查点（Review Required）

| # | 决策项 | 当前倾向 | 说明 |
|---|--------|----------|------|
| 1 | `DraftPES` 是否直接继承 `BasePES` | 是 | 复用现有三阶段调度、Hook、LLM tracing、失败处理 |
| 2 | 本次是否引入完整 `TaskSpec / GenomeSchema` 类型体系 | 是 | 已确认要引入；当前仓库尚未实现，需作为本计划前置交付 |
| 3 | Execute 阶段是否接入真实多轮 agent coding / 真实竞赛执行 | 是 | 已确认要接入，不做纯文本占位执行 |
| 4 | `draft_*.j2` 是否先用占位模板 | 是 | 只约定传入字段与输出格式，后续再补业务内容 |
| 5 | 本次是否扩展 `BasePES` 通用能力 | 尽量少 | 如确需扩展，需单独报告 |
| 6 | 基因结构是否先落为 DB 已支持的 `dict[str, dict]` | 是 | 对齐 `PESSolution.genes` 与 `GeneRepository.insert_batch()` 当前能力 |
| 7 | 本次是否从 `main.py` 接入运行入口 | 否 | 本轮不包含调度器与 CLI 装配，只保证可被测试与手工实例化运行 |

## 1.3 拟议变更（Proposed Changes）

### PES 实现

- [NEW] `core/pes/draft.py::DraftPES`
  - 继承 `BasePES`
  - 实现 `handle_phase_response()`
  - 在 `plan` 阶段解析 LLM JSON，产出 `solution.genes`
  - 在 `execute` 阶段驱动真实多轮 agent coding、真实竞赛执行、代码工件与指标落盘
  - 在 `summarize` 阶段写回 insight、状态与完成时间
- [NEW] `core/pes/draft.py::_extract_json`
  - 从 LLM 文本提取 JSON，兼容 fenced code block 与裸 JSON
- [NEW] `core/pes/draft.py::_parse_plan_response`
  - 将 plan 响应解析为 `dict[str, dict[str, Any]]`
- [NEW] `core/pes/draft.py::_validate_plan_payload`
  - 校验 slot、description、rationale、constraints 等最小字段
- [NEW] `core/pes/draft.py::_extract_metrics`
  - 从真实执行输出中解析 metrics 协议
- [NEW] `core/pes/draft.py::_run_execute_session`
  - 调用真实多轮 agent coding 接口，在 workspace 中生成/调试代码
- [NEW] `core/pes/draft.py::_run_competition_solution`
  - 在工作目录真实执行 `solution.py`
  - 收集 stdout/stderr/exit_code/duration/metrics
- [NEW] `core/pes/draft.py::_collect_execute_artifacts`
  - 按当前 `Workspace` 协议读取 `solution.py` 与 `submission.csv`
  - 触发 `after_solution_file_ready`、`after_execute_metrics`

### PES 配置

- [NEW] `config/pes/draft.yaml`
  - 定义 `name=draft`
  - 定义 `operation=draft`
  - 定义 `solution_file_name=solution.py`
  - 定义 `submission_file_name=submission.csv`
  - 定义三阶段的 `template_name`、`tool_names`、`max_retries`

### Prompt 规格与模板

- [MODIFY] `config/prompts/prompt_spec.yaml`
  - 新增 `draft_plan`
  - 新增 `draft_execute`
  - 新增 `draft_summarize`
  - 仅声明最小 `required_context`
- [NEW] `config/prompts/templates/draft_plan.j2`
  - 先定义输入：`agent`、`workspace`、`competition_dir`、`task_spec`、`genome_schema`
  - 先定义输出：slot -> `{description, rationale, constraints}`
- [NEW] `config/prompts/templates/draft_execute.j2`
  - 先定义输入：`solution`、`genes`、`workspace`、`competition_dir`
  - 先定义输出：`solution.py` / `submission.csv` / metrics 摘要 的约定
- [NEW] `config/prompts/templates/draft_summarize.j2`
  - 先定义输入：`solution`、`execution_log`
  - 先定义输出：简短 insight

### 类型与上下文协议

- [NEW] `core/pes/schema.py`
  - 定义 `TaskSpec`
  - 定义 `GenomeSchema`
  - 定义 `SlotContract`
  - 定义与 `DraftPES` 配套的最小但正式类型体系
  - 说明：当前仓库中这三类尚不存在，已核实需要本次补齐
- [MODIFY] `core/pes/types.py::PESSolution`
  - 若有必要，仅补充 `metadata` 使用约定，不大改结构
- [MODIFY] `core/pes/base.py::build_prompt_context`
  - 仅在确有必要时补充 `genes` 或 Draft 特定字段注入
  - 否则由 `DraftPES` 覆盖该方法，避免污染通用基类

### LLM / 执行适配

- [MODIFY] `core/llm.py::LLMClient`
  - 补齐真实多轮 agent coding 所需接口
  - 优先以最小增量方式支持 `DraftPES.execute()`
  - 如需要改动 `BasePES.call_phase_model()` 以兼容 execute 特殊调用，先单独报告
- [MODIFY] `core/tools.py`
  - 若真实 execute 需要工具集，则补最小工具注册与注入
- [MODIFY] `core/workspace.py`
  - 若真实 execute 需要更明确的运行目录/输入输出路径辅助方法，则做最小补充

### 数据持久化

- [MODIFY] `core/database/herald_db.py`
  - 仅在 `DraftPES` 需要更明确的 tracing / exec log 适配时做最小兼容
- [NO-CHANGE] `core/database/repositories/gene.py`
  - 前提：继续使用当前 `dict` 结构写入 genes
- [NO-CHANGE] `core/database/repositories/solution.py`
  - 前提：`PESSolution.to_record()` 已能覆盖所需字段

### 导出与装配

- [MODIFY] `core/pes/__init__.py`
  - 导出 `DraftPES`
- [MODIFY] `core/pes_engine.py`
  - 兼容导出 `DraftPES`
- [NO-CHANGE] `core/main.py`
  - 本轮明确不接 CLI / 调度器

### 测试

- [NEW] `tests/unit/test_draft_pes.py`
  - 验证 plan JSON 提取/解析
  - 验证非法 plan payload 快速失败
  - 验证 execute metrics 提取协议
- [NEW] `tests/unit/test_pes_schema.py`
  - 验证 `TaskSpec / GenomeSchema / SlotContract` 的最小构造与序列化
- [NEW] `tests/integration/test_draft_pes_flow.py`
  - 使用真实 `Workspace` + 临时 DB + 可控的测试 LLM/Agent 接口桩
  - 验证 `DraftPES.run()` 能走完三阶段
  - 验证 DB 中 solution / genes / llm_calls / exec_logs 已写入
  - 验证 `solution.py`、`submission.csv` 工件按约定落盘
  - 验证 execute 阶段真实调用代码生成与本地执行链路，而非纯字符串伪造

### 文档

- [MODIFY] `docs/architecture.md`
  - 补充当前 PES 层关系：`BasePES` 为通用三阶段骨架，`DraftPES` 为首个具体实现
- [MODIFY] `docs/TD.md`
  - 补充 `DraftPES`、`DraftTaskSpec`、`DraftGenomeSchema` 的最小接口说明

## 1.4 验证计划（Verification Plan）

1. 单元测试
   - `tests/unit/test_draft_pes.py` 通过
   - 覆盖 JSON 提取、plan 解析、metrics 提取、异常分支
2. 集成测试
   - `tests/integration/test_draft_pes_flow.py` 通过
   - 验证 `DraftPES` 在无真实竞赛逻辑下完成最小闭环
3. 人工抽检
   - 检查 `config/pes/draft.yaml` 可被 `load_pes_config()` 正常加载
   - 检查 `PromptManager.build_prompt("draft", phase, context)` 能找到对应模板
   - 检查生成工件与 DB 记录字段一致

## 2. 实施边界

- 本次只做 Herald2 里的第一个真实可跑 `DraftPES`
- 不做 mutate / crossover / selection
- 不做调度器与 `main.py` 入口接线
- 不做高质量 Prompt 设计优化
- 不做复杂 Tool 白名单治理
- 不做多 Agent 协作编排

## 3. 已知现状

- 已核实：仓库中尚无正式 `TaskSpec / GenomeSchema / SlotContract` 实现
- 已核实：当前仓库中尚无任何具体 PES 子类，`DraftPES` 将是首个具体实现
- 已核实：当前 `LLMClient` 只有 `call_with_tools()`，没有旧项目里那种现成的 execute-task 接口

## 4. 风险与缓解

- 风险 1：当前仓库还没有 `TaskSpec / GenomeSchema / SlotContract` 正式实现
  - 缓解：本次先补齐正式最小实现，并以此驱动 DraftPES
- 风险 2：`BasePES.build_prompt_context()` 当前只注入通用字段，Draft 所需上下文可能不够
  - 缓解：优先在 `DraftPES` 内局部覆盖，不扩大通用基类职责
- 风险 3：`LLMClient` 当前缺少真实 execute-task 级接口，可能不足以承载多轮 coding
  - 缓解：优先在 `LLMClient` 增加最小 execute 能力；若必须改 `BasePES` 通用调用路径，单独报告
- 风险 4：PromptSpec 对 `required_context` 校验很严格，漏字段会直接失败
  - 缓解：先让 `draft_*.j2` 极简，并为每个 phase 明确最小上下文字段
- 风险 5：真实竞赛执行依赖外部数据、环境与命令约定，测试中容易不稳定
  - 缓解：集成测试使用可控最小数据与受控执行脚本，先验证主链路正确性

## 5. 待审核结论

建议按上述修订版执行：`DraftPES` 继承 `BasePES`，本次同步补齐正式 `TaskSpec / GenomeSchema / SlotContract`，接入真实 execute 主链路，但保持占位 `draft_*.j2` 与最小 `BasePES` 侵入；若实现过程中发现必须扩展 `BasePES`，我会先单独报告再改。
