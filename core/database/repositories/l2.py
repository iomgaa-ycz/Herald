from __future__ import annotations

from core.database.repositories.base import BaseRepository
from core.utils.utils import utc_now_iso


class L2Repository(BaseRepository):
    """L2 insight / evidence 管理。"""

    def upsert_insight(
        self,
        slot: str,
        task_type: str,
        pattern: str,
        insight: str,
        solution_id: str | None = None,
        evidence_type: str = "support",
        note: str | None = None,
    ) -> int:
        now = utc_now_iso()

        existing = self._fetchone(
            """
            SELECT * FROM l2_insights
            WHERE slot = ? AND task_type = ? AND pattern = ?
            """,
            (slot, task_type, pattern),
        )

        if existing is None:
            self._execute(
                """
                INSERT INTO l2_insights (
                    slot, task_type, pattern, insight,
                    confidence, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (slot, task_type, pattern, insight, 1.0, "active", now, now),
            )
            existing = self._fetchone(
                """
                SELECT * FROM l2_insights
                WHERE slot = ? AND task_type = ? AND pattern = ?
                """,
                (slot, task_type, pattern),
            )
        else:
            confidence = float(existing["confidence"])
            if evidence_type == "support":
                confidence += 0.5
            elif evidence_type == "contradict":
                confidence -= 0.5

            status = "deprecated" if confidence <= 0 else "active"

            self._execute(
                """
                UPDATE l2_insights
                SET insight = ?, confidence = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (insight, confidence, status, now, existing["id"]),
            )

            existing = self._fetchone(
                "SELECT * FROM l2_insights WHERE id = ?",
                (existing["id"],),
            )

        assert existing is not None

        self._execute(
            """
            INSERT INTO l2_evidence (
                insight_id, solution_id, evidence_type, note, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                existing["id"],
                solution_id,
                evidence_type,
                note,
                now,
            ),
        )

        return int(existing["id"])

    def get_insights(
        self,
        slot: str,
        task_type: str | None = None,
    ) -> list[dict]:
        if task_type is None:
            return self._fetchall(
                """
                SELECT * FROM l2_insights
                WHERE slot = ?
                ORDER BY updated_at DESC
                """,
                (slot,),
            )

        return self._fetchall(
            """
            SELECT * FROM l2_insights
            WHERE slot = ? AND task_type = ?
            ORDER BY updated_at DESC
            """,
            (slot, task_type),
        )

    def get_all_insights(self) -> list[dict]:
        return self._fetchall(
            "SELECT * FROM l2_insights ORDER BY updated_at DESC"
        )

    def get_evidence(self, insight_id: int) -> list[dict]:
        return self._fetchall(
            """
            SELECT * FROM l2_evidence
            WHERE insight_id = ?
            ORDER BY created_at DESC
            """,
            (insight_id,),
        )