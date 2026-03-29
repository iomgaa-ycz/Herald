"""任务分发主链路集成测试。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from core.agent.registry import AgentRegistry
from core.database.herald_db import HeraldDB
from core.events import EventBus, TaskDispatchEvent, setup_task_dispatcher
from core.pes.config import load_pes_config
from core.pes.feature_extract import FeatureExtractPES
from core.pes.registry import PESRegistry
from core.prompts.manager import PromptManager
from core.workspace import Workspace


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

    async def execute_task(
        self,
        prompt: str,
        **kwargs: object,
    ) -> DummyResponse:
        """记录 Prompt 并返回固定响应。"""

        self.prompts.append(prompt)
        return DummyResponse(result="ok")


def setup_function() -> None:
    """重置全局单例。"""

    EventBus.reset()
    AgentRegistry.reset()
    PESRegistry.reset()


def _build_prompt_manager() -> PromptManager:
    """构造真实 PromptManager。"""

    base_dir = Path(__file__).resolve().parents[2] / "config" / "prompts"
    return PromptManager(
        template_dir=base_dir / "templates",
        fragments_dir=base_dir / "fragments",
        spec_path=base_dir / "prompt_spec.yaml",
    )


def test_dispatch_to_pes(tmp_path: Path) -> None:
    """完整事件流可到达真实 FeatureExtractPES，且可加载 kaggle_master Agent。"""

    async def scenario() -> None:
        competition_dir = tmp_path / "competition"
        competition_dir.mkdir(parents=True, exist_ok=True)
        (competition_dir / "description.md").write_text(
            "# Demo Competition\n\nmetric: auc\n",
            encoding="utf-8",
        )

        workspace = Workspace(tmp_path / "workspace")
        workspace.create(competition_dir)
        db = HeraldDB(str(workspace.db_path))
        llm = DummyLLM()
        try:
            pes = FeatureExtractPES(
                config=load_pes_config("config/pes/feature_extract.yaml"),
                llm=llm,
                db=db,
                workspace=workspace,
                runtime_context={"competition_dir": str(competition_dir)},
                prompt_manager=_build_prompt_manager(),
            )
            setup_task_dispatcher()

            EventBus.get().emit(
                TaskDispatchEvent(
                    task_name="feature_extract",
                    agent_name="kaggle_master",
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
            assert pes._current_agent.name == "kaggle_master"
            assert llm.prompts
        finally:
            db.close()

    asyncio.run(scenario())
