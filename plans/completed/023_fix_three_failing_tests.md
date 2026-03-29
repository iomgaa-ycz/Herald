# 023: 修复三个因接口/行为变化而失败的测试

## 元信息
- 状态: draft
- 创建: 2026-03-28
- 关联计划: 022（Tool-Write 契约）

## 1.1 摘要

修复 3 个因计划 022 引入的接口/行为变化而失败的测试：`test_dispatch_to_pes` 需改用真实 PES 配置；`test_handle_summarize_emits_complete` 与 `test_handle_summarize_emits_output_context` 需在测试中设置 `received_execute_event` 以触发事件发射。

## 1.2 审查点（Review Required）

1. **MockPES 替换策略**: 当前倾向删除 `MockPES`，改用 `FeatureExtractPES` + 真实配置，避免维护测试专用 PES
2. **事件触发方式**: 当前倾向在单元测试中直接设置 `pes.received_execute_event = TaskExecuteEvent(...)` 而非改用 Scheduler 驱动，保持测试对 `handle_phase_response` 行为的聚焦

## 1.3 拟议变更（Proposed Changes）

### A. 修复 `test_dispatch_to_pes`

**问题**: `MockPES` 使用 `operation="default"` + `default_plan/execute/summarize` 模板，但这些模板在 `prompt_spec.yaml` 中不存在。

**修复方案**: 删除 `MockPES`，改用 `FeatureExtractPES` + 真实配置。

- [MODIFY] `tests/integration/test_dispatch_flow.py`
  - [DELETE] `DummyLLM` 类（移至测试顶部或复用其他文件）
  - [DELETE] `MockPES` 类
  - [DELETE] `_build_config()` 函数
  - [MODIFY] `test_dispatch_to_pes()`
    - 导入 `FeatureExtractPES`, `load_pes_config`, `load_prompt_manager`
    - 构造最小 `Workspace` 和 `HeraldDB`
    - 使用 `config/pes/feature_extract.yaml` 真实配置
    - 使用 `DummyLLM` 作为测试桩
    - 验证 `FeatureExtractPES` 能被调度器正确触发

### B. 修复 `test_handle_summarize_emits_complete`

**问题**: `_emit_task_complete_event()` 新增守卫条件 `if self.received_execute_event is None: return`，测试直接调用 `handle_phase_response()` 不会触发事件。

**修复方案**: 在测试中设置 `pes.received_execute_event`。

- [MODIFY] `tests/unit/test_feature_extract_pes.py`
  - [MODIFY] `test_handle_summarize_emits_complete()`
    - 在调用 `handle_phase_response()` 之前添加：
      ```python
      from core.events.types import TaskExecuteEvent
      pes.received_execute_event = TaskExecuteEvent(
          type="task:execute",
          timestamp=time.time(),
          task_name="feature_extract",
          target_pes_id=pes.instance_id,
          generation=0,
      )
      ```

### C. 修复 `test_handle_summarize_emits_output_context`

**问题**: 同上，需要设置 `received_execute_event`。

- [MODIFY] `tests/unit/test_feature_extract_pes.py`
  - [MODIFY] `test_handle_summarize_emits_output_context()`
    - 在第一次调用 `handle_phase_response()` 之前添加同样的 `received_execute_event` 设置

## 1.4 验证计划（Verification Plan）

1. 运行 `pytest tests/integration/test_dispatch_flow.py -v`
2. 运行 `pytest tests/unit/test_feature_extract_pes.py::test_handle_summarize_emits_complete -v`
3. 运行 `pytest tests/unit/test_feature_extract_pes.py::test_handle_summarize_emits_output_context -v`
4. 运行全量测试 `pytest tests/ -v`，确认 54 passed, 0 failed

## 约束与备注

- 本计划只修复测试，不修改生产代码
- 遵循 evolve.md §6.1 的测试策略：尽量不使用 mock，使用真实配置和真实数据 manifest
- 保持测试对被测行为的聚焦，避免引入不必要的复杂度
