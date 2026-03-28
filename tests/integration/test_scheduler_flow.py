"""调度器集成测试。"""

from __future__ import annotations

from dataclasses import dataclass

from core.agent.registry import AgentRegistry
from core.events import EventBus, setup_task_dispatcher
from core.events.types import TaskCompleteEvent
from core.pes.base import BasePES
from core.pes.config import PESConfig, PhaseConfig
from core.pes.registry import PESRegistry
from core.pes.types import PESSolution
from core.scheduler import Scheduler


@dataclass(slots=True)
class DummyResponse:
    """测试用模型响应。"""

    result: str
    turns: list = None  # type: ignore[assignment]
    model: str = "dummy-model"
    tokens_in: int = 1
    tokens_out: int = 1
    cost_usd: float | None = None
    duration_ms: int = 0
    session_id: str | None = None

    def __post_init__(self) -> None:
        if self.turns is None:
            self.turns = []


class DummyLLM:
    """测试用 LLM。"""

    def __init__(self) -> None:
        """初始化测试桩。"""
        self.prompts: list[str] = []
        self.call_count = 0

    async def execute_task(
        self,
        prompt: str,
        **kwargs: object,
    ) -> DummyResponse:
        """记录 Prompt 并返回固定响应。"""
        self.prompts.append(prompt)
        self.call_count += 1
        return DummyResponse(result=f"response_{self.call_count}")


class MockPES(BasePES):
    """测试用 PES。"""

    def __init__(self, config: PESConfig, llm: DummyLLM) -> None:
        """初始化测试 PES。"""
        self._llm = llm
        super().__init__(config=config, llm=llm)
        self.completed_count = 0

    async def handle_phase_response(
        self,
        phase: str,
        solution: PESSolution,
        response: object,
        parent_solution: PESSolution | None,
    ) -> dict[str, object]:
        """消费响应并写入最小结果。"""
        del parent_solution
        result = getattr(response, "result", "")
        if phase == "plan":
            solution.plan_summary = result
        elif phase == "execute":
            solution.execute_summary = result
        elif phase == "summarize":
            solution.summarize_insight = result
            solution.status = "completed"
            self.completed_count += 1
            # 发出任务完成事件（与 DraftPES 保持一致）
            from core.utils.utils import utc_now_iso

            solution.finished_at = utc_now_iso()
            EventBus.get().emit(
                TaskCompleteEvent(
                    task_name=self.config.name,
                    pes_instance_id=self.instance_id,
                    status="completed",
                    solution_id=solution.id,
                )
            )
        return {"phase": phase}


def setup_function() -> None:
    """重置全局单例。"""
    EventBus.reset()
    AgentRegistry.reset()
    PESRegistry.reset()


def _build_config() -> PESConfig:
    """构造最小可运行 PES 配置。"""
    return PESConfig(
        name="draft",
        operation="draft",
        solution_file_name="solution.py",
        submission_file_name="submission.csv",
        phases={
            "plan": PhaseConfig(
                name="plan",
                template_name=None,
                tool_names=[],
                max_retries=1,
                allowed_tools=[],
                max_turns=1,
            ),
            "execute": PhaseConfig(
                name="execute",
                template_name=None,
                tool_names=[],
                max_retries=1,
                allowed_tools=[],
                max_turns=1,
            ),
            "summarize": PhaseConfig(
                name="summarize",
                template_name=None,
                tool_names=[],
                max_retries=1,
                allowed_tools=[],
                max_turns=1,
            ),
        },
    )


def _run_scheduler(max_tasks: int) -> tuple[MockPES, DummyLLM]:
    """运行一次调度器并返回测试桩。"""
    llm = DummyLLM()
    pes = MockPES(config=_build_config(), llm=llm)
    setup_task_dispatcher()

    scheduler = Scheduler(
        competition_dir="/tmp/test_competition",
        max_tasks=max_tasks,
        task_name="draft",
        agent_name="kaggle_master",
    )
    scheduler.run()
    return pes, llm


def test_scheduler_dispatches_one_task() -> None:
    """调度器发出单个任务并等待完成。"""
    pes, llm = _run_scheduler(max_tasks=1)

    # 验证 PES 被执行
    assert pes.completed_count == 1
    assert llm.prompts  # 有 LLM 调用


def test_scheduler_dispatches_multiple_tasks() -> None:
    """调度器依次发出多个任务。"""
    pes, llm = _run_scheduler(max_tasks=3)

    # 验证执行了 3 个任务
    assert pes.completed_count == 3
    assert len(llm.prompts) >= 9  # 每个 task 至少 3 个 phase


def test_task_complete_event_emitted() -> None:
    """任务完成时发出 TaskCompleteEvent。"""
    llm = DummyLLM()
    MockPES(config=_build_config(), llm=llm)
    setup_task_dispatcher()

    received_events: list[TaskCompleteEvent] = []

    def capture_event(event: TaskCompleteEvent) -> None:
        received_events.append(event)

    EventBus.get().on(TaskCompleteEvent.EVENT_TYPE, capture_event)

    scheduler = Scheduler(
        competition_dir="/tmp/test_competition",
        max_tasks=2,
    )

    scheduler.run()

    # 验证收到 2 个完成事件
    assert len(received_events) == 2
    for event in received_events:
        assert event.task_name == "draft"
        assert event.status == "completed"
