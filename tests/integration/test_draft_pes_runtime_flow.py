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

    for file_name in ("solution.py", "submission.csv", "metrics.json", "stdout.log"):
        source_path = case_dir / file_name
        if source_path.exists():
            (working_dir / file_name).write_text(
                source_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )


def _write_case_runtime_artifacts_with_metric(
    case_dir: Path,
    working_dir: Path,
    metric_value: float,
) -> None:
    """写入回放工件，并覆写 metrics.json 的分数。"""

    _write_case_runtime_artifacts(case_dir=case_dir, working_dir=working_dir)
    (working_dir / "metrics.json").write_text(
        json.dumps(
            {
                "val_metric_name": "auc",
                "val_metric_value": metric_value,
                "val_metric_direction": "max",
            }
        ),
        encoding="utf-8",
    )


def _build_runtime(tmp_path: Path) -> tuple[Path, Workspace, HeraldDB]:
    """构造竞赛目录、工作空间与数据库。"""

    competition_dir = tmp_path / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text("id,target\n1,0\n", encoding="utf-8")
    # 行数需要与回放资产中的 submission.csv 匹配（5 行数据）
    (competition_dir / "sample_submission.csv").write_text(
        "id,target\n800000,0\n800001,0\n800002,0\n800003,0\n800004,0\n",
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
                "metric_name": "auc",
                "metric_direction": "max",
            },
        },
        prompt_manager=DummyPromptManager(),
    )

    solution = asyncio.run(pes.run(agent_profile=_build_agent_profile(), generation=0))
    solution_row = db.get_solution(solution.id)

    assert solution.status == "completed"
    assert solution.metrics is not None
    assert solution.metrics["val_metric_name"] == "auc"
    assert solution.metrics["val_metric_value"] > 0.9
    assert solution.fitness > 0.9
    assert solution.metadata["submission_validated"] is True
    assert solution_row is not None
    assert solution_row["status"] == "completed"
    assert solution_row["fitness"] > 0.9
    assert Path(solution_row["solution_file_path"]).exists()
    assert Path(solution_row["submission_file_path"]).exists()
    submission = workspace.read_working_submission()
    assert submission.startswith("id,target\n")
    assert len(submission.strip().split("\n")) > 1
    version_dir = Path(str(solution.metadata["version_dir"]))
    assert version_dir.exists()
    assert (version_dir / "solution.py").exists()
    assert (version_dir / "submission.csv").exists()
    assert workspace.read_best_metadata() is not None
    assert workspace.read_best_metadata()["fitness"] > 0.9
    assert solution.metadata["best_promoted"] is True


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
                "metric_name": "auc",
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
    assert isinstance(solution.metrics["val_metric_value"], float)
    assert isinstance(solution.fitness, float)
    assert solution.metadata["submission_validated"] is False
    assert "submission.csv 校验失败" in solution.metadata["failure_reason"]
    assert solution_row is not None
    assert solution_row["status"] == "failed"


def test_draft_pes_runtime_lower_fitness_does_not_override_best(tmp_path: Path) -> None:
    """同一 run 中更低 fitness 的解不会覆盖 best。"""

    replay = _load_replay_case("draft_success_tabular_v1")
    competition_dir, workspace, db = _build_runtime(tmp_path)

    def writer_high(working_dir: Path) -> None:
        _write_case_runtime_artifacts_with_metric(
            case_dir=Path(replay["case_dir"]),
            working_dir=working_dir,
            metric_value=0.91,
        )

    pes_high = DraftPES(
        config=load_pes_config("config/pes/draft.yaml"),
        llm=ReplayLLM(
            responses=["计划完成", "执行完成", "总结完成"],
            turns=replay["turns"],
            execute_writer=writer_high,
        ),
        db=db,
        workspace=workspace,
        runtime_context={
            "competition_dir": str(competition_dir),
            "run_id": "run-001",
            "task_spec": {
                "metric_name": "auc",
                "metric_direction": "max",
            },
        },
        prompt_manager=DummyPromptManager(),
    )
    high_solution = asyncio.run(
        pes_high.run(agent_profile=_build_agent_profile(), generation=0)
    )

    best_metadata_after_high = workspace.read_best_metadata()
    assert best_metadata_after_high is not None
    assert best_metadata_after_high["solution_id"] == high_solution.id
    assert best_metadata_after_high["fitness"] == 0.91

    def writer_low(working_dir: Path) -> None:
        _write_case_runtime_artifacts_with_metric(
            case_dir=Path(replay["case_dir"]),
            working_dir=working_dir,
            metric_value=0.52,
        )

    pes_low = DraftPES(
        config=load_pes_config("config/pes/draft.yaml"),
        llm=ReplayLLM(
            responses=["计划完成", "执行完成", "总结完成"],
            turns=replay["turns"],
            execute_writer=writer_low,
        ),
        db=db,
        workspace=workspace,
        runtime_context={
            "competition_dir": str(competition_dir),
            "run_id": "run-001",
            "task_spec": {
                "metric_name": "auc",
                "metric_direction": "max",
            },
        },
        prompt_manager=DummyPromptManager(),
    )
    low_solution = asyncio.run(
        pes_low.run(agent_profile=_build_agent_profile(), generation=1)
    )

    best_metadata_after_low = workspace.read_best_metadata()
    assert best_metadata_after_low is not None
    assert best_metadata_after_low["solution_id"] == high_solution.id
    assert best_metadata_after_low["fitness"] == 0.91
    assert low_solution.metadata["best_promoted"] is False
