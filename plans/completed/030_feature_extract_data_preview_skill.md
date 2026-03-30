# 030：实现 FeatureExtract 数据预览 skill

## 元信息
- 状态: completed
- 创建: 2026-03-29
- 对应 TD: Task 14（§6.14）

## 1.1 摘要

本任务聚焦给 `FeatureExtractPES` 补一个真正可复用的 project skill：把当前 execute 阶段里临时性的 Bash / Python 数据窥探动作，收敛为一组可直接运行的小脚本，并通过 `SKILL.md` 明确何时调用、先调用哪个脚本、最少要收集哪些事实。目标不是在这一步直接产出正式版 `data_profile.md`，而是先把“稳定取数、稳定预览、稳定暴露 submission 约束”这层打实，为 Task 15 的格式化 skill 提供输入。

当前仓库已经完成了 Task 13 / 16 的 skill 发现与 working 可见性接线，因此 `030` 的重点不再是 SDK 配置，也不再额外修改 Prompt，而是 skill 本体、脚本拆分和最小测试闭环，直接依赖 Claude Agent SDK 的 project skill 发现与调用机制。

## 1.2 审查点（Review Required）

1. Skill 输出边界
   当前倾向让数据预览 skill 只输出“原始但结构化”的预览事实，不在本任务内承担 `data_profile.md` 的固定格式编排。
   原因：`docs/TD.md` 已把格式化职责明确留给 Task 15；若在 Task 14 一并做完，会扩大行为面。
2. 脚本组织方式
   当前倾向采用“一个共享库 + 多个可直接执行的薄 CLI 脚本”。
   具体拆分如下：
   - 共享库：`preview_support.py`
     - 负责文件发现、CSV 统计、description 摘要、submission 约束解析、统一渲染
   - 薄 CLI：`preview_competition.py`
     - 一次输出完整预览，供 Agent 首选调用
   - 薄 CLI：`preview_description.py`
     - 只看 `description.md` / 描述文件
   - 薄 CLI：`preview_table.py`
     - 只看 `train.csv` / `test.csv` 一类表格文件
   - 薄 CLI：`preview_submission.py`
     - 只看 `sample_submission.csv` 与目标列/行数约束
   原因：既满足“拆成多个小函数脚本”，又避免在每个脚本里重复实现 CSV / description / submission 解析逻辑。
3. Prompt 介入策略
   当前结论是不修改 Prompt，直接依赖 Claude Agent SDK 的 skill 管理与发现机制。
   原因：本任务只补 skill 本体，不扩大 `FeatureExtractPES` 的 phase 指令面。

## 1.3 拟议变更（Proposed Changes）

### A. 新增任务030计划文件

- [NEW] [plans/active/030_feature_extract_data_preview_skill.md](/home/yuchengzhang/Code/Herald2/plans/active/030_feature_extract_data_preview_skill.md)
  - 固化 Task 14 的范围、审查点、实现边界与验证计划

### B. 新增 FeatureExtract 数据预览 project skill

- [NEW] `core/prompts/skills/feature-extract-data-preview/SKILL.md`
  - 说明 skill 触发条件、推荐调用顺序、最小输出字段与退化策略
- [NEW] `core/prompts/skills/feature-extract-data-preview/scripts/preview_support.py`
  - [NEW] `find_common_competition_files(data_dir: Path) -> dict[str, str]`
  - [NEW] `summarize_table_file(csv_path: Path, sample_rows: int = 5, profile_rows: int = 2000) -> dict[str, Any]`
  - [NEW] `summarize_description_file(file_path: Path, max_lines: int = 40) -> dict[str, Any]`
  - [NEW] `summarize_submission_constraints(sample_submission_path: Path, test_path: Path | None = None) -> dict[str, Any]`
  - [NEW] `render_preview_report(data_dir: Path) -> str`
- [NEW] `core/prompts/skills/feature-extract-data-preview/scripts/preview_competition.py`
  - 汇总输出文件清单、description 摘要、train/test 预览与 submission 约束
- [NEW] `core/prompts/skills/feature-extract-data-preview/scripts/preview_description.py`
  - 聚焦预览 `description.md`
- [NEW] `core/prompts/skills/feature-extract-data-preview/scripts/preview_table.py`
  - 聚焦预览 `train.csv` / `test.csv`
- [NEW] `core/prompts/skills/feature-extract-data-preview/scripts/preview_submission.py`
  - 聚焦解析 `sample_submission.csv` 及目标列 / 行数约束
### C. 补齐 Task 14 最小测试

- [MODIFY] [tests/unit/test_feature_extract_pes.py](/home/yuchengzhang/Code/Herald2/tests/unit/test_feature_extract_pes.py)
  - [NEW] `test_feature_extract_skill_contract_keeps_execute_phase_skill_enabled()`
- [MODIFY] [tests/integration/test_feature_extract_skill_flow.py](/home/yuchengzhang/Code/Herald2/tests/integration/test_feature_extract_skill_flow.py)
  - [NEW] `test_feature_extract_preview_skill_scripts_run_on_competition_dir()`
  - [NEW] `test_feature_extract_preview_skill_output_covers_minimum_fields()`

### D. 文档同步

- [MODIFY] [docs/TD.md](/home/yuchengzhang/Code/Herald2/docs/TD.md)
  - 将 Task 14 状态同步为已实现
- [MODIFY] [docs/test_matrix.md](/home/yuchengzhang/Code/Herald2/docs/test_matrix.md)
  - 将 `test_feature_extract_skill_flow.py` 的覆盖说明补充为包含预览脚本执行

## 1.4 验证计划（Verification Plan）

1. 运行 `pytest tests/unit/test_feature_extract_pes.py`
2. 运行 `pytest tests/integration/test_feature_extract_skill_flow.py`
3. 人工验证点
   - `core/prompts/skills/feature-extract-data-preview/` 在仓库内存在且结构完整
   - `expose_project_skills()` 能将 `core/prompts/skills` 直接暴露到 `working/.claude/skills`
   - `preview_competition.py` 能在最小竞赛目录上输出文件清单、样本规模、列统计、缺失值、目标列与 submission 约束
   - 不修改 Prompt 的前提下，现有 `FeatureExtractPES.execute` 仍保持 `"Skill"` 工具可用
