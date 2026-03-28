# 021: 注入 run_id 与 run 级元数据

## 元信息
- 状态: draft
- 创建: 2026-03-28
- 对应 TD: Task 5（§6.5）

## 1.1 摘要

本任务默认 **Task 4 已完成**：`main.py` 已能装配 `FeatureExtractPES + DraftPES`、`Scheduler.task_stages` 已跑通、`DraftPES` 已消费 `data_profile`。因此 `021` 不再重复扩展主链路，只收敛 run 级 Harness 能力本身。

当前仓库里已经在 `core/main.py` 有一版可用的 `run_id/metadata.json` 原型实现，本任务将基于这部分现状做轻量收敛：确保 `run_id` 成为稳定的运行时基础字段，并把 `metadata.json` 的生命周期职责归位到 `Workspace`，使其与 `docs/TD.md`、`docs/evolve.md` 的 run 记录契约一致。

## 1.2 审查点（Review Required）

1. **run 元数据职责归属**: 当前倾向把 `metadata.json` 的读写/回写下沉到 `Workspace`，`main.py` 只负责组装字段并驱动生命周期，避免 run 工件写入逻辑继续散落在 CLI 层
2. **bootstrap 接口是否保持稳定**: 当前倾向不再改动 `bootstrap_feature_extract_pes()` / `bootstrap_draft_pes()` 的职责边界，沿用 Task 4 已完成的装配流程，只在 `main()` 中统一注入共享 `run_id`
3. **Task 5 与 Task 4 的边界**: 当前倾向保持 Task 5 只处理 `run_id + metadata.json`，不继续扩展 `TaskCompleteEvent.output_context`、`data_profile`、Prompt 模板、`task_stages` 等 Task 4 主题，避免任务重叠

## 1.3 拟议变更（Proposed Changes）

### A. 将 run 元数据落盘职责收敛到 Workspace

- [MODIFY] `core/workspace.py`
  - [NEW] `metadata_path` 路径访问入口
    - 统一指向工作空间根目录 `metadata.json`
  - [NEW] `write_run_metadata(metadata: dict[str, Any]) -> Path`
    - 负责原子/单点写入 run 级元数据文件
  - [NEW] `update_run_finished_at(finished_at: str) -> None`
    - 负责在 run 结束时回写 `finished_at`
  - [NEW] `read_run_metadata() -> dict[str, Any] | None`
    - 仅用于测试与后续审阅场景，避免在 `main.py` 中重复解析 JSON

### B. 基于 Task 4 已有主链路补齐 run_id 注入契约

- [MODIFY] `core/main.py`
  - [NEW] `build_run_metadata(config, workspace, run_id, started_at) -> dict[str, Any]`
    - 只负责构造符合 TD/evolve 要求的 run 元数据快照
  - [DELETE] `write_run_metadata(workspace, metadata) -> Path`
    - 迁移到 `Workspace.write_run_metadata()`
  - [DELETE] `update_run_metadata_finished_at(workspace, finished_at) -> None`
    - 迁移到 `Workspace.update_run_finished_at()`
  - [MODIFY] `main()`
    - 保留 Task 4 已完成的 bootstrap 与 `task_stages` 主流程
    - 在 bootstrap 后统一生成/持有唯一 `run_id`
    - 将同一个 `run_id` 注入 `feature_extract_pes.runtime_context`、`draft_pes.runtime_context`、`Scheduler.context`
    - 调用 `Workspace.write_run_metadata(...)` 写入 `metadata.json`
    - 在 `finally` 中调用 `Workspace.update_run_finished_at(...)`

### C. 用单元测试锁定 run 级 Harness 契约

- [MODIFY] `tests/unit/test_main_bootstrap.py`
  - [MODIFY] `test_run_metadata_file_can_be_written_and_updated()`
    - 改为通过 `Workspace` 的 run metadata 接口断言 `metadata.json` 写入与 `finished_at` 回写
  - [NEW] `test_main_injects_shared_run_id_into_runtime_context()`
    - 以 monkeypatch/stub 方式调用 `main()`
    - 断言两个 PES 的 `runtime_context["run_id"]` 与 `Scheduler.context["run_id"]` 一致
  - [NEW] `test_build_run_metadata_contains_required_fields()`
    - 断言最小字段集至少包含：
      - `run_id`
      - `competition_id`
      - `competition_root_dir`
      - `public_data_dir`
      - `workspace_dir`
      - `config_snapshot`
      - `started_at`
      - `finished_at`

## 1.4 验证计划（Verification Plan）

1. 运行 `pytest tests/unit/test_main_bootstrap.py`
2. 人工验证点
   - `FeatureExtractPES.runtime_context["run_id"]`、`DraftPES.runtime_context["run_id"]`、`Scheduler.context["run_id"]` 三者一致
   - 工作空间根目录存在 `metadata.json`
   - `metadata.json` 至少包含 `run_id`、`competition_root_dir`、`workspace_dir`、`config_snapshot`、`started_at`
   - run 结束后 `metadata.json` 中 `finished_at` 已被回写

## 约束与备注

- 本任务默认 `Task 4` 已完成，因此不再调整 `feature_extract -> draft` 主链路
- 保持 MVP 原则，不引入 run 表、额外 DB schema 或独立 RunRepository
- 若实现过程中发现现有 Task 4 代码已经覆盖部分 Task 5 能力，优先做轻量重构与职责归位，不重复造第二套 metadata 方案
