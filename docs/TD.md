# 技术方案（TD）— Herald2 第二阶段

> **状态**: v0.2
> **更新**: 2026-03-31
> **目标阶段**: 多次 Draft + L2 知识回流 + 差异化生成

---

## 1. 摘要

第一阶段（M0~M0.5）已完成单 Draft 闭环的全部 Harness 能力。当前系统的核心缺口是：**多次 draft 之间没有信息传递，每次 draft 都是"从零开始"**。

即使 Scheduler 支持 `draft` stage 运行 N 次，第 10 次 draft 和第 1 次 draft 看到的上下文完全相同——系统没有记忆，无法避免重复探索。

第二阶段的主链路：

```text
main.py
  -> Scheduler(task_stages=[("feature_extract", 1), ("draft", N)])
  -> FeatureExtractPES(1次) -> TaskSpec + data_profile
  -> DraftPES(N次，每次独立探索)
     -> plan: 先通过 Skill 调 CLI 查询前序 draft 经验（get-l2-insights），再规划差异化方向
     -> execute: 生成 solution.py / submission.csv
     -> summarize: 固定格式总结，自动写入 L2（L2 = draft summarize 的索引/加工视图）
  -> 扩大样本池，积累方案级经验
```

**关键概念澄清**：每次 run 前清除 DB，不存在跨 run 经验。L2 不是独立于 draft 的知识层——`l2_insights` 中的数据全部来自本 run 内前序 draft 的 summarize_insight 经 `_write_l2_knowledge()` 处理后写入。Agent 获取前序 draft 经验的唯一 CLI 入口是 `get-l2-insights`（含 confidence 评分和 pattern 索引），深查用 `get-draft-detail`。

本 TD 文档回答三个问题：

1. 第二阶段需要变更哪些模块
2. 每个变更的接口与行为应该长什么样
3. 如何验证"多次 draft + 差异化生成"确实成立

---

## 2. 技术决策

| 决策项 | 结论 | 理由 |
|---|---|---|
| Draft 与 parent 的关系 | Draft 没有 parent，每次独立探索 | Draft 的语义是"从零探索新方向"，不是 Mutate；parent 意味着继承完整代码，但 draft 只需知道前序策略简报 |
| 历史信息传递方式 | Skill 调 `get-l2-insights` CLI 查询 | Agent 已有 Bash 工具，按需查询不膨胀 prompt；L2 = draft summarize 的索引，单一入口避免概念混淆 |
| Summarize 输出格式 | 固定五小节结构，每节一段逻辑通顺的话 | 消费者是 LLM Agent，段落比列点更能表达因果关系 |
| L2 知识写入时机 | Summarize 阶段结束后 | 此时 metrics / exec_logs 已确定，信息完整 |
| L2 的真实语义 | L2 = draft summarize 的索引/加工视图 | 每次 run 清 DB，不存在跨 run 经验；L2 提供 confidence 评分和 pattern 索引，但数据源就是 draft summarize |
| L2 知识粒度 | 方案级（整体策略 + 结果），不做 slot 级拆分 | MVP 阶段先粗后细 |
| 差异化机制 | Skill 引导 + prompt 约束 | 先靠 prompt 引导，不做 banned strategy list |
| Draft 次数预期 | 10+ 次 | 真正扩大样本池，CLI 查询需做截断控制（list-drafts 默认 limit 20） |
| plan 阶段工具开放 | 开放 Bash | 让 Agent 在 plan 阶段能通过 Bash 调 CLI 查询 DB 历史 |

---

## 3. 范围与非范围

### 3.1 本阶段必须完成

- ✅ Draft Summarize 固定格式输出（五小节段落式）
- ✅ Summarize 完成后写入 L2（`l2_insights` + `l2_evidence`）
- ✅ CLI 新增 `get-draft-detail` 命令（按需深查单个 draft 的完整 summarize_insight）
- ✅ CLI 新增 `get-l2-insights` 命令（返回活跃的 L2 经验）
- ~~CLI 新增 `list-drafts` 命令~~ → 已合并到 `get-l2-insights`（见 Task 3.5）
- 合并 CLI：删除 `list-drafts`，增强 `get-l2-insights`（补充 fitness/metric/run-id 过滤）
- 新建 Skill: `draft-history-review`（指导 Agent 在 plan 阶段调 `get-l2-insights` 查询前序 draft 经验并规划差异化）
- `draft_plan.j2` 增加差异化约束文本
- `config/pes/draft.yaml` plan phase 开放 Bash 工具
- 运行 N 次 draft 时，后续 draft 能感知前序 draft 的策略与结果

