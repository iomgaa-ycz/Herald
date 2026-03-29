"""数据库 roundtrip 单元测试。"""

from __future__ import annotations

from pathlib import Path

from core.database.herald_db import HeraldDB
from core.pes.types import PESSolution
from core.utils.utils import utc_now_iso


def test_code_snapshot_roundtrip_with_real_sqlite(tmp_path: Path) -> None:
    """真实 sqlite 中的代码快照可完整 roundtrip。"""

    db = HeraldDB(str(tmp_path / "herald.db"))
    solution = PESSolution(
        id="solution-001",
        operation="draft",
        generation=0,
        status="running",
        created_at=utc_now_iso(),
        parent_ids=[],
        lineage="solution",
        run_id="run-001",
    )
    db.insert_solution(solution.to_record())
    db.insert_code_snapshot(solution.id, "def solve() -> None:\n    pass\n")

    snapshot = db.get_latest_code_snapshot(solution.id)

    assert snapshot is not None
    assert snapshot["solution_id"] == solution.id
    assert snapshot["full_code"] == "def solve() -> None:\n    pass\n"


def test_exec_log_roundtrip_with_real_sqlite(tmp_path: Path) -> None:
    """真实 sqlite 中的 exec_logs 可完整 roundtrip。"""

    db = HeraldDB(str(tmp_path / "herald.db"))
    solution = PESSolution(
        id="solution-001",
        operation="draft",
        generation=0,
        status="running",
        created_at=utc_now_iso(),
        parent_ids=[],
        lineage="solution",
        run_id="run-001",
    )
    db.insert_solution(solution.to_record())
    db.log_exec(
        solution_id=solution.id,
        command="python solution.py",
        stdout="ok\n",
        stderr="",
        exit_code=0,
        duration_ms=12.5,
        metrics={"metric_name": "auc", "metric_value": 0.7},
    )

    logs = db.get_exec_logs(solution.id)

    assert len(logs) == 1
    assert logs[0]["solution_id"] == solution.id
    assert logs[0]["command"] == "python solution.py"
    assert logs[0]["stdout"] == "ok\n"
    assert logs[0]["stderr"] == ""
    assert logs[0]["exit_code"] == 0
    assert logs[0]["duration_ms"] == 12.5
    assert logs[0]["metrics"] == {"metric_name": "auc", "metric_value": 0.7}


def test_solution_artifact_paths_roundtrip_with_real_sqlite(tmp_path: Path) -> None:
    """solution 工件路径更新后可被正确读回。"""

    db = HeraldDB(str(tmp_path / "herald.db"))
    solution = PESSolution(
        id="solution-001",
        operation="draft",
        generation=0,
        status="running",
        created_at=utc_now_iso(),
        parent_ids=[],
        lineage="solution",
        run_id="run-001",
    )
    db.insert_solution(solution.to_record())
    db.update_solution_artifacts(
        solution_id=solution.id,
        workspace_dir="/tmp/workspace/working",
        solution_file_path="/tmp/workspace/working/solution.py",
        submission_file_path="/tmp/workspace/working/submission.csv",
    )

    row = db.get_solution(solution.id)

    assert row is not None
    assert row["workspace_dir"] == "/tmp/workspace/working"
    assert row["solution_file_path"] == "/tmp/workspace/working/solution.py"
    assert row["submission_file_path"] == "/tmp/workspace/working/submission.csv"


def test_get_best_fitness_filters_by_run_id_and_excludes_current_solution(
    tmp_path: Path,
) -> None:
    """best fitness 查询支持 run 过滤与排除当前 solution。"""

    db = HeraldDB(str(tmp_path / "herald.db"))
    created_at = utc_now_iso()

    solution_a = PESSolution(
        id="solution-a",
        operation="draft",
        generation=0,
        status="completed",
        created_at=created_at,
        parent_ids=[],
        lineage="a",
        run_id="run-001",
        fitness=0.91,
    )
    solution_b = PESSolution(
        id="solution-b",
        operation="draft",
        generation=0,
        status="completed",
        created_at=created_at,
        parent_ids=[],
        lineage="b",
        run_id="run-001",
        fitness=0.85,
    )
    solution_c = PESSolution(
        id="solution-c",
        operation="draft",
        generation=0,
        status="completed",
        created_at=created_at,
        parent_ids=[],
        lineage="c",
        run_id="run-002",
        fitness=0.99,
    )

    db.insert_solution(solution_a.to_record())
    db.insert_solution(solution_b.to_record())
    db.insert_solution(solution_c.to_record())

    assert db.get_best_fitness(run_id="run-001") == 0.91
    assert (
        db.get_best_fitness(run_id="run-001", exclude_solution_id="solution-a") == 0.85
    )
