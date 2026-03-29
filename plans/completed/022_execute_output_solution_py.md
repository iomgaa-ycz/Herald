# 022: Tool-Write 契约化落盘真实 solution.py

## 元信息
- 状态: draft
- 创建: 2026-03-28
- 对应 TD: Task 6（§6.6）

## 1.1 摘要

本任务聚焦 `DraftPES.execute` 的最小闭环补齐：把当前“仅保留 LLM 原始文本 + touch 空 `solution.py`”推进到“以 Agent tools 成功写出真实 `working/solution.py` 作为 execute 成功的唯一契约，并同步写入 `code_snapshots`”。

基于当前代码现状，`HeraldDB.insert_code_snapshot()`、`Workspace.working_dir`、`solution.solution_file_path` 等骨架已存在，因此 `022` 不再扩展 Task 7 的本地执行，只收敛 tool-write 契约、失败可观测性与代码工件持久化三件事；最终文本输出不再承担代码来源职责。

## 1.2 审查点（Review Required）

1. **代码真相来源**: 当前倾向明确规定 `working/solution.py` 是 execute 阶段唯一代码真相来源；`response.result` 与自然语言总结只用于审阅，不允许再承担代码恢复或兜底职责
2. **tool-write 失败判定**: 当前倾向将以下任一情况都判定为 execute 失败：文件不存在、文件为空、文件无法读取、语法校验失败；不再引入输出解析兜底
3. **失败事件发射位置**: 当前倾向把 `TaskCompleteEvent(status="failed")` 的发射下沉到 `BasePES.handle_phase_failure()` 或受其调用的公共辅助方法，避免 execute 的 tool-write 失败导致调度器等待不到完成事件

## 1.3 拟议变更（Proposed Changes）

### A. 在 DraftPES 中实现 tool-write 契约主链路

- [MODIFY] `core/pes/draft.py`
  - [MODIFY] `handle_phase_response()`
    - 在 `execute` 分支不再直接把原始文本塞给 `solution.execute_summary`
    - 改为调用“检查 `working/solution.py` 是否已被 tools 写出 → 读取文件 → 语法校验 → 写入 `code_snapshots` → 挂载工件路径”的完整链路
  - [NEW] `_handle_execute_response(solution: PESSolution, response_text: str) -> dict[str, Any]`
    - 统一编排 execute 阶段的契约校验与持久化
  - [NEW] `_load_written_solution_code() -> str`
    - 读取 `workspace.working_dir/solution.py`
    - 文件不存在、为空或不可读时抛出 `ValueError`
  - [NEW] `_validate_python_code(code: str) -> None`
    - 用 `compile(code, "<solution.py>", "exec")` 做最小语法校验
    - 语法不合法时抛出带行号/错误摘要的 `ValueError`
  - [NEW] `_persist_code_snapshot(solution: PESSolution, code: str) -> None`
    - 调用 `HeraldDB.insert_code_snapshot()` 保存完整代码快照
  - [MODIFY] `_attach_workspace_artifacts()`
    - 保留路径挂载职责，但不再 `touch` 空 `solution.py`
    - `submission.csv` 仍可维持占位路径，不提前写入真实内容
  - [NEW] `_assert_tool_write_contract() -> Path`
    - 统一校验 `solution.py` 是否由 tools 成功写出
    - 将失败原因写入异常消息，供 `handle_phase_failure()` 记录

### B. 补齐失败可观测性，避免调度器卡死

- [MODIFY] `core/pes/base.py`
  - [NEW] `_emit_task_complete_event(solution: PESSolution, status: str, output_context: dict[str, Any] | None = None) -> None`
    - 统一封装 `TaskCompleteEvent` 发射逻辑，供成功/失败路径复用
  - [MODIFY] `handle_phase_failure()`
    - 在保留现有 `solution.status = "failed"` 与持久化逻辑基础上，记录可读失败原因到 `solution.execute_summary` 或 `solution.metadata["failure_reason"]`
    - 对由事件驱动触发的 PES 运行，在失败时补发 `TaskCompleteEvent(status="failed")`
