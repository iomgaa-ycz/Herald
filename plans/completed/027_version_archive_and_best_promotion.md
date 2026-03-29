# 027：版本归档与最佳结果提升

## 元信息
- 状态: draft
- 创建: 2026-03-29
- 对应 TD: Task 10（§6.10）

## 1.1 摘要

本任务聚焦把 `DraftPES` 从“成功产出当前 working 工件”推进到“成功产物被版本化归档，并在 `fitness` 更优时提升为 `best/`”。最小闭环是：成功 run 结束后把真实 `working/solution.py` 与 `working/submission.csv` 复制到 `history/{generation}_{solution_id}/`，同步回写 `solution`/DB 的工件路径，并仅在优于历史 best 时更新 `best/`。

基于当前现状，`026` 已完成 `submission.csv` 发现与 schema 校验，`Workspace` 也已具备 `save_version()` / `promote_best()` 基础方法，但主链路尚未真正调用这些能力，也没有“比较历史 best fitness”的最小事实来源与测试覆盖。`main.py` 的 `metadata.json.finished_at` 已经接通，因此 `027` 不重复实现 run 级收尾，只补“归档接线、best 判定、DB 路径一致性、测试面”四件事。

## 1.2 审查点（Review Required）

1. **版本目录命名是否保持现状**
   当前倾向沿用 `Workspace.save_version()` 现有命名：`history/gen{generation}_{solution_id[:8]}/`，而不是改成 TD/测试矩阵文案中的 `history/{generation}_{solution_id}/`。
   原因：仓库实现与目录注释已经稳定使用 `gen0_xxx` 形式，改命名会扩大变更面；测试可按真实实现校验。
2. **best 判定来源**
   当前倾向从数据库读取同一 `run_id` 下已完成 solution 的最高 `fitness`，仅当当前 `fitness` 严格大于历史 best 时才调用 `promote_best()`。
   原因：避免引入额外 `best_fitness.json` 或扫描文件系统；事实来源仍以 DB 为主。
