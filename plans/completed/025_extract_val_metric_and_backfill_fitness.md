# 025：提取 `val_metric_value` 并回写 `fitness`

## 元信息
- 状态: draft
- 创建: 2026-03-29
- 对应 TD: Task 8（§6.8）

## 1.1 摘要

本任务聚焦把 `DraftPES.execute` 从“已有真实运行日志”推进到“已有可用于调度的主分数”。最小闭环是：从 execute 阶段的真实运行事实中提取 `val_metric_name`、`val_metric_value`、`val_metric_direction`，写回 `solution.metrics` 与 `solution.fitness`，并同步落库到 `solutions`。

基于当前现状，Task 7 已完成 `solution.py` 真正落盘、首次运行事实采集和 `exec_logs` 持久化，因此 `025` 不重复处理代码来源或二次重跑；它只补“指标事实提取、fitness 回写、缺失指标时失败闭环”三件事。

## 1.2 审查点（Review Required）

1. **指标键空间**：当前倾向以 `val_metric_name` / `val_metric_value` / `val_metric_direction` 作为 `solution.metrics` 的规范键；为兼容现有 DB 列 `metric_*` 与 summarize 模板，在序列化/Prompt 层做映射或别名，不做本任务内的 schema 迁移
2. **提取优先级**：当前倾向按 `working/metrics.json` > `exec_result.metrics`（结构化 JSON） > `stdout` 中的 JSON 行 > `stdout` 中显式键值文本 的顺序提取；明确不读取模型自然语言总结来认定分数
3. **成功语义收紧**：当前倾向把“`exit_code == 0` 但缺失 `val_metric_value`”视为 execute 失败，避免把没有主分数的 run 误判为成功闭环

## 1.3 拟议变更（Proposed Changes）

### A. 在 DraftPES 中接入 `val_metric_*` 提取与回写

- [MODIFY] [core/pes/draft.py](/home/yuchengzhang/Code/Herald2/core/pes/draft.py)
  - [MODIFY] `_handle_execute_response()`
    - 在 `exec_logs` 落库后、成功返回前，追加指标提取与 `fitness` 回写
    - `exit_code != 0` 时维持现有失败逻辑
    - `exit_code == 0` 但提取不到 `val_metric_value` 时抛出明确错误，交给 `BasePES.handle_phase_failure()` 统一落失败状态
  - [NEW] `_extract_val_metrics(solution: PESSolution, exec_result: dict[str, Any]) -> dict[str, Any]`
    - 汇总 `working/metrics.json`、结构化 `metrics`、`stdout`、运行时工件中的指标事实
    - 产出规范化后的 `val_metric_*` 字段
  - [NEW] `_load_metrics_artifact() -> dict[str, Any] | None`
    - 优先读取 execute 阶段落在 `working/metrics.json` 的结构化指标文件
    - 作为当前阶段最主要的分数事实来源
  - [NEW] `_extract_val_metrics_from_structured_payload(payload: dict[str, Any]) -> dict[str, Any] | None`
    - 支持两类输入键：
      - 新规范键：`val_metric_name` / `val_metric_value` / `val_metric_direction`
      - 兼容键：`metric_name` / `metric_value` / `metric_direction`
  - [NEW] `_extract_val_metrics_from_stdout(stdout: str) -> dict[str, Any] | None`
    - 先尝试解析单行 JSON
    - 再兼容 `val_metric_value=0.8123`、`metric_value: 0.8123` 这类最小文本协议
  - [NEW] `_apply_val_metrics(solution: PESSolution, metrics: dict[str, Any]) -> None`
    - 将规范化指标写入 `solution.metrics`
    - 以 `val_metric_value` 回写 `solution.fitness`
    - 同步保留 prompt/旧持久化链路所需的别名字段，避免本任务扩散改动到模板层

### B. 收敛 `PESSolution` 的指标语义与序列化映射

