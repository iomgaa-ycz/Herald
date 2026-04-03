# Herald2 系统架构

> **版本**: v0.1
> **更新**: 2026-03-29
> **定位**: Herald2 的唯一系统架构基线

---

## 1. 项目定位

Herald2 的目标不是做一个“会写一点 baseline 的脚本生成器”，而是做一个**面向 mle-bench / Kaggle 类任务的自动化竞赛 Agent 系统**。

当前建议把系统公式收敛为：

```text
Herald2
= 任务规格（TaskSpec / GenomeSchema）
+ PES 驱动的方案生成-执行-总结闭环
+ 可追踪 Harness（Workspace + HeraldDB + Prompt/日志）
+ 渐进扩展的基因级进化能力（Draft / Mutate / Merge）
+ 人类可审查、可干预的研究工作流
```

一句话说：

**Herald2 应该是一个以 PES 为内核、以 Harness 为底座、最终走向基因级进化搜索的自动化竞赛研究系统。**

当前阶段必须坚持两个原则：

- **MVP 优先**：先把单方案闭环跑通，再谈种群、并行、多岛。
- **Harness 优先**：先让系统“看得见自己在做什么”，再让系统“更聪明”。

---

## 2. 系统核心设计

Herald2 的系统设计由以下能力组成：

| 核心能力 | 定义 | 当前状态 |
|---|---|---|
| 基因级方案表示 | 方案最终按 slot / gene 建模，而不是整段代码黑箱搜索 | 仅有 `TaskSpec` / `SlotContract` / `GenomeSchema` 最小类型与 DB 预留；GenomeSchema 模板体系（tabular / generic）已设计 |
| PES 研究闭环 | 所有核心操作统一走 `Plan / Execute / Summarize` | `BasePES` + `DraftPES` 已跑通三阶段调用；`FeatureExtractPES` 已设计为前置 PES |
| 分层记忆 | 运行日志、结构化经验、跨任务规律分层沉淀 | L1/L2/L3 相关表已建，真正知识回流尚未接入运行链路 |
| 多操作进化 | 系统最终由 `Draft / Mutate / Merge` 三类操作驱动 | 目前只有 `DraftPES` 实现 |
| 调度与编排 | 外层调度器负责任务驱动、预算与并行控制 | 当前是单进程、串行 `Scheduler` |
| Agent 专业化 | 不同操作可以绑定不同 agent profile 与执行策略 | 当前只有 `kaggle_master` 一个 profile |
| 人机协作 | 人类负责目标、审核与关键决策，系统负责搜索与执行 | 当前通过 `docs/`、`plans/`、审查点体现 |

这些能力共同定义了 Herald2 本身。

---

## 3. 架构原则

### 3.1 PES 是系统内核，不是调度器

调度器负责“何时发任务”，但真正定义一次研究迭代的，是 `Plan -> Execute -> Summarize`。

因此：

- `Scheduler` 只是外层驱动器
- `BasePES` / `DraftPES` 才是核心执行单元
- 后续 `MutatePES` / `MergePES` 也应复用同一套运行骨架

### 3.2 Solution 是第一公民

系统的核心对象不是一次 LLM 回复，而是一个 `Solution`：

- 有代数 `generation`
- 有谱系 `parent_ids` / `lineage`
- 有方案摘要
- 有产物路径
- 有指标 / fitness
- 有可追踪日志

所有后续进化能力都应围绕 `Solution` 扩展，而不是围绕“聊天历史”扩展。

### 3.3 Harness 先于 Intelligence

没有可追踪 Harness，再强的模型也只是不可复现的随机尝试。

Herald2 的真实底座是：

- `Workspace` 负责文件工件
- `HeraldDB` 负责状态与知识
- `PromptManager` 负责首次上下文装配
- `EventBus` 负责流程编排

这里还要明确一个事实来源原则：

