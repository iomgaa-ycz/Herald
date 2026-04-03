---
name: draft-history-review
description: >-
  This skill should be used when the Draft Agent needs to
  "plan a new draft", "review previous draft history",
  "query past draft experience", "differentiate strategy",
  "avoid repeating previous approaches", or
  "check what strategies have already been tried".
  Guides the agent to query L2 insights via CLI before planning,
  and choose a differentiated direction.
---

# Draft 历史感知与差异化规划

在 `DraftPES.plan` 阶段开始规划前使用。

## 何时使用

- 当前是第 2 次及以后的 draft（`generation > 0`），需要了解前序 draft 做了什么
- 需要选择一个与已有方案明确不同的探索方向
- 需要避免重复已有方案的核心策略

## 操作步骤

### Step 1：查询前序 draft 经验（必须执行）

通过 Bash 调用 `get-l2-insights` 获取本次 run 内前序 draft 的经验摘要：

```bash
python core/cli/db.py get-l2-insights --task-type <task_type> --db-path <db_path>
```

可选参数：
- `--run-id <run_id>` — 按 run 过滤（通常不需要，因为每次 run 前会清 DB）
- `--limit <N>` — 限制返回条数（默认 20）

输出为 JSON 数组，每个条目包含：

| 字段 | 说明 |
|------|------|
| `pattern` | 策略摘要（来自 summarize 的"# 摘要"段落） |
| `confidence` | 置信度评分 |
| `fitness` | 方案适应度 |
| `metric_name` / `metric_value` | 验证指标名称与数值 |
| `solution_status` | 方案状态（completed / failed） |
| `source_solution_id` | 来源 solution ID（用于深查） |

**重点关注**：
- `pattern` 告诉你前序 draft 用了什么策略
- `fitness` 和 `metric_value` 告诉你效果如何
- `solution_status` 告诉你是否成功执行

### Step 2：按需深查单个 draft（可选）

如果某个前序 draft 的策略值得深入了解（如 fitness 特别高或失败原因不明），调用 `get-draft-detail`：

```bash
python core/cli/db.py get-draft-detail --solution-id <source_solution_id> --db-path <db_path>
```

返回该 draft 的完整 `summarize_insight`（含五小节：摘要、策略选择、执行结果、关键发现、建议方向）。

### Step 3：规划差异化方向

基于查询结果，选择一个与已有方案**明确不同**的方向。差异化维度包括但不限于：

| 维度 | 差异化示例 |
|------|------------|
| 模型类型 | 前序用 LightGBM → 本次用 XGBoost 或 CatBoost 或神经网络 |
| 特征工程 | 前序用原始特征 → 本次做交叉特征 / 多项式特征 / 目标编码 |
| 验证策略 | 前序用随机切分 → 本次用 K-Fold / 时序切分 / 分层采样 |
| 数据预处理 | 前序用均值填充 → 本次用中位数填充 / 模型填充 / 删除缺失 |
| 集成策略 | 前序用单模型 → 本次用 Stacking / Blending / 加权平均 |
| 超参策略 | 前序用默认参数 → 本次做 Optuna / GridSearch 调参 |

## 禁止事项

- **不允许重复已有方案的核心策略**。如果前序 draft 已经使用 LightGBM + 原始特征，本次不能再用相同组合
- **不允许忽略查询结果**。必须在规划中明确说明"前序 draft 做了 X，本次选择 Y，原因是 Z"

## 空结果处理

如果 `get-l2-insights` 返回空数组（`[]`），说明这是本次 run 的第一个 draft，无需差异化，直接按正常流程规划即可。

## 关键概念

- **L2 = draft summarize 的索引**：`get-l2-insights` 返回的数据全部来自本 run 内前序 draft 的 summarize，不是独立知识源
- **唯一查询入口**：`get-l2-insights` 是查询前序 draft 经验的唯一 CLI 入口，深查用 `get-draft-detail`
- **每次 run 清 DB**：不存在跨 run 经验，只需关注本次 run 内的前序 draft
