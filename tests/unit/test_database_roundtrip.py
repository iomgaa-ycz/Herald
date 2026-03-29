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
