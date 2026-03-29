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


def test_extract_execute_fact_from_real_tool_trace(tmp_path: Path) -> None:
    """成功回放可恢复首次真实运行事实。"""

    replay = _load_replay_case("draft_success_tabular_v1")
    pes, _, _ = _build_pes(tmp_path, None, replay["turns"])
    expected = dict(replay["expected"])

    exec_fact = pes._extract_execute_fact(  # noqa: SLF001
        DummyResponse(result="执行完成", turns=replay["turns"])
    )

    assert exec_fact["command"] == str(expected.get("exec_command", "python solution.py"))
    assert exec_fact["exit_code"] == int(expected.get("exit_code", 0))
    assert exec_fact["duration_ms"] == float(expected.get("duration_ms", 1234.0))
    if replay["stdout"] is not None:
        assert exec_fact["stdout"] == replay["stdout"]
    else:
        assert exec_fact["stdout"] == "training done\nsubmission written to submission.csv"
    if replay["stderr"] is not None:
        assert exec_fact["stderr"] == replay["stderr"]
    else:
        assert exec_fact["stderr"] == ""


def test_execute_fact_non_zero_exit_code_marks_failure_after_logging(
    tmp_path: Path,
) -> None:
    """非零退出码会先写 exec_logs，再把 solution 标成 failed。"""

    replay = _load_replay_case("draft_runtime_error_v1")
    solution_code = str(replay["solution_code"])
    expected = dict(replay["expected"])

    def writer(working_dir: Path) -> None:
        (working_dir / "solution.py").write_text(solution_code, encoding="utf-8")

    pes, _, db = _build_pes(tmp_path, writer, replay["turns"])
    solution = pes.create_solution(generation=0)
    db.insert_solution(solution.to_record())

    with pytest.raises(ValueError, match="首次运行失败"):
        asyncio.run(pes.execute_phase(solution))

    exec_logs = db.get_exec_logs(solution.id)
    assert len(exec_logs) == 1
    assert exec_logs[0]["command"] == "python solution.py"
    assert exec_logs[0]["exit_code"] == int(expected.get("exit_code", 1))
    if replay["stderr"] is not None:
        assert exec_logs[0]["stderr"] == replay["stderr"]
    else:
        assert "RuntimeError: boom" in exec_logs[0]["stderr"]
    assert solution.status == "failed"
    assert "首次运行失败" in solution.metadata["failure_reason"]