- 不可信的是模型用自然语言给自己下结论，例如“我成功了”“这次更优了”
- 可信的是 execute 阶段通过 tools 真实产出的工件与机器事实，例如 `solution.py`、`submission.csv`、stdout/stderr、脚本打印出的 `fitness`
- Harness 的职责是沉淀这些事实，而不是为了“去除自述”默认把高成本脚本再完整重跑一遍

### 3.4 先单机串行，后多 Agent 并行

当前代码应坚持：

1. 先完成单 `DraftPES` 闭环
2. 再补 `Mutate`
3. 再补 `Merge`
4. 再做种群选择
5. 最后再做并行与多岛

不要跳过中间层，直接做“看起来很大”的多 Agent 系统。

### 3.5 文档、计划、数据库必须三位一体

Herald2 是研究项目，最怕“代码已经变了，但系统理解没变”。所以：

- `docs/architecture.md` 定义系统全景
- `docs/TD.md` 定义模块接口
- `plans/` 记录最近决策与边界
- `HeraldDB` 记录运行时事实

---

## 4. 目标架构（North Star）

这是 Herald2 的目标架构定义，不代表当前已经全部实现。

```text
┌──────────────────────────────────────────────────────────────┐
│                    人类研究者 / Lead Agent                    │
│        定义任务目标、审核关键决策、调整搜索方向与预算           │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                    Orchestrator / 调度层                      │
│    任务编排 · 预算管理 · 操作配比 · 并行控制 · 可观测性          │
└───────────────┬──────────────────────┬───────────────────────┘
                │                      │
      ┌─────────▼─────────┐  ┌────────▼────────┐
      │   Draft / Mutate  │  │     Merge       │
      │     PES Lane      │  │     PES Lane    │
      └─────────┬─────────┘  └────────┬────────┘
                │                      │
                └──────────┬───────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                    PES Runtime 抽象层                         │
│   BasePES · PromptManager · AgentProfile · LLMClient         │
└───────────────┬─────────────────────────┬────────────────────┘
                │                         │
┌───────────────▼──────────────┐ ┌────────▼────────────────────┐
│     Workspace / Sandbox       │ │         HeraldDB           │
│   代码落盘 · 执行 · 产物归档    │ │  solutions / traces / L2/L3 │
└───────────────┬──────────────┘ └────────┬────────────────────┘
                │                         │
                └──────────────┬──────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│             mle-bench / Kaggle 竞赛环境与评分反馈              │
└──────────────────────────────────────────────────────────────┘
```

这个目标架构里有三个真正不可动摇的轴：

1. **任务规格轴**：`TaskSpec + GenomeSchema` 定义“允许搜索什么”
2. **运行闭环轴**：PES 定义“如何搜索”
3. **追踪记忆轴**：Workspace + DB 定义“系统如何积累经验”

---

## 5. 当前代码的真实架构（2026-03-31）

当前仓库已完成第一阶段（M0~M0.5）的全部 17 个任务，实现了**单进程、串行驱动的 FeatureExtractPES + DraftPES 双 PES 流水线闭环**。

### 5.1 已实现主链路

