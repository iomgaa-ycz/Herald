"""DraftPES execute 事实采集集成测试。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

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


def _write_case_runtime_artifacts(case_dir: Path, working_dir: Path) -> None:
    """将回放工件写入工作区。"""

    for file_name in ("solution.py", "submission.csv", "metrics.json", "stdout.log"):
        source_path = case_dir / file_name
        if source_path.exists():
            (working_dir / file_name).write_text(
                source_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )


def test_draft_pes_execute_fact_success_flow(tmp_path: Path) -> None:
    """成功回放会在 solution 完成后写入至少一条 exec_logs。"""

    replay = _load_replay_case("draft_success_tabular_v1")

    def writer(working_dir: Path) -> None:
        _write_case_runtime_artifacts(Path(replay["case_dir"]), working_dir)

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

    exec_logs = db.get_exec_logs(received_events[0].solution_id)
    assert len(exec_logs) >= 1
    # 产物驱动验证，command 为描述性标记
    assert exec_logs[0]["command"] == "artifact-based-validation"
    assert exec_logs[0]["exit_code"] == 0

    # stdout 从 run.log/stdout.log 读取，应包含训练日志
    assert exec_logs[0]["stdout"] is not None
    assert len(exec_logs[0]["stdout"]) > 0

    assert exec_logs[0]["metrics"]["val_metric_name"] == "auc"
    assert exec_logs[0]["metrics"]["val_metric_value"] > 0.9


def test_draft_pes_execute_fact_failure_flow(tmp_path: Path) -> None:
    """agent 未产出 submission.csv 时标记 failed。"""

    replay = _load_replay_case("draft_runtime_error_v1")
    solution_code = str(replay["solution_code"])

    def writer(working_dir: Path) -> None:
        (working_dir / "solution.py").write_text(solution_code, encoding="utf-8")

    competition_dir, workspace, db = _build_runtime(tmp_path)
    DraftPES(
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
    assert "未找到 submission.csv" in solution_row["execute_summary"]


def test_draft_pes_execute_fact_submission_schema_error_flow(tmp_path: Path) -> None:
    """submission schema 错误会被稳定识别并标记 failed。"""

    replay = _load_replay_case("draft_submission_schema_error_v1")
    solution_code = str(replay["solution_code"])

    def writer(working_dir: Path) -> None:
        _write_case_runtime_artifacts(Path(replay["case_dir"]), working_dir)
        if solution_code:
            (working_dir / "solution.py").write_text(solution_code, encoding="utf-8")

    competition_dir, workspace, db = _build_runtime(tmp_path)
    DraftPES(
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
    assert "submission.csv 校验失败" in solution_row["execute_summary"]
