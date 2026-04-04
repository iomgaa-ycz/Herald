"""DraftPES test_score 补采集成测试。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from core.agent.profile import AgentProfile
from core.database.herald_db import HeraldDB
from core.events import EventBus
from core.pes.config import load_pes_config
from core.pes.registry import PESRegistry
from core.workspace import Workspace
from tests.grading import GradingResult, create_grading_hook


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
        execute_writer,
    ) -> None:
        self.responses = responses
        self.turns = turns
        self.execute_writer = execute_writer
        self._index = 0

    async def execute_task(self, prompt: str, **kwargs: object) -> DummyResponse:
        """按顺序返回 phase 响应。"""

        del prompt
        cwd = kwargs.get("cwd")
        if isinstance(cwd, str):
            self.execute_writer(Path(cwd))

        result = self.responses[self._index]
        self._index += 1
        return DummyResponse(result=result, turns=self.turns)


REPLAY_DIR = Path(__file__).resolve().parents[1] / "cases" / "replays"


def _load_replay_case(case_name: str) -> dict[str, object]:
    case_dir = REPLAY_DIR / case_name
    return {
        "case_dir": case_dir,
        "turns": json.loads((case_dir / "turns.json").read_text(encoding="utf-8")),
    }


def _write_case_runtime_artifacts(case_dir: Path, working_dir: Path) -> None:
    for file_name in ("solution.py", "submission.csv", "metrics.json"):
        source_path = case_dir / file_name
        if source_path.exists():
            (working_dir / file_name).write_text(
                source_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )


def _build_runtime(tmp_path: Path) -> tuple[Path, Workspace, HeraldDB]:
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
    return AgentProfile(name="draft-agent", display_name="Draft Agent", prompt_text="")


def _build_pes(
    tmp_path: Path,
    case_name: str,
):
    from core.pes.draft import DraftPES

    replay = _load_replay_case(case_name)

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
            "competition_id": competition_dir.name,
            "competition_root_dir": str(competition_dir),
            "public_data_dir": str(workspace.data_dir),
            "workspace_logs_dir": str(workspace.logs_dir),
            "run_id": "run-001",
            "task_spec": {
                "metric_name": "accuracy",
                "metric_direction": "max",
            },
        },
        prompt_manager=DummyPromptManager(),
    )
    return pes, db, workspace


def test_after_run_grades_valid_submission(tmp_path: Path, monkeypatch) -> None:
    """after_run 会为有效 submission 补采 test_score。"""

    pes, db, workspace = _build_pes(tmp_path, "draft_success_tabular_v1")
    expected = GradingResult(
        competition_id="competition",
        test_score=0.88,
        test_score_direction="max",
        test_valid_submission=True,
        test_medal_level="silver",
        test_above_median=True,
        gold_threshold=0.95,
        silver_threshold=0.9,
        bronze_threshold=0.8,
        median_threshold=0.5,
        graded_at="2026-03-29T00:00:00+00:00",
    )
    monkeypatch.setattr("tests.grading.grade_submission", lambda **_: expected)
    pes.hooks.register(
        create_grading_hook(workspace_logs_dir=str(workspace.logs_dir)),
        name="grading-hook",
    )

    solution = asyncio.run(pes.run(agent_profile=_build_agent_profile(), generation=0))
    output_path = workspace.logs_dir / "grading_result.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    row = db.get_latest_grading_result(solution.id)

    assert output_path.exists()
    assert payload[-1]["solution_id"] == solution.id
    assert payload[-1]["test_score"] == 0.88
    assert row is not None
    assert row["test_score"] == 0.88
    assert row["test_medal_level"] == "silver"


def test_grading_does_not_override_fitness(tmp_path: Path, monkeypatch) -> None:
    """评分补采不会改写 fitness。"""

    pes, _, workspace = _build_pes(tmp_path, "draft_success_tabular_v1")
    expected = GradingResult(
        competition_id="competition",
        test_score=0.66,
        test_score_direction="max",
        test_valid_submission=True,
        test_medal_level="bronze",
        test_above_median=True,
        gold_threshold=0.95,
        silver_threshold=0.9,
        bronze_threshold=0.8,
        median_threshold=0.5,
        graded_at="2026-03-29T00:00:00+00:00",
    )
    monkeypatch.setattr("tests.grading.grade_submission", lambda **_: expected)
    pes.hooks.register(
        create_grading_hook(workspace_logs_dir=str(workspace.logs_dir)),
        name="grading-hook",
    )

    solution = asyncio.run(pes.run(agent_profile=_build_agent_profile(), generation=0))

    assert solution.fitness == 0.81
    assert solution.metrics is not None
    assert solution.metrics["val_metric_value"] == 0.81


def test_grading_does_not_enter_prompt_payload(tmp_path: Path, monkeypatch) -> None:
    """评分结果不会通过 prompt payload 暴露。"""

    pes, _, workspace = _build_pes(tmp_path, "draft_success_tabular_v1")
    expected = GradingResult(
        competition_id="competition",
        test_score=0.77,
        test_score_direction="max",
        test_valid_submission=True,
        test_medal_level="bronze",
        test_above_median=False,
        gold_threshold=0.95,
        silver_threshold=0.9,
        bronze_threshold=0.8,
        median_threshold=0.5,
        graded_at="2026-03-29T00:00:00+00:00",
    )
    monkeypatch.setattr("tests.grading.grade_submission", lambda **_: expected)
    pes.hooks.register(
        create_grading_hook(workspace_logs_dir=str(workspace.logs_dir)),
        name="grading-hook",
    )

    solution = asyncio.run(pes.run(agent_profile=_build_agent_profile(), generation=0))
    payload = solution.to_prompt_payload()

    assert "test_score" not in payload["metadata"]
    assert "test_medal_level" not in payload["metadata"]


def test_missing_submission_skips_without_breaking_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """缺失 submission.csv 时 hook 安全跳过。"""

    called = {"count": 0}

    def _fake_grade_submission(**_: object) -> None:
        called["count"] += 1
        return None

    pes, _, workspace = _build_pes(tmp_path, "draft_submission_missing_v1")
    monkeypatch.setattr("tests.grading.grade_submission", _fake_grade_submission)
    pes.hooks.register(
        create_grading_hook(workspace_logs_dir=str(workspace.logs_dir)),
        name="grading-hook",
    )

    with pytest.raises(ValueError, match="未找到 submission.csv"):
        asyncio.run(pes.run(agent_profile=_build_agent_profile(), generation=0))

    assert called["count"] == 0
    assert not (workspace.logs_dir / "grading_result.json").exists()


def test_invalid_submission_skips_grading(tmp_path: Path, monkeypatch) -> None:
    """submission 校验失败时不触发评分。"""

    called = {"count": 0}

    def _fake_grade_submission(**_: object) -> None:
        called["count"] += 1
        return None

    pes, _, workspace = _build_pes(tmp_path, "draft_submission_schema_error_v1")
    monkeypatch.setattr("tests.grading.grade_submission", _fake_grade_submission)
    pes.hooks.register(
        create_grading_hook(workspace_logs_dir=str(workspace.logs_dir)),
        name="grading-hook",
    )

    with pytest.raises(ValueError, match="submission.csv 校验失败"):
        asyncio.run(pes.run(agent_profile=_build_agent_profile(), generation=0))

    assert called["count"] == 0
    assert not (workspace.logs_dir / "grading_result.json").exists()