```text
core/main.py
  │
  ├── ✅ ConfigManager.parse()
  ├── ✅ Workspace.create() + expose_project_skills()
  ├── ✅ HeraldDB(...)
  ├── ✅ EventBus.get()
  ├── ✅ setup_task_dispatcher()
  ├── ✅ bootstrap_feature_extract_pes(...)
  │      ├── load_pes_config("config/pes/feature_extract.yaml")
  │      ├── LLMClient(...)
  │      └── FeatureExtractPES(...)
  ├── ✅ bootstrap_draft_pes(...)
  │      ├── load_pes_config("config/pes/draft.yaml")
  │      ├── LLMClient(...)
  │      └── DraftPES(...)
  │
  └── ✅ Scheduler(task_stages=[
          ("feature_extract", 1),
          ("draft", max_tasks),
      ]).run()
          │
          ├── ✅ Stage 1: emit(TaskDispatchEvent(task_name="feature_extract"))
          │     ▼
          │   TaskDispatcher → FeatureExtractPES.run()
          │     ├── plan:     分析竞赛描述，规划数据探索策略
          │     ├── execute:  LLM Agent 用 Bash/Skill 工具读取数据文件
          │     │             → 生成 TaskSpec + data_profile + 选择 genome_template
          │     └── summarize: 总结数据特征与建模建议
          │     ▼
          │   TaskCompleteEvent (携带 output_context)
          │     → Scheduler 收集 TaskSpec / data_profile / genome_template
          │
          └── ✅ Stage 2: emit(TaskDispatchEvent(task_name="draft", context=上游产出))
                ▼
              TaskDispatcher → DraftPES.run()
                ├── plan:     消费 TaskSpec + data_profile + GenomeSchema 模板
                ├── execute:  生成真实 solution.py + submission.csv + 提取 metrics
                └── summarize: 总结 + 版本归档 + best 提升
```

### 5.2 FeatureExtractPES.run() 行为

```text
FeatureExtractPES.run()
  ├── create_solution()          -> 插入 solutions
  ├── plan()                     -> 渲染 feature_extract_plan Prompt
  │      └── 分析竞赛 description.md，规划数据探索策略
  ├── execute_phase()            -> 渲染 feature_extract_execute Prompt
  │      ├── LLM Agent 用 Bash 工具执行数据探索:
  │      │     - ls data/、head train.csv
  │      │     - python -c "pd.read_csv(...).info()"
  │      │     - 读取 description.md 提取任务目标与指标
  │      ├── 输出结构化 TaskSpec JSON
  │      ├── 输出数据概况报告 (data_profile)
  │      ├── 判断任务类型并选择 GenomeSchema 模板 (tabular/generic)
  │      └── 持久化到 workspace/working/:
  │            - task_spec.json
  │            - data_profile.md
  └── summarize()                -> 总结数据特征、关键发现、建模建议
         └── emit(TaskCompleteEvent, output_context={task_spec, data_profile, genome_template})
```

### 5.3 DraftPES.run() 真实行为

```text
DraftPES.run()
  ├── create_solution()          -> 插入 solutions
  ├── plan()                     -> 渲染 draft_plan Prompt，调 LLM，记录 llm_calls
  │      └── 消费 task_spec + data_profile + GenomeSchema 模板
  ├── execute_phase()            -> 渲染 draft_execute Prompt，调 LLM，记录 llm_calls
  │      ├── _attach_workspace_artifacts()
  │      ├── _assert_tool_write_contract()     -> 校验 solution.py 已写出
  │      ├── _validate_python_code()           -> 语法检查
  │      ├── _persist_code_snapshot()          -> 代码快照入库
  │      ├── _extract_execute_fact()           -> 从 tool trace 提取首次运行事实
  │      ├── _persist_exec_log()               -> exec_logs 入库
  │      ├── _extract_val_metrics()            -> 提取 val_metric_value
  │      ├── _apply_val_metrics()              -> 回写 fitness
  │      └── _validate_submission_artifact()   -> 校验 submission.csv
  └── summarize()                -> 渲染 draft_summarize Prompt，调 LLM，记录 llm_calls
         ├── _archive_completed_solution()     -> 版本归档
         ├── _maybe_promote_best()             -> 最优时提升 best/
         └── emit(TaskCompleteEvent)
```

### 5.4 当前必须明确的事实

