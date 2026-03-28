# 015: 任务调度器实现

## 元信息
- 状态: draft
- 创建: 2026-03-28
- 负责人: Codex

## 1.1 摘要

实现 `Scheduler` 调度器，负责驱动整个任务执行流程。调度器持续发出 `draft` 任务，等待每个任务完成后发出下一个，直到达到配置的任务数量。

## 1.2 审查点（Review Required）

| # | 决策项 | 当前倾向 | 说明 |
|---|--------|----------|------|
| 1 | 任务完成通知机制 | 新增 `TaskCompleteEvent` | PES 完成时发出，调度器监听 |
| 2 | 并发模式 | 串行（一个完成后再发下一个） | MVP 阶段保持简单 |
| 3 | 任务数量配置位置 | `RunConfig.max_tasks` | 默认值 1 |
| 4 | 调度器等待机制 | `asyncio.Event` | 每个 task 一个 event，等待完成 |

## 1.3 流程图

```
main.py
    │
    ├── 初始化（Config/Workspace/DB/EventBus/TaskDispatcher）
    │
    └── Scheduler.run()  ◀─────────────────────────────────────┐
          │                                                     │
          ├── dispatch_task()                                   │
          │       │                                             │
          │       └── EventBus.emit(TaskDispatchEvent)          │
          │                    │                                │
          │                    ▼                                │
          │              TaskDispatcher.handle_dispatch()       │
          │                    │                                │
          │                    ▼                                │
          │              EventBus.emit(TaskExecuteEvent)        │
          │                    │                                │
          │                    ▼                                │
          │              DraftPES.on_execute()                  │
          │                    │                                │
          │                    ▼                                │
          │              asyncio.create_task(DraftPES.run())    │
          │                    │                                │
          │                    ▼                                │
          │              EventBus.emit(TaskCompleteEvent) ──────┘
          │
          ├── await task_complete_event.wait()
          │
          ├── completed_tasks += 1
          │
          └── if completed_tasks < max_tasks:
                  → dispatch_task()
              else:
                  → return
```

## 1.4 拟议变更（Proposed Changes）

### A. 新增 `TaskCompleteEvent`

- [MODIFY] `core/events/types.py`
  - [NEW] `EventTypes.TASK_COMPLETE = "task:complete"`
  - [NEW] `TaskCompleteEvent(Event)`
    ```python
    @dataclass(slots=True)
    class TaskCompleteEvent(Event):
        EVENT_TYPE: ClassVar[str] = EventTypes.TASK_COMPLETE
        type: str = EventTypes.TASK_COMPLETE
        timestamp: float = field(default_factory=time.time)
        task_name: str = ""
        pes_instance_id: str = ""
        status: str = ""  # "completed" | "failed"
        solution_id: str = ""
    ```

### B. DraftPES 完成时发出事件

- [MODIFY] `core/pes/draft.py`
  - [MODIFY] `handle_phase_response()` phase=="summarize" 分支
    ```python
    # 现有代码
    solution.status = "completed"
    solution.finished_at = utc_now_iso()

    # [NEW] 发出完成事件
    EventBus.get().emit(TaskCompleteEvent(
        task_name=self.config.name,
        pes_instance_id=self.instance_id,
        status="completed",
        solution_id=solution.id,
    ))
    ```

### C. 新增调度器模块

- [NEW] `core/scheduler/__init__.py`
  ```python
  from core.scheduler.scheduler import Scheduler
  __all__ = ["Scheduler"]
  ```

