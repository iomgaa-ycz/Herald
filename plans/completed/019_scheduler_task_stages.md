# 019: Scheduler 支持 task_stages + 数据传递

## 元信息
- 状态: draft
- 创建: 2026-03-28
- 对应 TD: Task 3（§6.3）

## 1.1 摘要

为现有串行 `Scheduler` 增加 `task_stages` 多阶段调度能力，并通过 `TaskCompleteEvent.output_context` 在 stage 间传递共享数据。实现后，调度器可按 `feature_extract -> draft` 的顺序驱动 PES，同时保持不传 `task_stages` 时的旧行为不变。

## 1.2 审查点（Review Required）

1. **stage 产出合并策略**: 当前倾向使用扁平 `shared_context.update(output_context)`，若同名 key 冲突，后完成任务覆盖先前值；这是最简单的 MVP 方案
2. **失败任务的调度语义**: 当前倾向保持“收到 `TaskCompleteEvent` 就解除等待”，但仅在 `status == "completed"` 时合并 `output_context`，失败处理先只记录日志，不做重试/中断
3. **测试粒度**: 当前倾向新增 `tests/unit/test_scheduler_stages.py` 覆盖 stage 顺序、上下文注入、向后兼容；保留现有 `tests/integration/test_scheduler_flow.py` 作为旧链路回归

## 1.3 拟议变更（Proposed Changes）

### A. 扩展完成事件载荷

- [MODIFY] `core/events/types.py`
  - [MODIFY] `TaskCompleteEvent`
    - 新增字段 `output_context: dict[str, Any] = field(default_factory=dict)`
    - 保持默认空字典，确保现有 `DraftPES` / `FeatureExtractPES` 发事件代码在未显式传值时仍可运行

### B. Scheduler 增加 stage 顺序调度

- [MODIFY] `core/scheduler/scheduler.py`
  - [MODIFY] `Scheduler.__init__()`
    - 新增参数 `task_stages: list[tuple[str, int]] | None = None`
    - 新增内部状态：
      - `self.task_stages`
      - `self.shared_context: dict[str, Any]`
      - `self._current_stage_name: str | None`
      - `self._current_stage_outputs: list[dict[str, Any]]`
  - [NEW] `Scheduler._resolve_task_stages() -> list[tuple[str, int]]`
    - 若传入 `task_stages`，直接返回
    - 否则退化为 `[(self.task_name, self.max_tasks)]`
  - [MODIFY] `Scheduler._run_async()`
    - 由“单层 `for range(max_tasks)`”改为“按 stage 外层循环 + stage 内串行任务循环”
    - 每个 stage 开始前重置 `self._current_stage_outputs`
    - 每个 stage 结束后把本 stage 收到的 `output_context` 合并进 `self.shared_context`
  - [NEW] `Scheduler._run_stage(stage_name: str, count: int, start_generation: int) -> int`
    - 串行分发 `count` 个任务
    - 每次等待当前任务完成
    - 返回下一次可用的 generation，保证跨 stage 仍单调递增
  - [MODIFY] `Scheduler._dispatch_task(index: int, task_name: str) -> None`
    - dispatch context 改为：
      - 基础 `competition_dir`
      - `self.context`
      - `self.shared_context`
    - `TaskDispatchEvent.task_name` 使用当前 stage 的 `task_name`
  - [MODIFY] `Scheduler._on_task_complete(event: TaskCompleteEvent) -> None`
    - 仅响应当前 stage 对应 `task_name` 的完成事件
    - 若 `event.status == "completed"` 且 `event.output_context` 非空，暂存到 `self._current_stage_outputs`
    - 解除当前等待 event
  - [NEW] `Scheduler._merge_stage_outputs() -> None`
    - 按接收顺序将 `self._current_stage_outputs` 合并进 `self.shared_context`
    - 记录日志：stage 名、合并 key、累计 shared_context key

### C. 补充单元测试覆盖新调度语义

- [NEW] `tests/unit/test_scheduler_stages.py`
  - [NEW] `test_scheduler_runs_task_stages_in_order()`
    - 构造 `Scheduler(task_stages=[("a", 1), ("b", 2)])`
    - 用事件监听记录 dispatch 顺序
    - 断言总共发出 3 个任务，顺序为 `a -> b -> b`
  - [NEW] `test_stage_output_context_flows_to_next_stage()`
    - 第一阶段完成事件携带 `output_context={"task_spec": {...}, "data_profile": "..."}`
    - 断言第二阶段收到的 `TaskDispatchEvent.context` 可见这些字段
  - [NEW] `test_scheduler_falls_back_to_legacy_single_stage()`
    - 不传 `task_stages`
    - 断言行为仍等价于 `task_name="draft", max_tasks=N`

## 1.4 验证计划（Verification Plan）

1. 运行 `pytest tests/unit/test_scheduler_stages.py`
2. 运行 `pytest tests/integration/test_scheduler_flow.py`
3. 若本地链路受影响，再补跑 `pytest tests/unit/test_feature_extract_pes.py tests/unit/test_main_bootstrap.py`
4. 人工验证点
   - `Scheduler(task_stages=[("a", 1), ("b", 2)])` 共发出 3 个 dispatch
   - stage a 的 `output_context` 在 stage b dispatch context 中可见
   - 不传 `task_stages` 时旧用法不需要改调用代码

## 1.5 实施边界

- 本任务只实现调度层的 `task_stages` 与数据透传
- 不在本任务中修改 `core/main.py` 的 bootstrap 流程
- 不在本任务中让 `FeatureExtractPES` 产出真实 `schema` / `template_content` 注入；这里只提供通用传输通道
- 不实现失败重试、并发 stage、复杂冲突合并策略

## 1.6 与当前代码的对齐说明

- 当前 `Scheduler` 仅支持单一 `task_name + max_tasks`，不具备 stage loop
- 当前 `TaskCompleteEvent` 已存在，但缺少 `output_context`
- 当前 `TaskDispatcher.handle_dispatch()` 已经会原样复制 `event.context` 到 `TaskExecuteEvent.context`，因此无需修改 dispatcher，即可承接 Scheduler 注入的数据
- 当前 `DraftPES` / `FeatureExtractPES` 已会发出 `TaskCompleteEvent`，新增字段采用默认值可避免连带破坏；后续 Task 4 再让上游 PES 真正填充业务数据
