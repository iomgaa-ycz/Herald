# 031：实现 FeatureExtract 的 `data_profile.md` 格式化 skill

## 元信息
- 状态: completed
- 创建: 2026-03-29
- 对应 TD: Task 15（§6.15）

## 1.1 摘要

当前 `data_profile` 只是一段不定长纯文本（如"训练集800,000样本，测试集100,000样本…"），既不可读也无法被下游 `DraftPES` 稳定消费。本任务新建 `feature-extract-report-format` project skill，定义 `data_profile.md` 的固定 Markdown 标题结构与最小字段覆盖，并修改 `feature_extract_execute.j2` 指令让 LLM 输出遵循该固定结构，使 `DraftPES` 的 plan / execute prompt 能稳定消费结构化数据报告。

## 1.2 审查点（Review Required）

1. **data_profile 产出机制不变**
   `data_profile` 仍作为 JSON payload 的 `"data_profile"` 字段输出，但其值从"一段话总结"升级为"固定标题结构的 Markdown 文本"。`FeatureExtractPES._handle_execute_response` 的解析逻辑不需要改。

2. **SKILL.md 内容边界**
   `feature-extract-report-format/SKILL.md` 只提供模板规范说明，不包含可执行脚本（区别于 Task 14 的 `feature-extract-data-preview`）。Agent 在 execute 阶段写 `data_profile` 时参考该 skill 的格式约束。

3. **回放资产需更新**
   现有 `tests/cases/replays/feature_extract_tabular_success_v1/` 的 `execute_raw.txt` 和 `expected.json` 中的 `data_profile` 是一段话格式，需更新为固定结构 Markdown 以匹配新测试断言。

## 1.3 伪代码 / 数据流

```text
FeatureExtractPES.execute()
  ├── Agent 运行 preview skill 脚本获取原始事实
  ├── Agent 参照 feature-extract-report-format SKILL.md 格式约束  ← [NEW]
  ├── Agent 输出 JSON payload:
  │     {
  │       "task_spec": {...},
  │       "data_profile": "# 数据概况报告\n\n## 1. 数据集概览\n...",  ← 固定标题结构
  │       "genome_template": "tabular"
  │     }
  ├── _handle_execute_response() 解析 JSON（不变）
  └── _persist_data_profile() 写入 working/data_profile.md（不变）

DraftPES.plan() / DraftPES.execute()
  └── draft_plan.j2 / draft_execute.j2 中 {{ data_profile }} 渲染固定结构 Markdown（无需改模板）
```

## 1.4 拟议变更（Proposed Changes）

### A. 新增 report-format skill

- `core/prompts/skills/feature-extract-report-format/SKILL.md` [NEW]
  - 定义 `data_profile.md` 的固定标题结构（6 个 section）
  - 提供最小字段覆盖范围说明
  - 给出格式示例

固定标题结构：

```markdown
# 数据概况报告

## 1. 数据集概览
- 竞赛名称
- 任务类型（分类/回归/…）
- 训练集规模（行 × 列）
- 测试集规模（行 × 列）

## 2. 特征分析
- 数值特征列表与统计（均值/std/min/max 或类型说明）
- 类别特征列表与基数
- 高基数特征（唯一值 > 1000）

## 3. 缺失值
- 缺失列名与缺失比例
- 若无缺失值，明确写"无缺失值"

## 4. 目标变量
- 列名
- 类型（连续/二分类/多分类）
- 分布描述（类别比例或值域范围）

## 5. 提交格式
- 提交文件列顺序
- ID 列
- 目标列
- 行数约束（应与 test 行数一致）

## 6. 关键发现与建模建议
- 竞赛描述中的特殊提示
- 数据特性对建模方案的影响
```

### B. 修改 feature_extract_execute.j2

- `config/prompts/templates/feature_extract_execute.j2` [MODIFY]
  - 在"输出格式"部分将 `data_profile` 的描述从"数据概况报告：包含…"改为要求遵循固定 Markdown 标题结构
  - 明确列出 6 个必需 section 的标题
  - 强调 `data_profile` 的值是完整 Markdown 文本（含标题和区块）

### C. 更新回放资产

- `tests/cases/replays/feature_extract_tabular_success_v1/execute_raw.txt` [MODIFY]
  - `data_profile` 字段改为固定结构 Markdown
- `tests/cases/replays/feature_extract_tabular_success_v1/expected.json` [MODIFY]
  - 同步更新 `data_profile` 期望值
- `tests/cases/replays/feature_extract_degraded_v1/execute_raw.txt` [MODIFY]
  - 降级 case 同样遵循标题结构（部分 section 可标注"信息不足"）
- `tests/cases/replays/feature_extract_degraded_v1/expected.json` [MODIFY]
  - 同步更新

### D. 补充测试断言

- `tests/unit/test_feature_extract_pes.py` [MODIFY]
  - [NEW] `test_report_format_skill_exists_and_complete()` — 验证 skill 目录存在，SKILL.md 包含 6 个 section 标题
  - [MODIFY] 已有回放测试（`test_parse_real_tabular_replay` / `test_execute_phase_with_real_replay` / `test_full_cycle_with_real_replay`）在回放资产更新后自动覆盖新格式
  - [NEW] `test_data_profile_has_required_sections()` — 断言解析出的 data_profile 包含 6 个固定标题

- `tests/integration/test_feature_extract_skill_flow.py` [MODIFY]
  - [NEW] `test_report_format_skill_visible_in_working()` — 验证 report-format skill 可通过 `expose_project_skills()` 暴露到 working

### E. 文档同步

- `docs/TD.md` [MODIFY]
  - Task 15 状态从 ⬜ 改为 ✅

## 1.5 验证计划

1. `pytest tests/unit/test_feature_extract_pes.py -v` — 全部通过
2. `pytest tests/integration/test_feature_extract_skill_flow.py -v` — 全部通过
3. 人工验证：
   - `core/prompts/skills/feature-extract-report-format/SKILL.md` 存在且包含 6 个 section 定义
   - `feature_extract_execute.j2` 的输出格式部分要求 `data_profile` 遵循固定结构
   - 回放资产的 `data_profile` 为固定标题结构 Markdown
   - `DraftPES` 的 `draft_plan.j2` / `draft_execute.j2` 无需修改即可消费新格式