- [MODIFY] [core/pes/types.py](/home/yuchengzhang/Code/Herald2/core/pes/types.py)
  - [MODIFY] `PESSolution.to_record()`
    - 优先从 `solution.metrics["val_metric_*"]` 读取规范指标
    - 映射写入当前 DB 的 `metric_name` / `metric_value` / `metric_direction` 列
    - 保留对旧键的 fallback，避免测试桩一次性全部失效
  - [MODIFY] `PESSolution.to_prompt_payload()`
    - 输出给模板的 `metrics` 同时包含：
      - 规范键：`val_metric_name` / `val_metric_value` / `val_metric_direction`
      - 兼容键：`metric_name` / `metric_value` / `metric_direction`
    - 这样本任务无需同步修改现有 `draft_summarize.j2`

### C. 补齐状态持久化时的指标映射

- [MODIFY] [core/pes/base.py](/home/yuchengzhang/Code/Herald2/core/pes/base.py)
  - [MODIFY] `_persist_solution_status()`
    - 优先读取 `solution.metrics["val_metric_*"]`
    - 再映射到 `HeraldDB.update_solution_status()` 现有的 `metric_*` 参数
    - 避免仅靠 `to_record()` 覆盖 insert，而 update 链路仍读旧键导致落库为空

### D. 用真实回放资产补齐 Task 8 的最小测试面

- [NEW] [tests/unit/test_metric_extraction.py](/home/yuchengzhang/Code/Herald2/tests/unit/test_metric_extraction.py)
  - [NEW] `test_extract_val_metrics_from_structured_payload_prefers_canonical_keys()`
  - [NEW] `test_extract_val_metrics_from_stdout_json_line()`
  - [NEW] `test_extract_val_metrics_from_stdout_key_value_text()`
  - [NEW] `test_missing_val_metric_value_raises_for_successful_execute()`
- [NEW] [tests/unit/test_solution_model.py](/home/yuchengzhang/Code/Herald2/tests/unit/test_solution_model.py)
  - [NEW] `test_solution_to_record_maps_val_metric_fields_to_legacy_db_columns()`
  - [NEW] `test_solution_to_prompt_payload_exposes_metric_aliases()`
- [NEW] [tests/integration/test_draft_pes_runtime_flow.py](/home/yuchengzhang/Code/Herald2/tests/integration/test_draft_pes_runtime_flow.py)
  - [NEW] success case：`DraftPES.run()` 完成后，`solution.metrics` 和 DB `solutions` 中都有 `val_metric_value` 对应事实，且 `fitness == val_metric_value`
  - [NEW] metric-missing case：即使 `exit_code == 0`，若缺失 `val_metric_value`，solution 也会被标记为 `failed`
- [NEW] `tests/cases/replays/draft_metric_missing_v1/`
  - [NEW] `turns.json`
  - [NEW] `solution.py`
  - [NEW] `stdout.log`
- [MODIFY] `tests/cases/replays/draft_success_tabular_v1/`
  - [NEW] `metrics.json`
  - 必要时保留 `stdout.log` 作为兜底回放，但 success 主路径以 `metrics.json` 供给 `val_metric_value`

## 1.4 验证计划（Verification Plan）

1. 运行 `pytest tests/unit/test_metric_extraction.py`
2. 运行 `pytest tests/unit/test_solution_model.py`
3. 运行 `pytest tests/integration/test_draft_pes_runtime_flow.py`
4. 回归运行
   - `pytest tests/unit/test_execute_fact_capture.py`
   - `pytest tests/integration/test_draft_pes_execute_fact_flow.py`
5. 人工验证点
   - success case 的 `solution.metrics` 中必须有 `val_metric_name`、`val_metric_value`、`val_metric_direction`
   - `solution.fitness` 必须等于 `val_metric_value`
   - `solutions.metric_value` 实际承载的是 `val_metric_value`
   - `test_score` 未接入前，不存在任何逻辑覆盖 `fitness`
   - 缺失 `val_metric_value` 的 run 不会被误判为 `completed`

## 约束与备注

- 本任务不接入 `test_score`，也不改评分 hook
- 本任务不做数据库 schema 迁移；继续复用 `solutions.metric_*` 三列承载本地验证分数语义
- 本任务不修改 `DraftPES` 之外的执行模型；不引入通用 Runner 或新的评测框架
