"""Scheduler 多阶段调度单元测试。"""

from __future__ import annotations

from core.events import EventBus
from core.events.types import TaskCompleteEvent, TaskDispatchEvent
from core.scheduler import Scheduler


def setup_function() -> None:
    """每个测试前重置事件总线。"""

    EventBus.reset()


def test_scheduler_runs_task_stages_in_order() -> None:
    """`task_stages` 会按顺序串行发出任务。"""

    dispatches: list[tuple[str, int]] = []

    def on_dispatch(event: TaskDispatchEvent) -> None:
        dispatches.append((event.task_name, event.generation))
        EventBus.get().emit(
            TaskCompleteEvent(
                task_name=event.task_name,
                pes_instance_id=f"{event.task_name}-pes",
                status="completed",
                solution_id=f"solution-{event.generation}",
            )
        )

    EventBus.get().on(TaskDispatchEvent.EVENT_TYPE, on_dispatch)

    scheduler = Scheduler(
        competition_dir="/tmp/test_competition",
        task_stages=[("a", 1), ("b", 2)],
    )

    scheduler.run()

    assert dispatches == [("a", 0), ("b", 1), ("b", 2)]


def test_stage_output_context_flows_to_next_stage() -> None:
    """上一个 stage 的 `output_context` 会注入下一个 stage。"""

    dispatch_contexts: list[tuple[str, dict[str, object]]] = []

    def on_dispatch(event: TaskDispatchEvent) -> None:
        dispatch_contexts.append((event.task_name, dict(event.context)))

        output_context: dict[str, object] = {}
        if event.task_name == "feature_extract":
            output_context = {
                "task_spec": {"task_type": "tabular", "metric_name": "accuracy"},
                "data_profile": "训练集 100 行 10 列",
            }

        EventBus.get().emit(
            TaskCompleteEvent(
                task_name=event.task_name,
                pes_instance_id=f"{event.task_name}-pes",
                status="completed",
                solution_id=f"solution-{event.generation}",
                output_context=output_context,
            )
        )

    EventBus.get().on(TaskDispatchEvent.EVENT_TYPE, on_dispatch)

    scheduler = Scheduler(
        competition_dir="/tmp/test_competition",
        context={"run_id": "run-001"},
        task_stages=[("feature_extract", 1), ("draft", 2)],
    )

    scheduler.run()

    assert len(dispatch_contexts) == 3

    feature_context = dispatch_contexts[0][1]
    assert feature_context == {
        "competition_dir": "/tmp/test_competition",
        "run_id": "run-001",
    }

    draft_context_1 = dispatch_contexts[1][1]
    draft_context_2 = dispatch_contexts[2][1]
    expected_task_spec = {"task_type": "tabular", "metric_name": "accuracy"}

    assert draft_context_1["competition_dir"] == "/tmp/test_competition"
    assert draft_context_1["run_id"] == "run-001"
    assert draft_context_1["task_spec"] == expected_task_spec
    assert draft_context_1["data_profile"] == "训练集 100 行 10 列"

    assert draft_context_2["task_spec"] == expected_task_spec
    assert draft_context_2["data_profile"] == "训练集 100 行 10 列"


def test_scheduler_falls_back_to_legacy_single_stage() -> None:
    """不传 `task_stages` 时保持旧的单 stage 行为。"""

    dispatches: list[tuple[str, int]] = []

    def on_dispatch(event: TaskDispatchEvent) -> None:
        dispatches.append((event.task_name, event.generation))
        EventBus.get().emit(
            TaskCompleteEvent(
                task_name=event.task_name,
                pes_instance_id="draft-pes",
                status="completed",
                solution_id=f"solution-{event.generation}",
            )
        )

    EventBus.get().on(TaskDispatchEvent.EVENT_TYPE, on_dispatch)

    scheduler = Scheduler(
        competition_dir="/tmp/test_competition",
        max_tasks=2,
        task_name="draft",
    )

    scheduler.run()

    assert dispatches == [("draft", 0), ("draft", 1)]