### 3.2 本阶段明确不做

- MutatePES / MergePES
- parent_solution 在 Draft 中的使用（Draft 没有 parent）
- slot 级 L2 拆分
- 种群选择 / Boltzmann
- 并行执行
- L3 跨任务规律

---

## 4. 模块设计

### 4.1 Draft Summarize 固定格式

**文件**: `config/prompts/templates/draft_summarize.j2`
**变更类型**: MODIFY — 重写输出格式要求

当前 `draft_summarize.j2` 使用列点式结构（高价值经验 / 最终总结 / 下轮建议 / 迭代方向），信息密度低且不利于 LLM 消费。

新格式固定为五个小节，每个小节必须是一段逻辑通顺的话，不是列点：

```text
# 摘要
（一段话：策略 + 结果 + 核心发现）

# 策略选择
（一段话：模型、特征工程、验证策略、资源配置的选择及原因）

# 执行结果
（一段话：指标值、耗时、submission 状态、是否符合预期）

# 关键发现
（一段话：有因果逻辑的分析，不是孤立事实）

# 建议方向
（一段话：下次应该尝试什么不同的方向，为什么）
```

设计理由：
- **段落而非列点**：消费者是 LLM Agent，段落能表达因果关系和逻辑链条，列点只能罗列孤立事实
- **摘要在前**：`list-drafts` CLI 只提取第一小节的第一段（截断到 300 字符），作为可扫描简报
- **五个小节足够**：覆盖"做了什么 → 为什么这么做 → 结果如何 → 学到什么 → 下步建议"的完整闭环

### 4.2 L2 知识写入

**文件**: `core/pes/draft.py` — `handle_phase_response` 的 summarize 分支
**变更类型**: MODIFY — summarize 完成后新增 L2 写入逻辑

写入链路：

```text
DraftPES.handle_phase_response(phase="summarize")
  ├── 现有逻辑：设置 summarize_insight、status、archive、emit
  └── [NEW] _write_l2_knowledge()
        ├── 从 summarize_insight 的 "# 摘要" 小节提取第一段作为 pattern
        ├── 调用 L2Repository.upsert_insight()
        │     slot = "strategy"        # 方案级，不做 slot 拆分
        │     task_type = task_spec.task_type
        │     pattern = 摘要第一段
        │     insight = 完整 summarize_insight
        │     solution_id = solution.id
        │     evidence_type = "support"（completed）/ "contradict"（failed）
        └── 失败时仅 warn，不阻塞主链路
```

关键约束：
- `L2Repository` 已实现 `upsert_insight` / `get_insights`，直接调用即可
- L2 写入失败不应影响 solution 状态或 TaskCompleteEvent 发出
- `slot = "strategy"` 是 MVP 阶段的固定值，后续 MutatePES 可做 slot 级拆分

### 4.3 CLI 查询扩展

**状态**: ✅ 已完成基础实现，待 Task 3.5 合并优化

**已实现**：

#### `get-l2-insights` 命令（主查询入口）

获取前序 draft 经验（L2 = draft summarize 的索引/加工视图）。

```bash
python core/cli/db.py get-l2-insights --task-type tabular --db-path <path>
# 可选: --limit N (默认 20)
```

当前输出 JSON 数组含 `slot`、`pattern`、`insight`（截断）、`confidence`、`status`。

**Task 3.5 将增强此命令**：新增 `--run-id` 过滤、补充 fitness/metric 信息、删除冗余的 `list-drafts`。

#### `get-draft-detail` 命令

获取单个 draft 的完整 summarize_insight。

```bash
python core/cli/db.py get-draft-detail --solution-id <uuid> --db-path <path>
```

Agent 在 `get-l2-insights` 看到感兴趣的条目后按需深查。