- 两个生产级 PES：`FeatureExtractPES`（前置）和 `DraftPES`（主链路）
- 一个 Agent profile：`kaggle_master`
- `Scheduler` 是**串行**的，支持 `task_stages` 多阶段流水线
- `EventBus` 是**进程内总线**，不是分布式消息系统
- Draft execute 已接通完整的 tool-write 契约：代码落盘、语法校验、首次运行事实、metrics 提取、submission 校验
- `val_metric_value -> fitness` 闭环已打通
- `test_score` 通过 `MLEBenchGradingHook` 在 `after_run` 补采
- 版本归档（`save_version`）和 best 提升（`promote_best`）已接入
- Draft Summarize 已输出固定五小节格式，Summarize 完成后自动写入 `l2_insights`（L2 = draft summarize 的索引/加工视图，见 §7.4）
- CLI 已提供 `get-l2-insights`（查询 L2 经验）和 `get-draft-detail`（深查单个 draft 完整总结）
- **多次 draft 之间的信息传递机制正在建设中**：Agent 可通过 CLI 查询前序 draft 经验，差异化约束尚未接入 prompt

当前系统的定义是：

**Herald2 已完成单 Draft 闭环的全部 Harness 能力和 L2 经验沉淀机制，正在进入”多次 Draft 差异化生成”阶段。**

---

## 6. 模块职责划分

| 模块 | 职责 | 当前状态 |
|---|---|---|
| `core/main.py` | 生产入口，负责 bootstrap 全链路 | 已实现 |
| `core/scheduler/` | 最小调度器，串行发任务并等待完成 | 已实现 |
| `core/events/` | 进程内事件总线与任务分发 | 已实现 |
| `core/pes/base.py` | 统一的 PES 三阶段抽象 | 已实现 |
| `core/pes/feature_extract.py` | FeatureExtract 操作：数据分析 + TaskSpec 生成 + GenomeSchema 选择 | 待实现 |
| `core/pes/draft.py` | Draft 操作的最小落地 | 已实现，但执行能力仍很薄 |
| `core/pes/config.py` | PES YAML 配置加载 | 已实现 |
| `core/pes/types.py` | `PESSolution` 运行期状态模型 | 已实现 |
| `core/pes/schema.py` | `TaskSpec` / `SlotContract` / `GenomeSchema` 最小类型 + 模板加载 | 已实现（含模板加载 MVP） |
| `config/genome_templates/` | GenomeSchema 代码模板（tabular.py / generic.py） | 已实现（tabular / generic 模板） |
| `core/agent/` | Agent profile 注册与加载 | 已实现，当前仅 prompt profile |
| `core/prompts/` | 首次 Prompt 装配 | 已实现 |
| `config/prompts/templates/` | `draft_plan/execute/summarize` 模板 | 已实现 |
| `core/llm.py` | Claude Agent SDK 封装 | 已实现 |
| `core/workspace.py` | 工作空间目录、版本与最佳结果管理 | 基础能力已实现，尚未完全接入 PES |
| `core/database/` | SQLite schema、repo、query、门面 | 已实现 |
| `core/cli/db.py` | 供 Agent 通过 Bash 查询 DB 的 CLI | 已实现，但尚未成为主流程默认工具链 |

---

## 7. 数据模型与记忆层

### 7.1 当前中心对象：`PESSolution`

当前 `PESSolution` 已经承担了未来 `Solution` 的雏形角色，包含：

- 身份：`id`, `generation`, `lineage`, `parent_ids`
- 状态：`status`, `created_at`, `finished_at`
- 摘要：`plan_summary`, `execute_summary`, `summarize_insight`
- 产物：`workspace_dir`, `solution_file_path`, `submission_file_path`
- 预留扩展：`genes`, `metrics`, `fitness`, `metadata`

这说明系统的中心对象应当就是 `Solution`，而不是一次次离散 prompt。

### 7.2 任务规格边界：`TaskSpec + SlotContract + GenomeSchema`

这三个类型代表了 Herald2 后续从”整段代码生成”走向”受约束的基因级搜索”的边界。

其职责应是：

- `TaskSpec`：定义赛题目标、指标与任务类型。**由 `FeatureExtractPES` 动态生成**，不再静态构造
- `SlotContract`：定义每个 slot 的接口边界
- `GenomeSchema`：定义某类任务允许搜索哪些 slot。**携带代码模板文件路径**

