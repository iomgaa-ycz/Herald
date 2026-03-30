# 035 Skill 重构 + Draft 资源配置 Skill

## 元信息
- 状态: draft
- 创建: 2026-03-30
- 序号: 035

## 背景

Plan 034 已实现运行环境检测和训练建议生成（`preview_support.py` 代码已就绪），但端到端验证发现 **建议没有被采纳**：

1. **第一层丢失**：`preview_competition.py` 输出 `n_jobs: 16`，但 FeatureExtract Agent 在编写 data_profile 时用自身判断覆写为 `n_jobs: -1`。原因：skill 没有约束"脚本输出是权威数据源"
2. **第二层丢失**：即使 data_profile 正确，`draft_plan.j2` 和 `draft_execute.j2` 也没有指示 Draft Agent 采纳 §6/§7 的资源建议

此外，对照 skill-creator 最佳实践发现：
- 现有 skill 使用第二人称（"你"/"需要"），应改为祈使句
- `report-format` 的 8 section 结构与 `feature_extract_execute.j2` 高度重复
- Draft 阶段缺少竞赛类型专属的领域知识 skill，且未来需要支持多种竞赛类型（CV/NLP），不应把所有知识塞进 j2 模板

## 变更清单

### 1. `[MODIFY]` feature-extract-data-preview/SKILL.md — 修缮

**文件**: `core/prompts/skills/feature-extract-data-preview/SKILL.md`

按 skill-creator 规范重写：
- description 改为第三人称触发短语格式
- 正文改为祈使句（imperative form）
- **新增关键约束**：在"使用约束"中加入数据权威性规则

```markdown
## 数据权威性规则

脚本输出的以下字段是经过硬件检测和算法计算的权威值，编写 data_profile 时必须忠实引用，禁止用自身推断覆写：
- 运行环境（CPU 核数、内存、GPU 信息）
- 训练建议（n_jobs 推荐值、GPU 配置、验证策略）
- 数值统计量（min/max/mean/std/skew）
```

### 2. `[MODIFY]` feature-extract-report-format/SKILL.md — 修缮

**文件**: `core/prompts/skills/feature-extract-report-format/SKILL.md`

- description 改为第三人称触发短语格式
- 正文改为祈使句
- §7 训练建议的字段说明标注数据来源约束：

```markdown
## 7. 训练建议
- 推荐模型: <引用预览工具输出的模型列表>
- n_jobs 建议: <必须引用预览工具计算的推荐值，禁止自行设定为 -1>
- GPU 建议: <引用预览工具的 GPU 检测结果>
- 验证集划分: <引用预览工具的划分策略建议>
```

### 3. `[NEW]` draft-tabular-guide/ — 新建表格竞赛 Draft Skill

**文件**: `core/prompts/skills/draft-tabular-guide/SKILL.md`

这是核心新增。当 Draft Agent 需要为**表格竞赛**编写 solution.py 时自动触发，提供：

```yaml
---
name: draft-tabular-guide
description: >-
  This skill should be used when the Draft Agent needs to write solution.py
  for a tabular competition, "configure model parameters", "set n_jobs",
  "choose validation strategy", or "translate data_profile recommendations
  into code". Provides hardware-aware parameter mapping and tabular ML
  best practices.
---
```

**SKILL.md 正文结构**（~1500 词）：

#### 核心职责
将 data_profile §6（运行环境）和 §7（训练建议）翻译为代码参数。

#### 资源参数映射表

| data_profile 字段 | 代码参数 | 映射规则 |
|-------------------|---------|---------|
| `§7.n_jobs 建议` | `LGBMClassifier(n_jobs=N)` | 直接使用推荐值，**禁止** 设为 -1 |
| `§7.n_jobs 建议` | `XGBClassifier(nthread=N)` | 同上 |
| `§7.GPU 建议: 使用` | `XGBClassifier(tree_method='gpu_hist', device='cuda')` | 仅 GPU 可用时 |
| `§7.GPU 建议: 不使用` | 不设 GPU 参数 | 默认 CPU |
| `§7.验证策略: stratified_kfold, N折` | `StratifiedKFold(n_splits=N)` | — |
| `§7.验证策略: time_based_split` | 按时间列排序后 split | — |

#### 常见反模式（必须避免）

1. `n_jobs=-1` 在高核数服务器上导致线程同步灾难（192 核实测：训练时间从 30 分钟膨胀到 5 小时）
2. 不读 data_profile 直接用默认参数
3. GPU 不可用时仍设置 `tree_method='gpu_hist'`

#### 表格竞赛 MVP 模板结构参考

