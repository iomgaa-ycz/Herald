"""DraftPES runtime 指标与 submission 校验集成测试。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from core.agent.profile import AgentProfile
from core.database.herald_db import HeraldDB
from core.events import EventBus
from core.pes.config import load_pes_config
from core.pes.draft import DraftPES
from core.pes.registry import PESRegistry
from core.workspace import Workspace


def setup_function() -> None:
    """每个测试前重置全局单例。"""

    EventBus.reset()
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
    """按回放资产写入工作区并返回固定响应。"""

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
    return {
        "case_dir": case_dir,
        "turns": json.loads((case_dir / "turns.json").read_text(encoding="utf-8")),
    }


def _write_case_runtime_artifacts(case_dir: Path, working_dir: Path) -> None:
    """将回放工件写入工作区。"""

    for file_name in ("solution.py", "submission.csv", "metrics.json"):
        source_path = case_dir / file_name
        if source_path.exists():
            (working_dir / file_name).write_text(
                source_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )


def _build_runtime(tmp_path: Path) -> tuple[Path, Workspace, HeraldDB]:
    """构造竞赛目录、工作空间与数据库。"""

    competition_dir = tmp_path / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text("id,target\n1,0\n", encoding="utf-8")
    (competition_dir / "sample_submission.csv").write_text(
        "id,target\n1,0\n",
        encoding="utf-8",
    )

    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)
    db = HeraldDB(str(workspace.db_path))
    return competition_dir, workspace, db


def _build_agent_profile() -> AgentProfile:
    """构造最小 agent profile。"""

    return AgentProfile(
        name="draft-agent",
        display_name="Draft Agent",
        prompt_text="",
    )


def test_draft_pes_runtime_success_backfills_fitness_and_submission_validation(
    tmp_path: Path,
) -> None:
    """成功回放会同时回写 fitness 与 submission 校验结果。"""

    replay = _load_replay_case("draft_success_tabular_v1")

    def writer(working_dir: Path) -> None:
        _write_case_runtime_artifacts(Path(replay["case_dir"]), working_dir)

    competition_dir, workspace, db = _build_runtime(tmp_path)
    pes = DraftPES(
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
            "task_spec": {
                "metric_name": "accuracy",
                "metric_direction": "max",
            },
        },
        prompt_manager=DummyPromptManager(),
    )

    solution = asyncio.run(pes.run(agent_profile=_build_agent_profile(), generation=0))
    solution_row = db.get_solution(solution.id)

    assert solution.status == "completed"
    assert solution.metrics is not None
    assert solution.metrics["val_metric_value"] == 0.81
    assert solution.fitness == 0.81
    assert solution.metadata["submission_validated"] is True
    assert solution_row is not None
    assert solution_row["status"] == "completed"
    assert solution_row["fitness"] == 0.81
    assert workspace.read_working_submission() == "id,target\n1,0.9\n"


def test_draft_pes_runtime_invalid_submission_marks_failed(tmp_path: Path) -> None:
    """schema 错误的 submission 会让 solution 进入 failed。"""

    replay = _load_replay_case("draft_submission_schema_error_v1")

    def writer(working_dir: Path) -> None:
        _write_case_runtime_artifacts(Path(replay["case_dir"]), working_dir)

    competition_dir, workspace, db = _build_runtime(tmp_path)
    pes = DraftPES(
        config=load_pes_config("config/pes/draft.yaml"),
        llm=ReplayLLM(
            responses=["计划完成", "执行完成"],
            turns=replay["turns"],
            execute_writer=writer,
        ),
        db=db,
        workspace=workspace,
        runtime_context={
            "competition_dir": str(competition_dir),
            "run_id": "run-001",
            "task_spec": {
                "metric_name": "accuracy",
                "metric_direction": "max",
            },
        },
        prompt_manager=DummyPromptManager(),
    )

    solution = pes.create_solution(generation=0)
    db.insert_solution(solution.to_record())

    with pytest.raises(ValueError, match="submission.csv 校验失败"):
        asyncio.run(pes.execute_phase(solution))

    solution_row = db.get_solution(solution.id)

    assert solution.status == "failed"
    assert solution.metrics is not None
    assert solution.metrics["val_metric_value"] == 0.81
    assert solution.fitness == 0.81
    assert solution.metadata["submission_validated"] is False
    assert "submission.csv 校验失败" in solution.metadata["failure_reason"]
    assert solution_row is not None
    assert solution_row["status"] == "failed"