#### ~~`list-drafts` 命令~~（已废弃，将在 Task 3.5 删除）

原设计将 `list-drafts` 和 `get-l2-insights` 作为两个独立入口，但实际上 L2 = draft summarize 的加工产物，两者查询同一来源数据。Task 3.5 将删除 `list-drafts` 并将其功能（fitness/metric/run-id）合并到 `get-l2-insights`。

#### Repository 层

`SolutionRepository.list_by_run_and_operation()` 已实现（被 `list-drafts` 使用，Task 3.5 删除 `list-drafts` 后将由增强版 `get-l2-insights` 复用或替代）。

### 4.4 Draft 历史感知 Skill

**文件**: `core/prompts/skills/draft-history-review/SKILL.md` [NEW]
**变更类型**: NEW

Skill 内容要点：

1. **必须执行**：在 draft_plan 阶段开始规划前，先调用 `get-l2-insights` 查看前序 draft 经验（L2 = draft summarize 的索引，含 confidence、pattern、fitness/metric 信息）
2. **按需深查**：对感兴趣的条目调用 `get-draft-detail` 获取完整 summarize_insight
3. **差异化规划**：基于查询结果，选择一个与已有方案明确不同的方向（不同模型、不同特征工程策略、不同验证策略等）
4. **禁止重复**：不允许重复已有方案的核心策略

Skill 中提供具体的 CLI 调用示例，降低 Agent 学习成本。`get-l2-insights` 是唯一查询入口，不再需要单独查 `list-drafts`。

### 4.5 draft_plan.j2 差异化约束

**文件**: `config/prompts/templates/draft_plan.j2`
**变更类型**: MODIFY — 新增差异化约束段落

在现有"任务要求"之前新增：

```jinja2
{% if generation > 0 %}
# 差异化要求

本次 draft 是独立探索，不是对某个已有方案的改进。
你必须先通过 Bash 调用 `python core/cli/db.py get-l2-insights --task-type {{ task_spec.task_type }} --run-id {{ run_id }} --db-path {{ db_path }}` 查询前序 draft 经验。
如果已有方案，你必须选择一个明确不同的方向（不同模型、不同特征工程策略、不同验证策略等）。
不允许重复已有方案的核心策略。
{% endif %}
```

关键设计：
- `generation > 0` 条件判断：第一次 draft 无需查询历史
- 唯一查询入口是 `get-l2-insights`（L2 = draft summarize 的索引）
- 差异化是"要求"不是"建议"，prompt 中使用"必须"

### 4.6 DraftPES plan 阶段工具开放

**文件**: `config/pes/draft.yaml`
**变更类型**: MODIFY — plan phase 新增 `allowed_tools`

当前 plan phase 没有工具，Agent 无法在 plan 阶段调 CLI 查询历史。需要开放 Bash。

```yaml
phases:
  plan:
    max_retries: 1
    allowed_tools: ["Bash"]    # [MODIFY] 开放 Bash 供查询历史
    max_turns: 3               # [MODIFY] 允许多轮对话（查询 + 规划）
  execute:
    # ... 不变
  summarize:
    # ... 不变
```

变更说明：
- `allowed_tools: ["Bash"]`：让 Agent 能在 plan 阶段通过 Bash 调 CLI
- `max_turns: 3`：plan 阶段需要至少一轮查询 + 一轮规划，预留一轮兜底

---

## 5. 下一步任务清单

### 5.1 Task 1：Draft Summarize 固定格式 ✅

**状态**: 已完成（计划 039）

### 5.2 Task 2：Summarize 阶段写入 L2 ✅

**状态**: 已完成（计划 040）

**澄清**：L2 = draft summarize 的索引/加工视图，不是独立于 draft 的知识层。`_write_l2_knowledge()` 从 summarize_insight 提取 pattern 写入 `l2_insights`，提供 confidence 评分机制。

### 5.3 Task 3：CLI 新增 get-draft-detail / get-l2-insights ✅

**状态**: 已完成（计划 041）

**已实现**:
- `get-draft-detail`：返回完整 `summarize_insight`
- `get-l2-insights`：返回 L2 经验列表
- `list-drafts`：已实现但将在 Task 3.5 中删除并合并到 `get-l2-insights`
- `SolutionRepository.list_by_run_and_operation()` 已实现

