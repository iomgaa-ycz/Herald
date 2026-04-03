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

    def get_insights_with_solution_info(
        self,
        slot: str,
        task_type: str | None = None,
        run_id: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """获取 L2 经验并 JOIN solution 信息（fitness/metric/status）。

        MVP 阶段 insight:evidence 为严格 1:1。如果检测到同一 insight_id
        对应多条 evidence，抛出 RuntimeError——这极大概率是 bug 而非 LLM
        恰好生成了相同 pattern。

        Args:
            slot: 基因位点名
            task_type: 任务类型过滤，None 不过滤
            run_id: 按 solution.run_id 过滤，None 不过滤
            limit: 最大返回条数

        Returns:
            含 source_solution_id/fitness/metric_name/metric_value/solution_status 的字典列表
        """
        conditions = ["i.slot = ?"]
        params: list[object] = [slot]

        if task_type is not None:
            conditions.append("i.task_type = ?")
            params.append(task_type)
        if run_id is not None:
            conditions.append("s.run_id = ?")
            params.append(run_id)

        params.append(limit)

        rows = self._fetchall(
            f"""
            SELECT i.*, e.solution_id AS source_solution_id,
                   s.fitness, s.metric_name, s.metric_value,
                   s.status AS solution_status
            FROM l2_insights i
            LEFT JOIN l2_evidence e ON e.insight_id = i.id
            LEFT JOIN solutions s ON s.id = e.solution_id
            WHERE {" AND ".join(conditions)}
            ORDER BY i.updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        )

        # 防御性检查：insight:evidence 必须 1:1
        seen_ids: set[int] = set()
        for row in rows:
            iid = row["id"]
            if iid in seen_ids:
                raise RuntimeError(
                    f"L2 insight:evidence 1:1 invariant violated: "
                    f"insight_id={iid} 出现多条 evidence，"
                    f"请检查 _write_l2_knowledge 是否重复写入"
                )
            seen_ids.add(iid)

        return rows

    def get_all_insights(self) -> list[dict]:
        return self._fetchall("SELECT * FROM l2_insights ORDER BY updated_at DESC")

    def get_evidence(self, insight_id: int) -> list[dict]:
        return self._fetchall(
            """
            SELECT * FROM l2_evidence
            WHERE insight_id = ?
            ORDER BY created_at DESC
            """,
            (insight_id,),
        )
