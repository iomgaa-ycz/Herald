from __future__ import annotations

from core.database.repositories.base import BaseRepository
from core.utils.utils import utc_now_iso


class SnapshotRepository(BaseRepository):
    """code_snapshots 表读写。"""

    def insert(self, solution_id: str, full_code: str) -> None:
        self._execute(
            """
            INSERT INTO code_snapshots (solution_id, full_code, created_at)
            VALUES (?, ?, ?)
            """,
            (solution_id, full_code, utc_now_iso()),
        )

    def get_latest(self, solution_id: str) -> dict | None:
        return self._fetchone(
            """
            SELECT * FROM code_snapshots
            WHERE solution_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (solution_id,),
        )

    def get_full_code(self, solution_id: str) -> str | None:
        snapshot = self.get_latest(solution_id)
        if snapshot is None:
            return None
        return snapshot["full_code"]
