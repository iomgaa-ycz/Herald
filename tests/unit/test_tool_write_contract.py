"""DraftPES tool-write 契约单元测试。"""

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
        response_text: str,
        turns: list[dict[str, object]],
        execute_writer: Callable[[Path], None] | None = None,
    ) -> None:
        """初始化测试桩。"""

        self.response_text = response_text
        self.turns = turns
        self.execute_writer = execute_writer

    async def execute_task(self, prompt: str, **kwargs: object) -> DummyResponse:
        """在 execute phase 前按需写入工作区文件。"""

        del prompt
        cwd = kwargs.get("cwd")
        if self.execute_writer is not None and isinstance(cwd, str):
            self.execute_writer(Path(cwd))
        return DummyResponse(result=self.response_text, turns=self.turns)


REPLAY_DIR = Path(__file__).resolve().parents[1] / "cases" / "replays"


def _load_replay_case(case_name: str) -> dict[str, object]:
    """读取回放用例。"""

    case_dir = REPLAY_DIR / case_name
    solution_path = case_dir / "solution.py"
    solution_code = None
    if solution_path.exists():
        solution_code = solution_path.read_text(encoding="utf-8")

    return {
        "case_dir": case_dir,
        "turns": json.loads((case_dir / "turns.json").read_text(encoding="utf-8")),
        "solution_code": solution_code,
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
            response_text="执行完成，代码已写入工作区。",
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


def test_execute_reads_non_empty_solution_file_from_workspace(tmp_path: Path) -> None:
    """execute 成功时应从工作区读取真实代码文件。"""

    replay = _load_replay_case("draft_success_tabular_v1")

    def writer(working_dir: Path) -> None:
        _write_success_runtime_artifacts(Path(replay["case_dir"]), working_dir)

    pes, workspace, db = _build_pes(tmp_path, writer, replay["turns"])
    solution = pes.create_solution(generation=0)
    db.insert_solution(solution.to_record())

    asyncio.run(pes.execute_phase(solution))

    assert workspace.read_working_solution() == str(replay["solution_code"])
    assert "artifact-based-validation" in solution.execute_summary
    assert "exit_code=0" in solution.execute_summary
    assert solution.solution_file_path == str(
        workspace.get_working_file_path("solution.py")
    )


def test_handle_execute_response_persists_code_snapshot_from_written_file(
    tmp_path: Path,
) -> None:
    """execute 成功后应将代码快照写入数据库。"""

    replay = _load_replay_case("draft_success_tabular_v1")

    def writer(working_dir: Path) -> None:
        _write_success_runtime_artifacts(Path(replay["case_dir"]), working_dir)

    pes, workspace, db = _build_pes(tmp_path, writer, replay["turns"])
    solution = pes.create_solution(generation=0)
    db.insert_solution(solution.to_record())

    asyncio.run(pes.execute_phase(solution))

    snapshot = db.get_latest_code_snapshot(solution.id)
    assert snapshot is not None
    assert snapshot["full_code"] == workspace.read_working_solution()


def test_handle_execute_response_fails_when_solution_file_missing(
    tmp_path: Path,
) -> None:
    """缺失 solution.py 时应明确失败。"""

    replay = _load_replay_case("draft_missing_solution_file_v1")
    pes, _, db = _build_pes(tmp_path, None, replay["turns"])
    solution = pes.create_solution(generation=0)
    db.insert_solution(solution.to_record())

    with pytest.raises(ValueError, match="未写出代码文件"):
        asyncio.run(pes.execute_phase(solution))

    assert solution.status == "failed"
    assert "未写出代码文件" in solution.metadata["failure_reason"]


def test_handle_execute_response_fails_when_solution_file_empty(tmp_path: Path) -> None:
    """空 solution.py 时应明确失败。"""

    replay = _load_replay_case("draft_empty_solution_file_v1")
    solution_code = str(replay["solution_code"])

    def writer(working_dir: Path) -> None:
        (working_dir / "solution.py").write_text(solution_code, encoding="utf-8")

    pes, _, db = _build_pes(tmp_path, writer, replay["turns"])
    solution = pes.create_solution(generation=0)
    db.insert_solution(solution.to_record())

    with pytest.raises(ValueError, match="代码文件为空"):
        asyncio.run(pes.execute_phase(solution))

    assert solution.status == "failed"
    assert "代码文件为空" in solution.metadata["failure_reason"]


def test_handle_execute_response_fails_on_syntax_error(tmp_path: Path) -> None:
    """语法错误应在契约校验阶段失败。"""

    replay = _load_replay_case("draft_syntax_error_v1")
    solution_code = str(replay["solution_code"])

    def writer(working_dir: Path) -> None:
        (working_dir / "solution.py").write_text(solution_code, encoding="utf-8")

    pes, _, db = _build_pes(tmp_path, writer, replay["turns"])
    solution = pes.create_solution(generation=0)
    db.insert_solution(solution.to_record())

    with pytest.raises(ValueError, match="语法错误"):
        asyncio.run(pes.execute_phase(solution))

    assert solution.status == "failed"
    assert "语法错误" in solution.metadata["failure_reason"]