#### TaskSpec 动态生成流

```text
竞赛目录 (description.md + data files)
  → FeatureExtractPES.execute()
  → LLM Agent 分析数据结构与竞赛描述
  → 输出结构化 TaskSpec JSON:
      {task_type, competition_name, objective, metric_name, metric_direction}
  → 持久化到 workspace/working/task_spec.json
  → 通过 TaskCompleteEvent.output_context 传递给 Scheduler
  → 注入 DraftPES 的 runtime_context
```

#### GenomeSchema 模板体系

不同任务类型使用不同的代码模板骨架：

| task_type | 模板文件 | slots | 说明 |
|---|---|---|---|
| `tabular` | `config/genome_templates/tabular.py` | DATA, FEATURE_ENG, MODEL, POSTPROCESS | 标准表格任务，含 GENE 标记区域 |
| `generic` | `config/genome_templates/generic.py` | DATA, PROCESS, MODEL, POSTPROCESS | 通用模板，兼容非 tabular 任务 |

模板文件格式遵循 `Reference/tabular_ml.py` 的约定：
- `# === GENE:XXX_START ===` / `# === GENE:XXX_END ===` 标记 LLM 可填充的 slot 区域
- `# === FIXED:XXX ===` / `# === FIXED:XXX_END ===` 标记不可修改的固定区域
- 模板选择由 `FeatureExtractPES` 根据 task_type 判断确定

`GenomeSchema` 新增 `template_file` 字段指向对应的模板文件路径。`load_genome_template(task_type)` 函数根据 task_type 返回对应的 `GenomeSchema` + 模板代码内容。

#### FeatureExtractPES 输出数据流

```text
FeatureExtractPES 产出:
  ├── TaskSpec              → runtime_context[“task_spec”]
  ├── data_profile          → runtime_context[“data_profile”] (文本报告)
  ├── genome_template       → runtime_context[“schema”] (GenomeSchema + template_content)
  └── workspace 持久化:
        ├── working/task_spec.json
        └── working/data_profile.md
```

### 7.3 HeraldDB 的分层职责

| 层级 | 表 | 目标职责 | 当前状态 |
|---|---|---|---|
| 核心实体 | `solutions` | 记录方案生命周期 | 已接入 |
| 基因层 | `genes` | 记录 slot 级描述态 | 已建表，主流程未接入 |
| 代码态 | `code_snapshots` | 保存完整代码快照 | 已建表，主流程未接入 |
| L1 Trace | `llm_calls` | 保存模型调用痕迹 | 已接入 |
| L1 Trace | `exec_logs` | 保存执行日志 | 已建表，主流程未接入 |
| L1 Trace | `contract_checks` | 保存契约验证结果 | 已建表，主流程未接入 |
| L2 Knowledge | `l2_insights`, `l2_evidence` | draft summarize 的索引/加工视图 | 已接入主链路（Summarize 后自动写入） |
| L3 Wisdom | `l3_wisdom`, `l3_sources` | 保存跨任务规律 | 已建表预留 |

### 7.4 DB 的 run 生命周期与 L2 的真实语义

**关键事实：每次 run 前会清除 DB 数据。** 这意味着：

- **不存在跨 run 的 L2 经验**。`l2_insights` 表中的数据全部来自本次 run 内前序 draft 的 summarize_insight
- **L2 = draft summarize 的索引/加工视图**，不是独立于 draft 的知识来源。`_write_l2_knowledge()` 从 summarize_insight 中提取 pattern 并写入 `l2_insights`，同时记录 evidence（support/contradict）和 confidence 评分
- Agent 获取前序 draft 经验的**主要入口是 `get-l2-insights` CLI**（含 confidence 评分和 pattern 索引），需要深查时用 `get-draft-detail`
- L3（跨任务规律）在单 run 清 DB 的语境下无实际意义，表结构仅作远期预留

---

