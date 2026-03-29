from __future__ import annotations

import uuid
from typing import Any

from core.database.repositories.base import BaseRepository
from core.utils.utils import utc_now_iso


class GradingRepository(BaseRepository):
    """grading_results 表读写。"""

    def insert(self, data: dict[str, Any]) -> str:
        """写入一条评分结果。"""

        event_id = str(uuid.uuid4())
        self._execute(
            """
            INSERT INTO grading_results (
                id, solution_id, competition_id, test_score, test_score_direction,
                test_valid_submission, test_medal_level, test_above_median,
                gold_threshold, silver_threshold, bronze_threshold, median_threshold,
                graded_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                data["solution_id"],
                data["competition_id"],
                data["test_score"],
                data["test_score_direction"],
                1 if data["test_valid_submission"] else 0,
                data["test_medal_level"],
                1 if data["test_above_median"] else 0,
                data.get("gold_threshold"),
                data.get("silver_threshold"),
                data.get("bronze_threshold"),
                data.get("median_threshold"),
                data["graded_at"],
                utc_now_iso(),
            ),
        )
        return event_id

    def get_by_solution(self, solution_id: str) -> list[dict]:
        """读取 solution 对应的全部评分结果。"""

        rows = self._fetchall(
            """
            SELECT * FROM grading_results
            WHERE solution_id = ?
            ORDER BY graded_at ASC, created_at ASC
            """,
            (solution_id,),
        )
        return [self._normalize_row(row) for row in rows]

    def get_latest_by_solution(self, solution_id: str) -> dict | None:
        """读取 solution 最新评分结果。"""

        row = self._fetchone(
            """
            SELECT * FROM grading_results
            WHERE solution_id = ?
            ORDER BY graded_at DESC, created_at DESC
            LIMIT 1
            """,
            (solution_id,),
        )
        if row is None:
            return None
        return self._normalize_row(row)

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """将 sqlite 行中的布尔字段归一化。"""

        normalized = dict(row)
        normalized["test_valid_submission"] = bool(normalized["test_valid_submission"])
        normalized["test_above_median"] = bool(normalized["test_above_median"])
        return normalized