### 5.3.5 Task 3.5：合并 CLI — 删除 list-drafts，增强 get-l2-insights

**目标**: 消除冗余 CLI 入口。L2 = draft summarize 的索引，不需要 `list-drafts` 和 `get-l2-insights` 两个独立命令。

**要干什么**

- 删除 `core/cli/db.py` 中的 `cmd_list_drafts` 函数和 argparse 注册
- 增强 `get-l2-insights`：
  - 新增 `--run-id` 可选参数（通过 `l2_evidence.solution_id` JOIN `solutions.run_id` 过滤）
  - 输出补充每条 insight 对应 solution 的 fitness / metric_name / metric_value / solution_status
  - 实现方式：`L2Repository` 新增查询方法 JOIN `l2_evidence` + `solutions`，或在 CLI 层做二次查询（MVP 优先）
- 删除 `tests/unit/test_cli_db.py` 中 `list-drafts` 相关测试
- 更新 `get-l2-insights` 测试以验证新增字段

**增强后 `get-l2-insights` 输出格式**

```json
[
  {
    "id": 1,
    "slot": "strategy",
    "pattern": "...",
    "insight": "...(截断500字符)",
    "confidence": 1.5,
    "status": "active",
    "source_solution_id": "uuid",
    "fitness": 0.8123,
    "metric_name": "auc",
    "metric_value": 0.8123,
    "solution_status": "completed"
  }
]
```

**涉及文件**

- `core/cli/db.py` [MODIFY] — 删除 list-drafts，增强 get-l2-insights
- `core/database/repositories/l2.py` 或 `core/database/herald_db.py` [MODIFY] — 增强查询
- `tests/unit/test_cli_db.py` [MODIFY] — 删除/更新测试

**测试通过标准**

- `list-drafts` 命令不再存在
- `get-l2-insights --task-type tabular --run-id <id>` 返回含 fitness/metric 信息的 JSON
- 不传 `--run-id` 时返回全部 L2 经验
- `--limit` 参数生效

### 5.4 Task 4：新建 draft-history-review Skill

**目标**: 指导 Agent 在 plan 阶段查询前序 draft 经验并规划差异化方向。

**要干什么**

- 创建 `core/prompts/skills/draft-history-review/SKILL.md`
- 包含具体的 CLI 调用示例
- **唯一查询入口是 `get-l2-insights`**（L2 = draft summarize 的索引），深查用 `get-draft-detail`
- 明确"必须查询" vs "按需深查"的层次：
  1. **必须执行**：调 `get-l2-insights` 查看前序 draft 经验（含 confidence、pattern、fitness）
  2. **按需深查**：对感兴趣的条目调 `get-draft-detail` 获取完整 summarize_insight
  3. **差异化规划**：基于查询结果选择与已有方案明确不同的方向

**涉及文件**

- `core/prompts/skills/draft-history-review/SKILL.md` [NEW]

**前置依赖**

- Task 3.5（CLI 合并）完成后，Skill 中的 CLI 示例需使用增强后的 `get-l2-insights` 命令格式

**测试通过标准**

- Skill 文件存在且可被 project skill 机制发现
- CLI 调用示例中的命令格式与增强后的 `get-l2-insights` 一致

### 5.5 Task 5：draft_plan 差异化约束 + plan 阶段开放 Bash

**目标**: 让 Agent 在 plan 阶段能查询前序 draft 经验，并被明确要求差异化。

**要干什么**

- 修改 `config/prompts/templates/draft_plan.j2`，新增差异化约束段落（`generation > 0` 条件渲染）
- 差异化约束中引导 Agent 调 `get-l2-insights`（唯一查询入口），不再引导调 `list-drafts`
- 修改 `config/pes/draft.yaml`，plan phase 添加 `allowed_tools: ["Bash"]` 和 `max_turns: 3`
- 确保 `generation` 和 `run_id`、`db_path` 变量在 plan prompt context 中可用

**涉及文件**

- `config/prompts/templates/draft_plan.j2` [MODIFY]
- `config/pes/draft.yaml` [MODIFY]
- `core/pes/draft.py` [MODIFY]（如需补充 prompt context 变量）