3. **best 更新范围**
   当前倾向只在 `status == "completed"`、`submission_validated == True`、且 `fitness is not None` 时允许提升 `best/``。
   原因：避免无效 submission、失败 run 或无指标 run 污染最佳版本。
4. **工件路径写回语义**
   当前倾向让 `solution.solution_file_path` / `submission_file_path` 在 execute 阶段继续指向 `working/` 真正产物路径；版本目录路径单独写入 `solution.metadata["version_dir"]` 与 `best_metadata.json`，不覆盖现有字段。
   原因：这与 Task 6/9 已建立的 execute 事实语义一致，也更符合“DB 中工件路径与工作空间真实文件一致”的当前测试口径。

## 1.3 拟议变更（Proposed Changes）

### A. 在 DraftPES 成功路径接入版本归档与 best 提升

- [MODIFY] [core/pes/draft.py](/home/yuchengzhang/Code/Herald2/core/pes/draft.py)
  - [MODIFY] `handle_phase_response()`
    - 在 `summarize` phase 标记 `completed` 之前后，保持现有完成语义不变，但确保归档逻辑只发生在完整成功 run 上
  - [NEW] `_archive_successful_solution(solution: PESSolution) -> Path`
    - 读取 `working/solution.py` 与 `working/submission.csv`
    - 调用 `workspace.save_version()`
    - 将版本目录写入 `solution.metadata["version_dir"]`
  - [NEW] `_maybe_promote_best(solution: PESSolution, version_dir: Path) -> bool`
    - 若当前 solution 不满足 `completed + submission_validated + fitness 非空`，直接跳过
    - 查询历史 best fitness
    - 仅当当前 `fitness` 更优时调用 `workspace.promote_best()`
    - 返回是否发生 best 提升
  - [NEW] `_get_current_best_fitness(solution: PESSolution) -> float | None`
    - 从 `db.get_active_solutions()` 或新增 DB 便捷方法中过滤同 `run_id` 且非当前 solution 的记录
    - 返回最高 fitness
  - [NEW] `_build_best_metadata(solution: PESSolution, version_dir: Path) -> dict[str, Any]`
    - 生成最小 best 元数据：`solution_id`、`generation`、`fitness`、`run_id`、`version_dir`、`promoted_at`
  - [MODIFY] `_handle_execute_response()`
    - 保持 execute 工件发现与路径挂接逻辑不变，不在 execute 阶段提前归档，避免半成品进入 `history/`

### B. 给 Workspace 补足最小 best 元信息与目录比较能力

- [MODIFY] [core/workspace.py](/home/yuchengzhang/Code/Herald2/core/workspace.py)
  - [MODIFY] `save_version()`
    - 保持“保存真实代码与 submission”职责
    - 如有必要，补充更明确的中文 docstring，强调返回版本目录
  - [MODIFY] `promote_best()`
    - 继续使用原子替换方式复制 `solution.py` / `submission.csv`
    - 统一把传入 metadata 写为 `best/metadata.json`
  - [NEW] `read_best_metadata() -> dict[str, Any] | None`
    - 读取 `best/metadata.json`
    - 为单测和调试提供稳定入口

### C. 在 DB facade 补最小 best 查询辅助，避免 DraftPES 直接拼 repo 逻辑

- [MODIFY] [core/database/herald_db.py](/home/yuchengzhang/Code/Herald2/core/database/herald_db.py)
  - [NEW] `get_best_fitness(run_id: str | None = None, exclude_solution_id: str | None = None) -> float | None`
    - 返回有效解中的最高 `fitness`
    - 支持按 `run_id` 过滤
    - 支持排除当前 solution，避免自比较
- [MODIFY] [core/database/repositories/solution.py](/home/yuchengzhang/Code/Herald2/core/database/repositories/solution.py)
  - [NEW] `get_best_fitness(run_id: str | None = None, exclude_solution_id: str | None = None) -> float | None`
    - SQL 仅筛选 `status IN ('completed', 'success') AND fitness IS NOT NULL`
    - 可选增加 `run_id = ?`
    - 可选排除指定 solution

### D. 补齐 Task 10 的单元与集成测试

- [NEW] [tests/unit/test_workspace.py](/home/yuchengzhang/Code/Herald2/tests/unit/test_workspace.py)
  - [NEW] `test_save_version_creates_directory()`
    - 断言版本目录创建成功，且包含真实 `solution.py` / `submission.csv`
  - [NEW] `test_promote_best_updates_best_dir()`
    - 断言 `best/solution.py`、`best/submission.csv`、`best/metadata.json` 同步更新
  - [NEW] `test_read_best_metadata_returns_none_when_absent()`
  - [NEW] `test_read_best_metadata_roundtrip()`
- [MODIFY] [tests/unit/test_database_roundtrip.py](/home/yuchengzhang/Code/Herald2/tests/unit/test_database_roundtrip.py)
  - [NEW] `test_solution_artifact_paths_roundtrip_with_real_sqlite()`
    - 断言 `update_solution_artifacts()` 后路径可完整读回
  - [NEW] `test_get_best_fitness_filters_by_run_id_and_excludes_current_solution()`
    - 构造双 solution 场景，验证 best 查询语义
- [MODIFY] [tests/integration/test_draft_pes_runtime_flow.py](/home/yuchengzhang/Code/Herald2/tests/integration/test_draft_pes_runtime_flow.py)
  - [NEW] `test_draft_pes_runtime_success_saves_version_and_promotes_best()`
    - success 回放后断言 `history/` 下生成版本目录，`best/` 被设置，`best/metadata.json` 含当前 fitness
  - [NEW] `test_draft_pes_runtime_lower_fitness_does_not_override_best()`
    - 同一 workspace 连续两次运行：第一次高分、第二次低分，断言 `best/` 保持第一次内容
  - [MODIFY] 现有 success case
    - 追加 DB 中 `solution_file_path` / `submission_file_path` 仍指向 working 工件，且文件真实存在

## 1.4 验证计划（Verification Plan）

1. 运行 `pytest tests/unit/test_workspace.py`
2. 运行 `pytest tests/unit/test_database_roundtrip.py`
3. 运行 `pytest tests/integration/test_draft_pes_runtime_flow.py`
4. 回归运行
   - `pytest tests/unit/test_draft_pes.py`
   - `pytest tests/unit/test_submission_validator.py`
   - `pytest tests/integration/test_draft_pes_tool_write_flow.py`
5. 人工验证点
   - success 回放后 `history/gen{generation}_{solution_id[:8]}/` 存在，内容与 `working/` 中真实工件一致
   - 更高 `fitness` 会更新 `best/solution.py`、`best/submission.csv`、`best/metadata.json`
   - 更低 `fitness` 不会覆盖已有 `best/`
   - `solution_file_path` / `submission_file_path` 继续指向 execute 阶段真实工件，不被版本目录路径污染
   - `main.py` 结束后 `metadata.json.finished_at` 仍然存在，不因本任务回归

## 约束与备注

- 本任务不实现 `test_score` 评分与 `MLEBenchGradingHook`；那是 Task 11
- 本任务不引入新的归档数据库表，优先复用现有 `solutions` 与 `Workspace.best/metadata.json`
- 本任务不把版本目录路径塞进现有 `solution_file_path` / `submission_file_path` 字段，避免破坏 Task 6/9 已有语义
- 若实现中发现“best 应跨 run 共享”比“同 run 内比较”更符合后续演化设计，需要先回到本计划的审查点再调整