- [MODIFY] `core/pes/feature_extract.py`
  - [MODIFY] `_handle_summarize_response()`
    - 复用 `BasePES` 的公共事件发射方法，收敛成功路径写法

### C. 把 working/solution.py 的读取与校验职责收敛到 Workspace

- [MODIFY] `core/workspace.py`
  - [NEW] `get_working_file_path(file_name: str) -> Path`
    - 统一返回 `working/` 目录下的工件路径
  - [NEW] `read_working_solution(file_name: str = "solution.py") -> str`
    - 作为 `solution.py` 的专用读取入口
    - 文件不存在或为空时抛出可读异常
  - [NEW] `read_working_text(file_name: str) -> str | None`
    - 仅用于测试和审阅，便于断言落盘内容与快照一致

### D. 为代码快照 roundtrip 暴露最小查询入口

- [MODIFY] `core/database/herald_db.py`
  - [NEW] `get_latest_code_snapshot(solution_id: str) -> dict | None`
    - 直接透传 `SnapshotRepository.get_latest()`
    - 便于 `tests/unit/test_database_roundtrip.py` 断言 `full_code` 与文件落盘内容一致

### E. 基于真实 tool trace 与工作空间快照补齐 Task 6 测试面

- [NEW] `tests/unit/test_tool_write_contract.py`
  - [NEW] `test_execute_reads_non_empty_solution_file_from_workspace()`
    - 断言 `working/solution.py` 被作为唯一代码来源读取
  - [NEW] `test_handle_execute_response_persists_code_snapshot_from_written_file()`
    - 断言 `code_snapshots` 与 `working/solution.py` 完全一致
  - [NEW] `test_handle_execute_response_fails_when_solution_file_missing()`
    - `draft_missing_solution_file_v1` 明确失败，并留下可读原因
  - [NEW] `test_handle_execute_response_fails_when_solution_file_empty()`
    - `draft_empty_solution_file_v1` 明确失败，并留下可读原因
  - [NEW] `test_handle_execute_response_fails_on_syntax_error()`
    - `draft_syntax_error_v1` 在契约校验阶段即失败短路
- [NEW] `tests/unit/test_database_roundtrip.py`
  - [NEW] `test_code_snapshot_roundtrip_with_real_sqlite()`
    - 用真实 sqlite 验证 `insert_code_snapshot()` / `get_latest_code_snapshot()` roundtrip
- [NEW] `tests/integration/test_draft_pes_tool_write_flow.py`
  - [NEW] success 回放：`DraftPES.run()` 后存在非空 `working/solution.py`，且 `code_snapshots` 与文件内容一致
  - [NEW] failure 回放：文件缺失、文件为空或语法错误时，solution 状态为 `failed`，调度侧不会无限等待
- [NEW] `tests/cases/replays/draft_success_tabular_v1/turns.json`
- [NEW] `tests/cases/replays/draft_missing_solution_file_v1/turns.json`
- [NEW] `tests/cases/replays/draft_empty_solution_file_v1/turns.json`
- [NEW] `tests/cases/replays/draft_syntax_error_v1/solution.py`

## 1.4 验证计划（Verification Plan）

1. 运行 `pytest tests/unit/test_tool_write_contract.py`
2. 运行 `pytest tests/unit/test_database_roundtrip.py`
3. 运行 `pytest tests/integration/test_draft_pes_tool_write_flow.py`
4. 人工验证点
   - `working/solution.py` 由 Agent tools 真实写出，且为非空 Python 代码
   - `code_snapshots.full_code` 与 `working/solution.py` 内容完全一致
   - `draft_missing_solution_file_v1` / `draft_empty_solution_file_v1` / `draft_syntax_error_v1` 都会把 `solution.status` 置为 `failed`
   - 失败 case 有可读错误原因，且调度器能收到 `TaskCompleteEvent(status="failed")`

## 约束与备注

- 本任务不执行 `solution.py`，不记录 `exec_logs`，这些属于 Task 7
- 本任务不提取 `val_metric_value`、不生成真实 `submission.csv`，这些分别属于 Task 8 与后续任务
- 保持 MVP 原则：只做 tool-write 契约、代码快照入库、失败可观测，不引入额外执行器抽象层