```
Phase 1: 数据加载 — pd.read_csv, 列类型对齐
Phase 2: 特征工程 — 参考 data_profile §2 的特征分析
Phase 3: 模型训练 — 参考 data_profile §7 设置资源参数
Phase 4: 预测输出 — 参考 data_profile §5 的提交格式
```

#### 扩展说明
未来如需支持 CV/NLP 竞赛，创建对应的 `draft-cv-guide/` 和 `draft-nlp-guide/` skill。

### 4. `[MODIFY]` draft_plan.j2 — 补充资源配置引用

**文件**: `config/prompts/templates/draft_plan.j2`

修改第 127 行，从：
```
明确利用 `data_profile` 中的字段类型、缺失值、数据规模与 submission 约束，决定特征工程和模型复杂度。
```
改为：
```
明确利用 `data_profile` 中的字段类型、缺失值、数据规模、submission 约束、运行环境（§6）和训练建议（§7，含 n_jobs/GPU 配置），决定特征工程、模型复杂度和资源参数。
```

### 5. `[MODIFY]` draft_execute.j2 — 补充资源参数遵循

**文件**: `config/prompts/templates/draft_execute.j2`

修改第 123 行，从：
```
必须结合 `data_profile` 选择合适的数据读取、缺失值处理、特征编码与验证策略，不要忽略上游数据分析结论。
```
改为：
```
必须结合 `data_profile` 选择合适的数据读取、缺失值处理、特征编码与验证策略，不要忽略上游数据分析结论。必须按 data_profile §6（运行环境）和 §7（训练建议）设置 n_jobs、GPU、验证折数等资源参数，禁止使用 n_jobs=-1。
```

### 6. `[MODIFY]` feature_extract_execute.j2 — 去重 + 强化引用约束

**文件**: `config/prompts/templates/feature_extract_execute.j2`

当前第 83-95 行硬编码了 8 section 结构，与 `report-format/SKILL.md` 重复。简化为引用 skill：
```
## `data_profile` 固定结构要求

`data_profile` 的值必须是完整的 Markdown 文本，严格遵循 `feature-extract-report-format` skill 定义的 8 section 标题和顺序。

**数据权威性规则**: §6 运行环境和 §7 训练建议中的数值（CPU 核数、n_jobs 推荐值、GPU 信息等）必须忠实引用预览工具的脚本输出，禁止用自身推断覆写。
```

### 7. `[MODIFY]` draft.yaml — 添加 Skill 工具权限

**文件**: `config/pes/draft.yaml`

在 execute phase 的 allowed_tools 中添加 `"Skill"`：

```yaml
execute:
  allowed_tools: ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "Skill"]
```

这确保 Draft Agent 在 execute 阶段可以触发和使用 skill，与 FeatureExtract 对齐。

## 不变更的文件

- `preview_support.py` — Plan 034 已完成增强，代码无需改动
- `preview_competition.py` — 同上
- `core/pes/` — 无需改动 PES 逻辑
- `core/workspace.py` — skill 自动通过已有 symlink 暴露

## 架构决策记录

**为什么为 Draft 建独立 skill 而非只改模板？**
1. j2 模板是通用调度器，不应膨胀为领域知识库
2. 不同竞赛类型（tabular/CV/NLP）需要不同的参数映射和最佳实践
3. Skill 天然支持按竞赛类型扩展：`draft-tabular-guide/`、`draft-cv-guide/`、`draft-nlp-guide/`
4. Skill 的 progressive disclosure 机制可以在未来将详细映射表移到 `references/` 中

**为什么在 feature_extract_execute.j2 中去重？**
- 8 section 结构同时定义在 j2 和 report-format SKILL.md 中，维护两份副本容易不一致
- Skill 是该格式的唯一真值来源（single source of truth）

**Skill 工具权限（draft.yaml）是否必要？**
- **必要**。参考 FeatureExtract：其 execute phase 的 `allowed_tools` 包含 `"Skill"`，这使得 Agent 能够触发 `.claude/skills/` 下的 skill 加载
- Draft execute 当前没有 `"Skill"` → 新建的 `draft-tabular-guide` skill 无法被 Agent 访问
- 修改：`draft.yaml` execute phase `allowed_tools` 加入 `"Skill"`，与 FeatureExtract 对齐

## 验证计划

1. **Ruff 检查**: `ruff check . --fix && ruff format .`（仅验证 Python 文件无语法错误）
2. **Skill 结构验证**: 确认新 skill 目录 `draft-tabular-guide/SKILL.md` 存在且 frontmatter 正确
3. **端到端验证**: 运行 `scripts/run_real_l1.sh`，检查：
   - data_profile.md §7 的 n_jobs 不是 -1（FeatureExtract 忠实引用）
   - solution.py 中 n_jobs 与 data_profile §7 一致（Draft 采纳建议）
   - 训练完成时间合理（~30-60 分钟）