## 8. 当前主流程的分层理解

### 8.1 Bootstrap 层

`main.py` 做四件事：

1. 加载配置
2. 创建工作空间
3. 初始化 DB
4. 初始化事件系统并装配 `DraftPES`

这意味着 Herald2 当前不是通过“自动发现所有组件”来启动，而是通过**显式 bootstrap** 启动。

这是正确的 MVP 决策，因为当前只有一个 PES 类型。

### 8.2 调度层

`Scheduler + TaskDispatcher + EventBus` 组成最小调度层。

职责边界如下：

- `Scheduler`：决定发几次任务、何时发下一个。**支持 `task_stages` 多阶段流水线**
- `TaskDispatcher`：把”任务名”映射成”具体 PES 实例”（无需修改）
- `EventBus`：负责消息通知
- `PESRegistry`：负责查询已注册 PES（无需修改）

#### task_stages 机制

`Scheduler` 新增 `task_stages: list[tuple[str, int]]` 参数，支持按阶段顺序调度不同 PES：

```text
task_stages = [
    (“feature_extract”, 1),    # 前置阶段：运行 1 次
    (“draft”, max_tasks),      # 主阶段：运行 N 次
]
```

阶段之间的数据传递：
1. 每个阶段完成后，Scheduler 从 `TaskCompleteEvent.output_context` 收集产出
2. 产出合并到 `shared_context`，注入下一阶段的 dispatch context
3. 下游 PES 通过 `_execution_context` 访问上游产出

向后兼容：不传 `task_stages` 时，退化为原有 `(task_name, max_tasks)` 行为。

这层目前只解决”驱动问题”，还不负责：

- 种群选择
- 预算分配
- 并行控制
- 操作配比

### 8.3 PES 层

`BasePES` 已经提供了非常关键的稳定抽象：

- 统一三阶段
- 统一 prompt 渲染
- 统一模型调用
- 统一 LLM trace 记录
- 统一错误处理

这是后续实现 `MutatePES` / `MergePES` 最重要的复用层。

### 8.4 Harness 层

当前 Harness 由两部分构成：

- `Workspace`：工件落盘、版本归档、best 提升、project skill 暴露
- `HeraldDB`：solutions、llm_calls、exec_logs、code_snapshots、contract_checks、grading_results 已全部接入主流程

L2 已接入主流程：Draft Summarize 完成后自动调用 `_write_l2_knowledge()` 写入 `l2_insights`。L2 本质是 draft summarize 的索引/加工视图（见 §7.4）。

---

## 9. 当前缺口与真正的下一步

### 9.1 ✅ P0：单 Draft 闭环（已完成）

第一阶段（M0~M0.5）的全部 17 个任务已完成：

- FeatureExtractPES 动态生成 TaskSpec + data_profile + GenomeSchema 选择
- Scheduler 支持 task_stages 多阶段流水线
- DraftPES 完整 tool-write 契约、代码落盘、首次运行事实、metrics 提取
- submission 校验、版本归档、best 提升
- MLEBenchGradingHook 补采 test_score
- run 级元数据与人类可读日志
- project skill 暴露到 workspace

### 9.2 P0.7：多次 Draft + 差异化生成（当前阶段）

第一阶段的系统有一个核心缺口：**多次 draft 之间没有信息传递，每次 draft 都是”从零开始”**。

本阶段的进展与剩余工作：

**已完成：**
1. **Draft Summarize 固定格式** — 五小节段落式结构化输出
2. **L2 经验自动沉淀** — Summarize 完成后自动将 draft 经验写入 `l2_insights`（L2 = draft summarize 的加工产物，提供 confidence 评分和 pattern 索引）
3. **CLI 查询** — `get-l2-insights`（查询 L2 经验）、`get-draft-detail`（深查完整总结）

