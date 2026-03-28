# Herald2 系统架构

> **版本**: v0.1
> **更新**: 2026-03-28
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

## 5. 当前代码的真实架构（2026-03-28）

当前仓库已经实现的，不是完整进化系统，而是一个**单进程、单任务类型、串行驱动的 DraftPES MVP 闭环**。

### 5.1 目标主链路

> **图例**: ✅ 已实现 · ⬜ 待实现 · 🔄 需修改

```text
core/main.py
  │
  ├── ✅ ConfigManager.parse()
  ├── ✅ Workspace.create()
  ├── ✅ HeraldDB(...)
  ├── ✅ EventBus.get()
  ├── ✅ setup_task_dispatcher()
  ├── ⬜ bootstrap_feature_extract_pes(...)        # [NEW] 前置数据分析 PES
  │      ├── load_pes_config("config/pes/feature_extract.yaml")
  │      ├── LLMClient(...)
  │      └── FeatureExtractPES(...)
  ├── ✅ bootstrap_draft_pes(...)
  │      ├── load_pes_config("config/pes/draft.yaml")
  │      ├── LLMClient(...)
  │      └── DraftPES(...)
  │
  └── 🔄 Scheduler(task_stages=[                   # [MODIFY] 支持多阶段流水线
          ("feature_extract", 1),
          ("draft", max_tasks),
      ]).run()
          │
          ├── ⬜ Stage 1: emit(TaskDispatchEvent(task_name="feature_extract"))
          │     ▼
          │   TaskDispatcher → FeatureExtractPES.run()
          │     ├── plan:     分析竞赛描述，规划数据探索策略
          │     ├── execute:  LLM Agent 用 Bash 工具读取数据文件
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
                ├── execute:  实现代码
                └── summarize: 总结
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
  │      └── _attach_workspace_artifacts()
  │             ├── 设置 workspace_dir / solution_file_path
  │             └── 仅 touch 空的 solution.py / submission.csv
  └── summarize()                -> 渲染 draft_summarize Prompt，调 LLM，记录 llm_calls
         └── emit(TaskCompleteEvent)
```

### 5.4 当前必须明确的事实

- 当前阶段有两个生产级 PES：`FeatureExtractPES`（前置）和 `DraftPES`（主链路）
- 现在只有一个 Agent profile：`kaggle_master`
- `Scheduler` 是**串行**的，不是并行的
- `EventBus` 是**进程内总线**，不是分布式消息系统
- `AgentRegistry` 当前加载的是**prompt persona**，不是独立 Agent 进程
- `execute` 阶段目前**还不会把模型输出解析成真实代码再执行**

所以当前系统更准确的定义是：

**Herald2 目前是“以 DraftPES 为核心的可观测 Harness 原型”，还不是完整的进化式竞赛系统。**

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
| `core/pes/schema.py` | `TaskSpec` / `SlotContract` / `GenomeSchema` 最小类型 + 模板加载 | 已实现类型，模板加载待实现 |
| `config/genome_templates/` | GenomeSchema 代码模板（tabular.py / generic.py） | 待实现 |
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
| L2 Knowledge | `l2_insights`, `l2_evidence` | 保存 slot 级经验 | 已建表并有 repo，主流程未接入 |
| L3 Wisdom | `l3_wisdom`, `l3_sources` | 保存跨任务规律 | 已建表预留 |

这里要特别注意一个“定义与实现”的差异：

- 数据库结构已经定义了完整的记忆分层
- 但运行链路目前只真正用了 `solutions` 和 `llm_calls`

所以不能误判为“分层记忆已完成”，目前只是**schema 先行、闭环待补**。

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

当前真正的 Harness 由两部分构成：

- `Workspace`
- `HeraldDB`

它们的设计方向是对的，但接线还没完：

- `Workspace.save_version()` / `promote_best()` 还未接入 `DraftPES`
- `exec_logs` / `code_snapshots` / `genes` 还未在主流程产出

---

## 9. 当前缺口与真正的下一步

为了避免开发歪掉，这里要明确：**接下来最该做的，不是“再加一个更大的架构层”，而是把当前闭环补实。**

### 9.1 P0：FeatureExtractPES + 任务规格动态生成

