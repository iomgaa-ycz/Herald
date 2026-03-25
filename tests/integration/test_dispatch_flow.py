"""任务分发主链路集成测试。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from core.agent.registry import AgentRegistry
from core.events import EventBus, TaskDispatchEvent, setup_task_dispatcher
from core.pes.base import BasePES
from core.pes.config import PESConfig, PhaseConfig
from core.pes.registry import PESRegistry
from core.pes.types import PESSolution


@dataclass(slots=True)
class DummyResponse:
    """测试用模型响应。"""

    text: str
    model: str = "dummy-model"
    tokens_in: int = 1
    tokens_out: int = 1


class DummyLLM:
    """测试用 LLM。"""

    def __init__(self) -> None:
        """初始化测试桩。"""

        self.prompts: list[str] = []

    async def call(self, prompt: str) -> DummyResponse:
        """记录 Prompt 并返回固定响应。"""

        self.prompts.append(prompt)
        return DummyResponse(text="ok")


class MockPES(BasePES):
    """测试用 PES。"""

    async def handle_phase_response(
        self,
        phase: str,
        solution: PESSolution,
        response: object,
        parent_solution: PESSolution | None,
    ) -> dict[str, object]:
        """消费响应并写入最小结果。"""

        del parent_solution
        if phase == "plan":
            solution.plan_summary = response.text
        elif phase == "execute":
            solution.execute_summary = response.text
        elif phase == "summarize":
            solution.summarize_insight = response.text
            solution.status = "completed"
        return {"phase": phase}


def setup_function() -> None:
    """重置全局单例。"""

    EventBus.reset()
    AgentRegistry.reset()
    PESRegistry.reset()


def _build_config() -> PESConfig:
    """构造最小可运行 PES 配置。"""

    return PESConfig(
        name="mock",
        operation="default",
        solution_file_name="solution.py",
        submission_file_name="submission.csv",
        phases={
            "plan": PhaseConfig(
                name="plan",
                template_name="default_plan",
                tool_names=[],
                max_retries=1,
            ),
            "execute": PhaseConfig(
                name="execute",
                template_name="default_execute",
                tool_names=[],
                max_retries=1,
            ),
            "summarize": PhaseConfig(
                name="summarize",
                template_name="default_summarize",
                tool_names=[],
                max_retries=1,
            ),
        },
    )


def test_dispatch_to_pes() -> None:
    """完整事件流可到达目标 PES，且 Agent Persona 进入 Prompt。"""

    async def scenario() -> None:
        llm = DummyLLM()
        pes = MockPES(config=_build_config(), llm=llm)
        setup_task_dispatcher()

        EventBus.get().emit(
            TaskDispatchEvent(
                task_name="mock",
                agent_name="aggressive",
                generation=3,
                context={"slot": "l2"},
            )
        )

        await asyncio.sleep(0.05)

        assert pes.received_execute_event is not None
        assert pes.received_execute_event.target_pes_id == pes.instance_id
        assert pes.received_execute_event.context["slot"] == "l2"
        assert pes.received_execute_event.generation == 3
        assert pes._current_agent is not None
        assert pes._current_agent.name == "aggressive"
        assert llm.prompts
        assert "激进的机器学习竞赛选手" in llm.prompts[0]

    asyncio.run(scenario())
