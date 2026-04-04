"""DraftPES 首次运行事实采集单元测试。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

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
    """按回放资产写入 solution.py 的最小 LLM 测试桩。"""

    def __init__(
        self,
        turns: list[dict[str, object]],
        execute_writer: Callable[[Path], None] | None = None,
    ) -> None:
        """初始化测试桩。"""

        self.turns = turns
        self.execute_writer = execute_writer

    async def execute_task(self, prompt: str, **kwargs: object) -> DummyResponse:
        """在 execute phase 前按需写入工作区文件。"""

        del prompt
        cwd = kwargs.get("cwd")
        if self.execute_writer is not None and isinstance(cwd, str):
            self.execute_writer(Path(cwd))
        return DummyResponse(result="执行完成", turns=self.turns)


REPLAY_DIR = Path(__file__).resolve().parents[1] / "cases" / "replays"


def _load_replay_case(case_name: str) -> dict[str, object]:
    """读取回放用例。"""

    case_dir = REPLAY_DIR / case_name
    solution_path = case_dir / "solution.py"
    solution_code = None
    if solution_path.exists():
        solution_code = solution_path.read_text(encoding="utf-8")

    expected_path = case_dir / "expected.json"
    stdout_path = case_dir / "stdout.log"
    stderr_path = case_dir / "stderr.log"

    return {
        "case_dir": case_dir,
        "turns": json.loads((case_dir / "turns.json").read_text(encoding="utf-8")),
        "solution_code": solution_code,
        "expected": (
            json.loads(expected_path.read_text(encoding="utf-8"))
            if expected_path.exists()
            else {}
        ),
        "stdout": (
            stdout_path.read_text(encoding="utf-8") if stdout_path.exists() else None
        ),
        "stderr": (
            stderr_path.read_text(encoding="utf-8") if stderr_path.exists() else None
        ),
    }


def _build_workspace_and_db(tmp_path: Path) -> tuple[Workspace, HeraldDB]:
    """构造真实工作空间与 sqlite。"""

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
    return workspace, db


def _build_pes(
    tmp_path: Path,
    execute_writer: Callable[[Path], None] | None,
    turns: list[dict[str, object]],
) -> tuple[DraftPES, Workspace, HeraldDB]:
    """构造带真实 workspace/db 的 DraftPES。"""

    workspace, db = _build_workspace_and_db(tmp_path)
    pes = DraftPES(
        config=load_pes_config("config/pes/draft.yaml"),
        llm=ReplayLLM(
            turns=turns,
            execute_writer=execute_writer,
        ),
        db=db,
        workspace=workspace,
        runtime_context={"competition_dir": str(tmp_path / "competition")},
        prompt_manager=DummyPromptManager(),
    )
    return pes, workspace, db


def _write_success_runtime_artifacts(case_dir: Path, working_dir: Path) -> None:
    """将成功回放所需工件写入工作区。"""

    for file_name in ("solution.py", "submission.csv", "metrics.json", "stdout.log"):
        source_path = case_dir / file_name
        if source_path.exists():
            (working_dir / file_name).write_text(
                source_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )


def test_missing_submission_csv_marks_failure(
    tmp_path: Path,
) -> None:
    """agent 未产出 submission.csv 时 solution 标为 failed。"""

    replay = _load_replay_case("draft_runtime_error_v1")
    solution_code = str(replay["solution_code"])

    def writer(working_dir: Path) -> None:
        (working_dir / "solution.py").write_text(solution_code, encoding="utf-8")

    pes, _, db = _build_pes(tmp_path, writer, replay["turns"])
    solution = pes.create_solution(generation=0)
    db.insert_solution(solution.to_record())

    with pytest.raises(ValueError, match="未找到 submission.csv"):
        asyncio.run(pes.execute_phase(solution))

    assert solution.status == "failed"
    assert "未找到 submission.csv" in solution.metadata["failure_reason"]


def test_success_case_fills_metrics_from_runtime_artifacts(
    tmp_path: Path,
) -> None:
    """成功回放会从 runtime 工件补全结构化指标。"""

    replay = _load_replay_case("draft_success_tabular_v1")

    def writer(working_dir: Path) -> None:
        _write_success_runtime_artifacts(Path(replay["case_dir"]), working_dir)

    pes, _, db = _build_pes(tmp_path, writer, replay["turns"])
    solution = pes.create_solution(generation=0)
    db.insert_solution(solution.to_record())

    asyncio.run(pes.execute_phase(solution))

    assert solution.metrics is not None
    assert solution.metrics["val_metric_name"] == "auc"
    assert isinstance(solution.metrics["val_metric_value"], float)
    assert solution.metrics["val_metric_value"] > 0.9