当前 prompt 模板已经支持 `task_spec`、`schema`、`workspace`、`recent_error`、`template_content`，但生产 bootstrap 只注入了 `competition_dir`。

`TaskSpec` 不再由 bootstrap 静态构造，而是由 `FeatureExtractPES` 动态生成。因此必须补：

- 实现 `FeatureExtractPES`（plan/execute/summarize 三阶段）
- execute 阶段：LLM Agent 用工具分析数据文件，生成 TaskSpec + data_profile + 选择 GenomeSchema 模板
- 实现 GenomeSchema 模板加载（tabular.py / generic.py）
- Scheduler 支持 `task_stages` 多阶段流水线
- `FeatureExtractPES` 产出注入 `DraftPES.runtime_context`
- DraftPES prompt 模板消费 `data_profile`

### 9.2 P0：把 execute 输出沉淀成真实代码

当前 `execute` 阶段只做了两件事：

- 保存文本摘要
- `touch()` 一个空文件

必须尽快补成：

1. 从模型输出提取代码块
2. 写入 `working/solution.py`
3. 保存 `code_snapshots`
4. 执行代码
5. 记录 `exec_logs`
6. 解析 metrics / submission 路径

### 9.3 P0：让 Workspace 与 DB 真正闭环

当前 `Workspace` 里已经有：

- `history/`
- `best/`
- `save_version()`
- `promote_best()`

这意味着架构已经准备好了，只差最后接线：

- execute 成功后保存版本
- fitness 更优时 promote best
- 把产物路径更新回 `solutions`

### 9.4 P1：从单 Draft 进入单谱系进化

在 P0 完成前，不应直接做并行。

正确顺序应是：

1. 单 `Draft` 闭环补实
2. 单 `Mutate` 闭环
3. 父子 `Solution` 与 slot 级 history 真正接入
4. 再讨论选择压力、Boltzmann、population summary

### 9.5 P2：补全完整研究系统能力

只有当 P0/P1 稳定后，才值得做：

- Merge
- L2/L3 真正回流到 Plan
- compatibility rules
- 多样性维持
- 多岛 / 并行
- Agent 专业化与自进化

---

## 10. 推荐演进路线

| 阶段 | 目标 | 关键交付 |
|---|---|---|
| M0-now | 单 `DraftPES` 调用链打通 | 已完成 |
| M0.3 | FeatureExtractPES + GenomeSchema 模板 | `FeatureExtractPES` 数据分析与 TaskSpec 生成、`task_stages` 调度、tabular/generic 模板、DraftPES 消费 data_profile |
| M0.5 | 真实代码落盘与执行验证 | `solution.py` 写入、执行、metrics、submission、`exec_logs` |
| M1 | 单谱系进化 | `MutatePES`、parent/child、genes/snapshots 真接入 |
| M2 | 完整方案级搜索骨架 | `MergePES`、L2/L3 回流、schema 驱动搜索 |
| M3 | 并行与编排 | 多任务调度、预算管理、并行执行 |
| M4 | 研究级评测 | MLE-bench 全量实验与 ablation |

这里最关键的路线约束是：

**不要在 M0.5 之前实现“看起来像高级智能”的功能。**

因为：

- 没有真实执行，就没有真实反馈
- 没有真实反馈，就没有 fitness
- 没有 fitness，就没有真正的进化

---

## 11. 一句话架构结论

Herald2 的正确方向不是“把更多 Agent 堆起来”，而是：

**以 `TaskSpec / GenomeSchema` 定义搜索空间，以 `BasePES` 定义研究循环，以 `Workspace + HeraldDB` 定义可追踪 Harness，再在这个稳定底座上逐步长出 `Draft -> Mutate -> Merge -> Population -> Orchestrator`。**

当前代码已经把这个方向的骨架搭出来了，系统正从**单 `DraftPES` Harness MVP** 阶段推进到 **`FeatureExtractPES + DraftPES` 双 PES 流水线** 阶段；接下来最重要的是实现 FeatureExtractPES 动态生成 TaskSpec、GenomeSchema 模板体系，以及把 execute 产物、执行验证和知识回流真正接上。
