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
     -> plan: 先通过 Skill 调 CLI 查询历史 draft 简报 + L2 经验，再规划差异化方向
     -> execute: 生成 solution.py / submission.csv
     -> summarize: 固定格式总结，写入 L2 知识
  -> 扩大样本池，积累方案级经验
```

本 TD 文档回答三个问题：

1. 第二阶段需要变更哪些模块
2. 每个变更的接口与行为应该长什么样
3. 如何验证"多次 draft + L2 知识回流 + 差异化生成"确实成立

---

## 2. 技术决策

| 决策项 | 结论 | 理由 |
|---|---|---|
| Draft 与 parent 的关系 | Draft 没有 parent，每次独立探索 | Draft 的语义是"从零探索新方向"，不是 Mutate；parent 意味着继承完整代码，但 draft 只需知道前序策略简报 |
| 历史信息传递方式 | Skill 调 CLI 查询 DB | Agent 已有 Bash 工具，按需查询不膨胀 prompt；Agent 更容易学会通过 bash 调用接口 |
| Summarize 输出格式 | 固定五小节结构，每节一段逻辑通顺的话 | 消费者是 LLM Agent，段落比列点更能表达因果关系 |
| L2 知识写入时机 | Summarize 阶段结束后 | 此时 metrics / exec_logs 已确定，信息完整 |
| L2 知识粒度 | 方案级（整体策略 + 结果），不做 slot 级拆分 | MVP 阶段先粗后细 |
| 差异化机制 | Skill 引导 + prompt 约束 | 先靠 prompt 引导，不做 banned strategy list |
| Draft 次数预期 | 10+ 次 | 真正扩大样本池，CLI 查询需做截断控制（list-drafts 默认 limit 20） |
| plan 阶段工具开放 | 开放 Bash | 让 Agent 在 plan 阶段能通过 Bash 调 CLI 查询 DB 历史 |

---

## 3. 范围与非范围

### 3.1 本阶段必须完成

- Draft Summarize 固定格式输出（五小节段落式）
- Summarize 完成后写入 L2 知识（`l2_insights` + `l2_evidence`）
- CLI 新增 `list-drafts` 命令（返回所有 draft 的简报，含截断控制）
- CLI 新增 `get-draft-detail` 命令（按需深查单个 draft 的完整 summarize_insight）
- CLI 新增 `get-l2-insights` 命令（返回活跃的 L2 经验）
- 新建 Skill: `draft-history-review`（指导 Agent 在 plan 阶段查询历史并规划差异化）
- `draft_plan.j2` 增加差异化约束文本
- `draft_summarize.j2` 更新为固定格式要求
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

**文件**: `core/cli/db.py`
**变更类型**: MODIFY — 新增三个命令

**文件**: `core/database/repositories/solution.py`
**变更类型**: MODIFY — 新增查询方法

#### `list-drafts` 命令

列出当前 run 的所有 draft solution 简报。

```bash
python core/cli/db.py list-drafts --run-id <run_id> --db-path <path>
# 可选: --limit N (默认 20)
# 可选: --status completed|failed|all (默认 all)
```

输出 JSON 数组，每个元素只包含摘要级信息：

```json
[
  {
    "solution_id": "...",
    "generation": 1,
    "status": "completed",
    "fitness": 0.8123,
    "metric_name": "auc",
    "metric_value": 0.8123,
    "summary_excerpt": "（从 summarize_insight 的 # 摘要 小节提取的第一段，截断到 300 字符）"
  }
]
```

设计理由：
- 10+ 次 draft 时，完整 summarize_insight 会过长，简报足够 Agent 判断是否需要深查
- `summary_excerpt` 的截断逻辑与 L2 写入的 `pattern` 提取逻辑共用同一函数

#### `get-draft-detail` 命令

获取单个 draft 的完整 summarize_insight。

```bash
python core/cli/db.py get-draft-detail --solution-id <uuid> --db-path <path>
```

输出包含完整 `summarize_insight` 的 JSON 对象。Agent 在 `list-drafts` 看到感兴趣的条目后按需深查。

#### `get-l2-insights` 命令

获取活跃的 L2 经验。

```bash
python core/cli/db.py get-l2-insights --task-type tabular --db-path <path>
# 可选: --limit N (默认 20)
```

输出 JSON 数组，每个元素包含 `slot`、`pattern`、`insight`（截断）、`confidence`、`status`。

#### Repository 层变更

`SolutionRepository` 新增：

```python
def list_by_run_and_operation(
    self,
    run_id: str,
    operation: str,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """查询指定 run 下某操作类型的 solution 列表。"""
```

### 4.4 Draft 历史感知 Skill

**文件**: `core/prompts/skills/draft-history-review/SKILL.md` [NEW]
**变更类型**: NEW

Skill 内容要点：

1. **必须执行**：在 draft_plan 阶段开始规划前，先调用 `list-drafts` 查看当前 run 已有的 draft 方案
2. **建议执行**：调用 `get-l2-insights` 查看已积累的方案级经验
3. **按需深查**：对感兴趣的 draft 调用 `get-draft-detail` 获取完整总结
4. **差异化规划**：基于查询结果，选择一个与已有方案明确不同的方向（不同模型、不同特征工程策略、不同验证策略等）
5. **禁止重复**：不允许重复已有方案的核心策略

Skill 中提供具体的 CLI 调用示例，降低 Agent 学习成本。

### 4.5 draft_plan.j2 差异化约束

**文件**: `config/prompts/templates/draft_plan.j2`
**变更类型**: MODIFY — 新增差异化约束段落

在现有"任务要求"之前新增：

```jinja2
{% if generation > 0 %}
# 差异化要求

本次 draft 是独立探索，不是对某个已有方案的改进。
你必须先通过 Bash 调用 `python core/cli/db.py list-drafts --run-id {{ run_id }} --db-path {{ db_path }}` 查询当前 run 已有的 draft 方案。
如果已有方案，你必须选择一个明确不同的方向（不同模型、不同特征工程策略、不同验证策略等）。
不允许重复已有方案的核心策略。
{% endif %}
```

关键设计：
- `generation > 0` 条件判断：第一次 draft 无需查询历史
- 提供具体的 CLI 命令，减少 Agent 猜测
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

### 5.1 Task 1：Draft Summarize 固定格式

**目标**: 让 summarize 输出结构化、可解析、可被后续 draft 消费。

**要干什么**

- 重写 `config/prompts/templates/draft_summarize.j2` 的输出格式要求
- 五个固定小节：摘要 / 策略选择 / 执行结果 / 关键发现 / 建议方向
- 每个小节必须是一段逻辑通顺的话

**涉及文件**

- `config/prompts/templates/draft_summarize.j2` [MODIFY]

**测试通过标准**

- 回放 case 验证输出满足固定五小节结构
- 每个小节是段落而非列点

### 5.2 Task 2：Summarize 阶段写入 L2

**目标**: 让每次 draft 的经验自动沉淀到 L2 知识层。

**要干什么**

- 在 `DraftPES.handle_phase_response` 的 summarize 分支新增 `_write_l2_knowledge()` 方法
- 从 summarize_insight 的 "# 摘要" 小节提取第一段作为 pattern
- 调用 `L2Repository.upsert_insight()`
- completed 方案用 `evidence_type="support"`，failed 方案用 `evidence_type="contradict"`
- 失败时仅 warn，不阻塞主链路

**涉及文件**

- `core/pes/draft.py` [MODIFY]

**测试通过标准**

- 成功 case 验证 `l2_insights` 表中有条目
- 失败 case 验证 `l2_evidence` 中 `evidence_type="contradict"`
- L2 写入失败不影响 solution 状态

### 5.3 Task 3：CLI 新增 list-drafts / get-draft-detail / get-l2-insights

**目标**: 让 Agent 能通过 Bash 按需查询历史 draft 和 L2 经验。

**要干什么**

- 在 `core/cli/db.py` 新增三个命令
- 在 `core/database/repositories/solution.py` 新增 `list_by_run_and_operation()` 方法
- 实现 `summary_excerpt` 提取逻辑（从 summarize_insight 的 # 摘要小节提取第一段，截断 300 字符）

**涉及文件**

- `core/cli/db.py` [MODIFY]
- `core/database/repositories/solution.py` [MODIFY]

**测试通过标准**

- `list-drafts` 输出 JSON 格式正确，含 `summary_excerpt`
- `get-draft-detail` 返回完整 `summarize_insight`
- `get-l2-insights` 返回 L2 经验列表
- `--limit` 参数生效

### 5.4 Task 4：新建 draft-history-review Skill

**目标**: 指导 Agent 在 plan 阶段查询历史并规划差异化方向。

**要干什么**

- 创建 `core/prompts/skills/draft-history-review/SKILL.md`
- 包含具体的 CLI 调用示例
- 明确"必须查询" vs "建议查询" vs "按需深查"的层次

**涉及文件**

- `core/prompts/skills/draft-history-review/SKILL.md` [NEW]

**测试通过标准**

- Skill 文件存在且可被 project skill 机制发现
- CLI 调用示例中的命令格式与 Task 3 实现一致

### 5.5 Task 5：draft_plan 差异化约束 + plan 阶段开放 Bash

**目标**: 让 Agent 在 plan 阶段能查询历史，并被明确要求差异化。

**要干什么**

- 修改 `config/prompts/templates/draft_plan.j2`，新增差异化约束段落（`generation > 0` 条件渲染）
- 修改 `config/pes/draft.yaml`，plan phase 添加 `allowed_tools: ["Bash"]` 和 `max_turns: 3`
- 确保 `generation` 和 `run_id`、`db_path` 变量在 plan prompt context 中可用

**涉及文件**

- `config/prompts/templates/draft_plan.j2` [MODIFY]
- `config/pes/draft.yaml` [MODIFY]
- `core/pes/draft.py` [MODIFY]（如需补充 prompt context 变量）

**测试通过标准**

- `generation=0` 时不渲染差异化段落
- `generation>0` 时渲染差异化段落，含正确的 CLI 命令
- plan phase 的 `allowed_tools` 包含 `"Bash"`
- plan phase 的 `max_turns` 为 3

### 5.6 Task 6：端到端验证

**目标**: 在真实场景下验证多次 draft + L2 知识回流 + 差异化生成。

**要干什么**

- 配置 `task_stages=[("feature_extract", 1), ("draft", 3)]`
- 验证第 2、3 次 draft 的 plan 阶段能查到前序 draft 简报
- 验证 `l2_insights` 表中有条目
- 验证后续 draft 的策略与前序明确不同
- 验证 10+ 次 draft 时 `list-drafts --limit` 截断正常

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

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `config/prompts/templates/draft_summarize.j2` | MODIFY | 固定五小节段落式输出格式 |
| `config/prompts/templates/draft_plan.j2` | MODIFY | 新增差异化约束段落 |
| `config/pes/draft.yaml` | MODIFY | plan phase 开放 Bash、max_turns 调整 |
| `core/pes/draft.py` | MODIFY | L2 写入 + prompt context 补充 |
| `core/cli/db.py` | MODIFY | 新增 list-drafts / get-draft-detail / get-l2-insights |
| `core/database/repositories/solution.py` | MODIFY | 新增 list_by_run_and_operation() |
| `core/prompts/skills/draft-history-review/SKILL.md` | NEW | 历史感知 Skill |

---

## 8. 一句话结论

第二阶段的核心不是让系统"更聪明"，而是让系统"有记忆"——通过固定格式的 Summarize、L2 知识写入、CLI 查询和差异化约束，使 10+ 次 Draft 不再是 10 次独立随机尝试，而是逐步覆盖更大策略空间的有方向探索。
