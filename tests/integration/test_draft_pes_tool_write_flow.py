"""DraftPES tool-write 集成测试。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from core.agent.registry import AgentRegistry
from core.database.herald_db import HeraldDB
from core.events import EventBus, setup_task_dispatcher
from core.events.types import TaskCompleteEvent
from core.pes.config import load_pes_config
from core.pes.draft import DraftPES
from core.pes.registry import PESRegistry
from core.scheduler import Scheduler
from core.workspace import Workspace


def setup_function() -> None:
    """每个测试前重置全局单例。"""

    EventBus.reset()
    AgentRegistry.reset()
    PESRegistry.reset()


@dataclass(slots=True)
class DummyResponse:
    """测试用模型响应。"""

    result: str
    turns: list[dict[str, object]]
    model: str = "dummy-model"
    tokens_in: int = 1
    tokens_out: int = 1
    cost_usd: float | None = None
    duration_ms: int = 0
    session_id: str | None = None


class DummyPromptManager:
    """最小 PromptManager 测试桩。"""

    def build_prompt(
        self,
        operation: str,
        phase: str,
        context: dict[str, object],
    ) -> str:
        """返回固定 Prompt。"""

        del operation, context
        return f"prompt:{phase}"


class ReplayLLM:
    """按顺序返回回放响应，并在 execute 时写入工作区。"""

    def __init__(
        self,
        responses: list[str],
        turns: list[dict[str, object]],
        execute_writer: Callable[[Path], None] | None = None,
    ) -> None:
        """初始化测试桩。"""

        self.responses = responses
        self.turns = turns
        self.execute_writer = execute_writer
        self._index = 0

    async def execute_task(self, prompt: str, **kwargs: object) -> DummyResponse:
        """按顺序返回 phase 响应。"""

        del prompt
        cwd = kwargs.get("cwd")
        if self.execute_writer is not None and isinstance(cwd, str):
            self.execute_writer(Path(cwd))

        result = self.responses[self._index]
        self._index += 1
        return DummyResponse(result=result, turns=self.turns)


REPLAY_DIR = Path(__file__).resolve().parents[1] / "cases" / "replays"


def _load_replay_case(case_name: str) -> dict[str, object]:
    """读取回放资产。"""

    case_dir = REPLAY_DIR / case_name
    solution_path = case_dir / "solution.py"
    solution_code = None
    if solution_path.exists():
        solution_code = solution_path.read_text(encoding="utf-8")

    return {
        "turns": json.loads((case_dir / "turns.json").read_text(encoding="utf-8")),
        "solution_code": solution_code,
    }


def _build_runtime(tmp_path: Path) -> tuple[Path, Workspace, HeraldDB]:
    """构造竞赛目录、工作空间与数据库。"""

    competition_dir = tmp_path / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text("id,target\n1,0\n", encoding="utf-8")

    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)
    db = HeraldDB(str(workspace.db_path))
    return competition_dir, workspace, db


def test_draft_pes_tool_write_success_flow(tmp_path: Path) -> None:
    """成功回放会生成真实 solution.py 并同步代码快照。"""

    replay = _load_replay_case("draft_success_tabular_v1")
    solution_code = str(replay["solution_code"])

    def writer(working_dir: Path) -> None:
        (working_dir / "solution.py").write_text(solution_code, encoding="utf-8")

    competition_dir, workspace, db = _build_runtime(tmp_path)
    DraftPES(
        config=load_pes_config("config/pes/draft.yaml"),
        llm=ReplayLLM(
            responses=["计划完成", "执行完成", "总结完成"],
            turns=replay["turns"],
            execute_writer=writer,
        ),
        db=db,
        workspace=workspace,
        runtime_context={
            "competition_dir": str(competition_dir),
            "run_id": "run-001",
        },
        prompt_manager=DummyPromptManager(),
    )
    setup_task_dispatcher()

    received_events: list[TaskCompleteEvent] = []
    EventBus.get().on(TaskCompleteEvent.EVENT_TYPE, received_events.append)

    scheduler = Scheduler(
        competition_dir=str(competition_dir),
        max_tasks=1,
        context={"run_id": "run-001"},
    )
    scheduler.run()

    assert len(received_events) == 1
    assert received_events[0].status == "completed"
    assert workspace.read_working_solution() == solution_code

    snapshot = db.get_latest_code_snapshot(received_events[0].solution_id)
    assert snapshot is not None
    assert snapshot["full_code"] == workspace.read_working_solution()


@pytest.mark.parametrize(
    ("case_name", "execute_writer_factory", "expected_reason"),
    [
        ("draft_missing_solution_file_v1", lambda _: None, "未写出代码文件"),
        (
            "draft_empty_solution_file_v1",
            lambda code: (
                lambda working_dir: (working_dir / "solution.py").write_text(
                    code,
                    encoding="utf-8",
                )
            ),
            "代码文件为空",
        ),
        (
            "draft_syntax_error_v1",
            lambda code: (
                lambda working_dir: (working_dir / "solution.py").write_text(
                    code,
                    encoding="utf-8",
                )
            ),
            "语法错误",
        ),
    ],
)
def test_draft_pes_tool_write_failure_flow(
    tmp_path: Path,
    case_name: str,
    execute_writer_factory: Callable[[str | None], Callable[[Path], None] | None],
    expected_reason: str,
) -> None:
    """失败回放会显式标记 failed，且调度器不会卡住。"""

    replay = _load_replay_case(case_name)
    solution_code = replay["solution_code"]
    execute_writer = execute_writer_factory(solution_code)

    competition_dir, workspace, db = _build_runtime(tmp_path)
    DraftPES(
        config=load_pes_config("config/pes/draft.yaml"),
        llm=ReplayLLM(
            responses=["计划完成", "执行完成"],
            turns=replay["turns"],
            execute_writer=execute_writer,
        ),
        db=db,
        workspace=workspace,
        runtime_context={
            "competition_dir": str(competition_dir),
            "run_id": "run-001",
        },
        prompt_manager=DummyPromptManager(),
    )
    setup_task_dispatcher()

    received_events: list[TaskCompleteEvent] = []
    EventBus.get().on(TaskCompleteEvent.EVENT_TYPE, received_events.append)

    scheduler = Scheduler(
        competition_dir=str(competition_dir),
        max_tasks=1,
        context={"run_id": "run-001"},
    )
    scheduler.run()

    assert len(received_events) == 1
    assert received_events[0].status == "failed"

    solution_row = db.get_solution(received_events[0].solution_id)
    assert solution_row is not None
    assert solution_row["status"] == "failed"
    assert expected_reason in solution_row["execute_summary"]
