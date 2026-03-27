# 010: DraftPES 接口定型

## 元信息
- 状态: draft
- 创建: 2026-03-25
- 更新: 2026-03-27
- 负责人: Codex

## 1.1 摘要

本轮不追求 `DraftPES.run()` 可跑通，也不接入正式 Prompt。目标只收敛 4 个接口面：`BasePES` 的 `cwd` / `env` 透传、`DraftPES` 类骨架、`core/pes/schema.py` 最小类型定义、`config/pes/draft.yaml` 配置接口。

换言之，本轮交付的是“后续实现 DraftPES 的骨架与约束”，不是完整 DraftPES 功能。`prompt_spec.yaml`、`draft_*.j2`、plan/execute/summarize 的真实业务逻辑，统一留到下一轮。

## 1.2 审查点（Review Required）

| # | 决策项 | 当前倾向 | 说明 |
|---|--------|----------|------|
| 1 | `BasePES` 如何支持 `cwd` / `env` | 新增 phase 级 hook | 由子类提供 phase 运行参数，基类统一透传 |
| 2 | `DraftPES` 骨架是否要求可运行 | 否 | 只要求可导入、接口明确，不承诺 `run()` 可用 |
| 3 | `DraftPES.handle_phase_response()` 如何处理 | 显式占位 | 用 `NotImplementedError` 表明业务逻辑待下一轮实现 |
| 4 | `schema.py` 的范围 | 最小正式类型 | 只定义 DraftPES 下一轮会依赖的核心输入结构 |
| 5 | `config/pes/draft.yaml` 是否接入 Prompt | 否 | 只定义 phase 配置结构，不配套 `prompt_spec/j2` |

## 1.3 已核实基线

- 已核实：`LLMClient` 已迁移到 `execute_task()`，并支持 `cwd` / `env`
- 已核实：`BasePES.call_phase_model()` 当前尚未透传 `cwd` / `env`
- 已核实：`core/tools.py` 已不存在，后续工具访问路径应走 CLI
- 已核实：当前仓库尚无具体 PES 子类，`DraftPES` 将是首个具体实现
- 已核实：当前 Prompt 装配链要求 `prompt_spec + j2` 成对存在，因此本轮若不做 Prompt 文件，就不应承诺 `DraftPES.run()` 可用

## 1.4 拟议变更（Proposed Changes）

### A. `BasePES` 增加 `cwd` / `env` 透传能力

- [MODIFY] `core/pes/base.py`
  - [NEW] `build_phase_model_options(phase, solution, parent_solution) -> dict[str, Any]`
    - 默认返回空字典
    - 本轮只约定支持两个 key：
      - `cwd`
      - `env`
  - [MODIFY] `_run_phase()`
    - 在调用模型前收集 `model_options`
    - 将 `cwd` / `env` 传给 `call_phase_model()`
  - [MODIFY] `call_phase_model()`
    - 新增显式参数：
      - `cwd: str | None = None`
      - `env: dict[str, str] | None = None`
    - 透传到 `self.llm.execute_task()`

### B. `DraftPES` 类骨架

- [NEW] `core/pes/draft.py`
  - [NEW] `DraftPES(BasePES)`
    - 继承 `BasePES`
    - 实现 `build_phase_model_options()`
      - `plan` / `summarize` 返回空字典
      - `execute` 在 `workspace` 存在时返回：
        - `cwd = str(workspace.working_dir)`
        - `env = {"HERALD_DB_PATH": str(workspace.db_path)}`
    - 实现 `handle_phase_response()`
      - 当前阶段显式抛出 `NotImplementedError`
      - 错误信息中注明：DraftPES 业务逻辑待下一轮实现

- [NO-CHANGE] 本轮不实现：
  - plan JSON 解析
  - execute 真实 Agent coding
  - summarize insight 提取
  - 工件读取、metrics 抽取、DB 落盘

### C. 最小 Schema

- [NEW] `core/pes/schema.py`
  - [NEW] `TaskSpec`
    - `task_type`
    - `competition_name`
    - `objective`
    - `metric_name`
    - `metric_direction`
  - [NEW] `SlotContract`
    - `function_name`
    - `params`
    - `return_type`
  - [NEW] `GenomeSchema`
    - `task_type`
    - `slots: dict[str, SlotContract | None]`

- [NO-CHANGE] 本轮不定义：
  - 复杂 genome DSL
  - Prompt 上下文字段协议
  - Gene payload 校验规则

### D. `draft.yaml` 配置接口

- [NEW] `config/pes/draft.yaml`
  - 定义：
    - `name = draft`
    - `operation = draft`
    - `solution_file_name = solution.py`
    - `submission_file_name = submission.csv`
  - 定义三阶段配置结构：
    - `plan`
    - `execute`
    - `summarize`
  - 本轮只要求字段完整，可被 `load_pes_config()` 正常加载
  - 建议值：
    - `template_name = null`
    - `tool_names = []` 或 `["db_cli"]`
    - `allowed_tools` 保留未来 execute 所需接口
    - `max_retries`
    - `max_turns`

## 1.5 明确不做（Out of Scope）

- 不修改 `config/prompts/prompt_spec.yaml`
- 不新增 `config/prompts/templates/draft_*.j2`
- 不实现 `DraftPES.run()` 端到端可用
- 不实现 plan / execute / summarize 真实业务逻辑
- 不修改 `core/llm.py`
- 不接入 `main.py`
- 不做 DB 持久化与 execute 工件处理
- 不导出 `DraftPES` 到统一入口，除非实现时发现这是导入所必需的最小改动

## 1.6 验证计划（Verification Plan）

1. 接口冒烟
   - `from core.pes.draft import DraftPES` 导入成功
   - `from core.pes.schema import TaskSpec, SlotContract, GenomeSchema` 导入成功

2. 配置冒烟
   - `load_pes_config("config/pes/draft.yaml")` 成功
   - `plan/execute/summarize` 三个 phase 都存在
   - `allowed_tools/max_turns` 字段可正常读取

3. 透传冒烟
   - 使用最小 DummyPES / DummyLLM 验证：
     - `build_phase_model_options()` 返回的 `cwd` / `env`
     - 能经由 `BasePES._run_phase() -> call_phase_model() -> llm.execute_task()` 透传

## 2. 实施边界

- 本轮只做接口，不做功能
- 本轮只定型，不做 Prompt
- 本轮只保证骨架可导入、配置可加载、`cwd/env` 接口可透传
- 本轮不承诺 `DraftPES.run()` 可执行

## 3. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 用户误以为 `DraftPES` 已可运行 | `handle_phase_response()` 显式抛出 `NotImplementedError` |
| `draft.yaml` 存在但无 Prompt 文件，后续误调用运行链路 | 在计划与实现注释中明确“配置先行，Prompt 待后续补齐” |
| `BasePES` 新增接口影响未来子类 | 默认实现返回空字典，保持向后兼容 |

## 4. 待审核结论

建议按本收缩版执行。本版严格只覆盖 4 项接口层交付：`BasePES.cwd/env`、`DraftPES` 骨架、`schema.py`、`draft.yaml`；Prompt、真实 phase 逻辑与端到端运行统一推迟到下一轮。