**前置依赖**

- Task 3.5（CLI 合并）完成后，prompt 中的 CLI 示例需使用增强后的 `get-l2-insights` 命令格式

**测试通过标准**

- `generation=0` 时不渲染差异化段落
- `generation>0` 时渲染差异化段落，含 `get-l2-insights` CLI 命令（非 `list-drafts`）
- plan phase 的 `allowed_tools` 包含 `"Bash"`
- plan phase 的 `max_turns` 为 3

### 5.6 Task 6：端到端验证

**目标**: 在真实场景下验证多次 draft + 差异化生成。

**要干什么**

- 配置 `task_stages=[("feature_extract", 1), ("draft", 3)]`
- 验证第 2、3 次 draft 的 plan 阶段能通过 `get-l2-insights` 查到前序 draft 经验
- 验证 `l2_insights` 表中有条目（= 前序 draft summarize 的索引）
- 验证后续 draft 的策略与前序明确不同
- 验证 10+ 次 draft 时 `get-l2-insights --limit` 截断正常

**涉及文件**

- 无新增文件，使用已有测试框架

**测试通过标准**

- 3 次 draft 端到端跑通
- 第 2 次 draft 的 plan 输出中包含对第 1 次 draft 的引用或差异化说明
- `l2_insights` 表中至少有 3 条记录
- 每次 draft 的核心策略（模型类型或特征工程方法）互不相同

---

## 6. 验证计划

### 6.1 单元测试

- Summarize 格式解析：验证固定五小节结构能被正确识别
- `summary_excerpt` 提取：验证从 summarize_insight 中提取摘要第一段的逻辑
- L2 写入：验证 `_write_l2_knowledge()` 在成功/失败 case 下的行为
- CLI 命令：验证 `list-drafts` / `get-draft-detail` / `get-l2-insights` 的输出格式
- Prompt 渲染：验证 `draft_plan.j2` 在 `generation=0` 和 `generation>0` 时的差异

### 6.2 集成测试

- 3 次 draft 端到端：验证历史感知和差异化生成
- L2 回流链路：draft A summarize → L2 写入 → draft B plan 查询 → 差异化规划

### 6.3 功能测试

真实竞赛（tabular-playground-series-may-2022）跑 3 次 draft，验证：
- 每次 draft 的 summarize_insight 满足固定格式
- `l2_insights` 表中有 3 条记录
- 后续 draft 的策略与前序不同

---

## 7. 涉及文件汇总

| 文件 | 变更类型 | 说明 | 状态 |
|------|----------|------|------|
| `config/prompts/templates/draft_summarize.j2` | MODIFY | 固定五小节段落式输出格式 | ✅ |
| `core/pes/draft.py` | MODIFY | L2 写入 | ✅ |
| `core/cli/db.py` | MODIFY | get-draft-detail / get-l2-insights | ✅（Task 3.5 将删除 list-drafts 并增强 get-l2-insights） |
| `core/database/repositories/solution.py` | MODIFY | list_by_run_and_operation() | ✅ |
| `core/cli/db.py` | MODIFY | 删除 list-drafts，增强 get-l2-insights | Task 3.5 待完成 |
| `core/database/repositories/l2.py` | MODIFY | 增强查询（JOIN solution 信息） | Task 3.5 待完成 |
| `config/prompts/templates/draft_plan.j2` | MODIFY | 差异化约束（引导调 get-l2-insights） | Task 5 待完成 |
| `config/pes/draft.yaml` | MODIFY | plan phase 开放 Bash、max_turns 调整 | Task 5 待完成 |
| `core/prompts/skills/draft-history-review/SKILL.md` | NEW | 历史感知 Skill（唯一入口 get-l2-insights） | Task 4 待完成 |

---

## 8. 一句话结论

第二阶段的核心不是让系统"更聪明"，而是让系统"有记忆"——通过固定格式的 Summarize、draft 经验自动沉淀（L2 = draft summarize 的索引/加工视图）、统一的 `get-l2-insights` 查询入口和差异化约束，使 10+ 次 Draft 不再是 10 次独立随机尝试，而是逐步覆盖更大策略空间的有方向探索。