- [NEW] `core/scheduler/scheduler.py`
  ```python
  class Scheduler:
      def __init__(
          self,
          competition_dir: str,
          max_tasks: int = 1,
          task_name: str = "draft",
          agent_name: str = "kaggle_master",
      ) -> None:
          self.competition_dir = competition_dir
          self.max_tasks = max_tasks
          self.task_name = task_name
          self.agent_name = agent_name
          self._completed_count = 0
          self._dispatched_count = 0
          self._current_task_event: asyncio.Event | None = None

      def run(self) -> None:
          """主入口，阻塞直到所有任务完成。"""
          asyncio.run(self._run_async())

      async def _run_async(self) -> None:
          EventBus.get().on(TaskCompleteEvent.EVENT_TYPE, self._on_task_complete)
          for i in range(self.max_tasks):
              self._dispatch_task(i)
              await self._wait_current_task()

      def _dispatch_task(self, index: int) -> None:
          self._current_task_event = asyncio.Event()
          EventBus.get().emit(TaskDispatchEvent(
              task_name=self.task_name,
              agent_name=self.agent_name,
              generation=index,
              context={"competition_dir": self.competition_dir},
          ))

      async def _wait_current_task(self) -> None:
          if self._current_task_event:
              await self._current_task_event.wait()

      def _on_task_complete(self, event: TaskCompleteEvent) -> None:
          self._completed_count += 1
          if self._current_task_event:
              self._current_task_event.set()
  ```

### D. 更新 `main.py`

- [MODIFY] `core/main.py`
  - [NEW] import `Scheduler`
  - [NEW] Phase 5: 启动调度器
    ```python
    # Phase 5: 启动调度器
    from core.scheduler import Scheduler
    scheduler = Scheduler(
        competition_dir=config.run.competition_dir,
        max_tasks=config.run.max_tasks,
    )
    scheduler.run()
    ```

### E. 扩展 `RunConfig`

- [MODIFY] `config/classconfig/run.py`
  ```python
  @dataclass(slots=True)
  class RunConfig:
      workspace_dir: str = "workspace"
      competition_dir: str = ""
      max_tasks: int = 1  # [NEW] 最大任务数
  ```

## 1.5 明确不做（Out of Scope）

- 不实现并发调度（多任务并行）
- 不实现失败重试逻辑
- 不实现复杂的调度策略（aggressive/conservative）
- 不实现任务优先级
- 不实现任务依赖

## 1.6 验证计划（Verification Plan）

1. **单元测试**
   - `Scheduler` 构造与属性正确
   - `_dispatch_task()` 发出正确的 `TaskDispatchEvent`

2. **集成测试**
   - `tests/integration/test_scheduler_flow.py`
   - 验证 `max_tasks=3` 时发出 3 个任务
   - 验证每个任务完成后才发下一个
   - 验证 `run()` 正常返回

3. **端到端验证**
   - `python core/main.py --run_competition_dir=/path/to/competition --run_max_tasks=2`
   - 日志显示任务分发和完成
   - 程序正常退出

## 2. 实施边界

- 本轮只实现串行调度
- 本轮只支持单一 task_name (`draft`)
- 本轮只支持单一 agent_name (`kaggle_master`)
- 本轮不处理任务失败场景

## 3. 风险与缓解

| 风险 | 缓解 |
|------|------|
| `TaskCompleteEvent` 未发出导致死锁 | 设置超时，默认 10 分钟 |
| DraftPES 异常未捕获导致事件未发出 | 在 `BasePES.run()` 的 finally 中发出失败事件 |
| EventBus 异步任务未完成程序退出 | `Scheduler.run()` 使用 `asyncio.run()` 确保事件循环运行 |

## 4. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `core/events/types.py` | MODIFY | 新增 `TaskCompleteEvent` |
| `core/events/__init__.py` | MODIFY | 导出 `TaskCompleteEvent` |
| `core/pes/draft.py` | MODIFY | 发出完成事件 |
| `core/scheduler/__init__.py` | NEW | 模块入口 |
| `core/scheduler/scheduler.py` | NEW | 调度器实现 |
| `core/main.py` | MODIFY | 启动调度器 |
| `config/classconfig/run.py` | MODIFY | 新增 `max_tasks` |
| `tests/integration/test_scheduler_flow.py` | NEW | 集成测试 |

## 5. 待审核结论

建议按本计划执行。核心是补全"谁驱动流程"的缺失环节：通过 `Scheduler` 持续发出 `TaskDispatchEvent` 并等待 `TaskCompleteEvent`，形成完整的任务执行闭环。
