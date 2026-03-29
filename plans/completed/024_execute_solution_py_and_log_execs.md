# 024：执行 `solution.py` 并记录 `exec_logs`

## 元信息
- 状态: draft
- 创建: 2026-03-29
- 对应 TD: Task 7（§6.7）

## 1.1 摘要

本任务聚焦把 `DraftPES.execute` 从“代码已落盘”推进到“首次真实运行事实可查询”。最小闭环是：Agent 在 `execute` phase 里对最终 `working/solution.py` 完成真实运行后，系统把该次运行的 `command/stdout/stderr/exit_code/duration_ms` 落库到 `exec_logs`，并在运行失败时把 solution 明确置为 `failed`。

基于当前现状，`Task 6` 已经完成 `solution.py` 的真实落盘、语法校验与 `code_snapshots` 持久化，因此 `024` 不再重复处理代码来源问题，也不默认引入 Harness 二次复跑；它只补“首次运行事实采集、执行日志落库和失败可观测”三件事。

## 1.2 审查点（Review Required）

1. **执行事实来源**：当前倾向优先消费 Agent 在 `execute` phase 中对最终 `solution.py` 的首次真实运行记录，而不是 phase 结束后由 Harness 再完整重跑同一脚本
2. **可信边界**：当前倾向把 `solution.py`、`submission.csv`、stdout/stderr、脚本打印出的 `fitness` 视为可信事实；不把模型自然语言里的“我成功了 / 我更好了”视为通过依据
3. **失败语义**：当前倾向把首次真实运行中的非零退出码直接视为 execute 失败；仍记录完整 `exec_logs`，随后由 `BasePES.handle_phase_failure()` 统一落状态并阻断 summarize

## 1.3 拟议变更（Proposed Changes）

### A. 在 DraftPES 中接入首次运行事实采集链路

- [MODIFY] `core/pes/draft.py`
  - [MODIFY] `_handle_execute_response()`
    - 在现有 tool-write 契约与语法校验成功后，追加首次运行事实提取与持久化
    - 成功时把执行摘要写入 `solution.execute_summary`
    - 失败时抛出带执行上下文的 `ValueError`，交给 `BasePES` 统一处理
  - [NEW] `_extract_execute_fact(response: object) -> dict[str, Any]`
    - 优先从 `response.turns` 中的真实工具调用提取首次运行的命令与结果
    - 至少恢复 `command/stdout/stderr/exit_code/duration_ms`
  - [NEW] `_assert_execute_fact_matches_final_solution(solution: PESSolution, exec_fact: dict[str, Any]) -> None`
    - 确认记录到的执行事实对应的是最终 `working/solution.py`
  - [NEW] `_persist_exec_log(solution: PESSolution, exec_result: dict[str, Any]) -> None`
    - 调用 `HeraldDB.log_exec()` 写入 `exec_logs`
  - [NEW] `_format_execute_summary(exec_result: dict[str, Any]) -> str`
    - 生成简洁的人类可读执行摘要，供 summarize 和失败回放复用

### B. 给 Workspace 暴露最小运行时事实辅助能力

- [MODIFY] `core/workspace.py`
  - [NEW] `get_working_submission_path(file_name: str = "submission.csv") -> Path`
    - 统一提供提交文件标准路径，避免 `DraftPES` 内部拼接路径分散
  - [NEW] `read_runtime_artifact(file_name: str) -> str | None`
    - 读取 execute 阶段生成的 `stdout.log` / `stderr.log` / 指标 JSON 等辅助工件，作为事实补充来源

### C. 扩展 DB roundtrip 与执行日志查询

- [MODIFY] `core/database/herald_db.py`
  - [NEW] `get_exec_logs(solution_id: str) -> list[dict[str, Any]]`
    - 透传 `TracingRepository.get_exec_logs()`，供单测和集成测试断言

### D. 补齐 Task 7 的最小测试面

- [NEW] `tests/unit/test_execute_fact_capture.py`
  - [NEW] `test_extract_execute_fact_from_real_tool_trace()`
    - 使用真实回放 `turns.json`，断言可恢复 `command/stdout/stderr/exit_code/duration_ms`
  - [NEW] `test_execute_fact_non_zero_exit_code_marks_failure_after_logging()`
    - 用 runtime-error 回放，断言失败前已写入 `exec_logs`
- [MODIFY] `tests/unit/test_database_roundtrip.py`
  - [NEW] `test_exec_log_roundtrip_with_real_sqlite()`
    - 验证 `log_exec()` / `get_exec_logs()` 的 sqlite roundtrip
- [NEW] `tests/integration/test_draft_pes_execute_fact_flow.py`
  - [NEW] success case：`DraftPES.run()` 后存在至少一条 `exec_logs`，且 `exit_code=0`
  - [NEW] failure case：runtime error 时 solution 状态为 `failed`，`stderr` 可查询，调度器不挂起
- [NEW] `tests/cases/replays/draft_runtime_error_v1/solution.py`
  - 构造会抛出运行时异常的最小脚本

## 1.4 验证计划（Verification Plan）

1. 运行 `pytest tests/unit/test_execute_fact_capture.py`
2. 运行 `pytest tests/unit/test_database_roundtrip.py`
3. 运行 `pytest tests/integration/test_draft_pes_execute_fact_flow.py`
4. 人工验证点
   - success case 至少写入一条 `exec_logs`
   - `stdout`、`stderr`、`exit_code`、`duration_ms` 均可从 DB 查询
   - runtime-error case 不会静默吞错，`solution.status` 明确为 `failed`
   - `working/solution.py` 仍是唯一代码真相来源，本任务不回退到解析模型文本恢复代码
   - 不要求 Harness 再对同一高成本脚本做默认二次完整重跑

## 约束与备注

- 本任务不提取 `val_metric_value`，不回写 `fitness`，这些属于 Task 8
- 本任务不补采 `test_score`，这些属于后续评分链路任务
- 坚持 MVP：不引入通用 Runner 框架，只在 `DraftPES` 内实现最小可验证事实采集链路