**待完成：**
1. **CLI 合并** — 删除冗余的 `list-drafts` 命令，将其功能合并到 `get-l2-insights`（补充 fitness/metric/run-id 过滤）
2. **Draft 历史感知 Skill** — 指导 Agent 在 plan 阶段通过 Bash 调 `get-l2-insights` 查询前序 draft 经验
3. **差异化约束** — prompt 中明确要求”先查历史，不重复已有策略”
4. **plan 阶段工具开放** — 让 Agent 在 plan 阶段能调 Bash 查询 DB

关键设计决策：
- **Draft 没有 parent**：Draft 的语义是”独立探索新方向”，不是 Mutate。它需要知道其他 draft 做了什么（简报级），但不继承代码
- **Skill 调 CLI 查询**：Agent 已有 Bash 工具，按需查询不膨胀 prompt
- **L2 = draft summarize 的索引**：每次 run 清 DB，L2 经验全部来自本 run 内前序 draft 的 summarize，不是独立知识源

### 9.3 P1：从多 Draft 进入单谱系进化

在 P0.7 完成后：

1. 单 `Mutate` 闭环（Mutate 才有 parent，继承代码做局部修改）
2. 父子 `Solution` 与 slot 级 history 真正接入
3. 再讨论选择压力、Boltzmann、population summary

### 9.4 P2：补全完整研究系统能力

只有当 P0.7/P1 稳定后，才值得做：

- Merge
- L3 跨任务规律
- compatibility rules
- 多样性维持
- 多岛 / 并行
- Agent 专业化与自进化

---

## 10. 推荐演进路线

| 阶段 | 目标 | 关键交付 | 状态 |
|---|---|---|---|
| M0 | 单 `DraftPES` 调用链打通 | BasePES + DraftPES 三阶段 | ✅ 完成 |
| M0.3 | FeatureExtractPES + GenomeSchema 模板 | FeatureExtractPES、task_stages 调度、tabular/generic 模板 | ✅ 完成 |
| M0.5 | 真实代码落盘、首次执行与事实记录 | tool-write 契约、solution.py、metrics、submission、exec_logs | ✅ 完成 |
| **M0.7** | **多次 Draft + 差异化生成** | **Summarize 固定格式 ✅、L2 写入 ✅、CLI 查询（合并中）、draft-history-review Skill、差异化约束** | **← 当前** |
| M1 | 单谱系进化 | MutatePES、parent/child、genes/snapshots 真接入 | 待开始 |
| M2 | 完整方案级搜索骨架 | MergePES、L3 回流、schema 驱动搜索 | 待开始 |
| M3 | 并行与编排 | 多任务调度、预算管理、并行执行 | 待开始 |
| M4 | 研究级评测 | MLE-bench 全量实验与 ablation | 待开始 |

当前路线约束：

**M0.7 的核心是”让系统有记忆”，而不是”让系统更聪明”。**

因为：

- 没有跨 draft 记忆，10 次 draft 等于 10 次独立随机尝试
- 有了 draft 经验沉淀（L2 = draft summarize 的索引），每次 draft 才能避免重复、逐步覆盖更大的策略空间
- 差异化生成是扩大样本池的前提，而不是优化单个方案的手段

---

## 11. 一句话架构结论

Herald2 的正确方向不是”把更多 Agent 堆起来”，而是：

**以 `TaskSpec / GenomeSchema` 定义搜索空间，以 `BasePES` 定义研究循环，以 `Workspace + HeraldDB` 定义可追踪 Harness，再在这个稳定底座上逐步长出 `Draft -> Mutate -> Merge -> Population -> Orchestrator`。**

当前系统已完成单 Draft 闭环的全部 Harness 能力和 L2 经验沉淀机制（M0~M0.5 + M0.7 部分），正在进入**多次 Draft 差异化生成**阶段。下一步是通过 CLI 合并、draft-history-review Skill 和差异化约束，使每次 Draft 能感知前序 Draft 的策略与结果（L2 = draft summarize 的索引/加工视图），避免重复探索，真正扩大样本池。
