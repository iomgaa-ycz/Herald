from __future__ import annotations

import json
from typing import Any

from core.database.repositories.base import BaseRepository


class SolutionRepository(BaseRepository):
    """solutions 表读写。"""

    def insert(self, data: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO solutions (
                id, generation, lineage, schema_task_type, operation,
                mutated_slot, parent_ids, fitness, metric_name,
                metric_value, metric_direction, run_id, workspace_dir,
                solution_file_path, submission_file_path, plan_summary,
                execute_summary, summarize_insight, status,
                created_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["id"],
                data["generation"],
                data.get("lineage"),
                data.get("schema_task_type"),
                data.get("operation"),
                data.get("mutated_slot"),
                json.dumps(data.get("parent_ids", [])),
                data.get("fitness"),
                data.get("metric_name"),
                data.get("metric_value"),
                data.get("metric_direction"),
                data.get("run_id"),
                data.get("workspace_dir"),
                data.get("solution_file_path"),
                data.get("submission_file_path"),
                data.get("plan_summary"),
                data.get("execute_summary"),
                data.get("summarize_insight"),
                data["status"],
                data["created_at"],
                data.get("finished_at"),
            ),
        )

    def update_status(
        self,
        solution_id: str,
        status: str,
        fitness: float | None = None,
        metric_name: str | None = None,
        metric_value: float | None = None,
        metric_direction: str | None = None,
        execute_summary: str | None = None,
        summarize_insight: str | None = None,
        finished_at: str | None = None,
    ) -> None:
        updates = ["status = ?"]
        params: list[Any] = [status]

        if fitness is not None:
            updates.append("fitness = ?")
            params.append(fitness)
        if metric_name is not None:
            updates.append("metric_name = ?")
            params.append(metric_name)
        if metric_value is not None:
            updates.append("metric_value = ?")
            params.append(metric_value)
        if metric_direction is not None:
            updates.append("metric_direction = ?")
            params.append(metric_direction)
        if execute_summary is not None:
            updates.append("execute_summary = ?")
            params.append(execute_summary)
        if summarize_insight is not None:
            updates.append("summarize_insight = ?")
            params.append(summarize_insight)
        if finished_at is not None:
            updates.append("finished_at = ?")
            params.append(finished_at)

        params.append(solution_id)

        self._execute(
            f"UPDATE solutions SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )

    def update_artifacts(
        self,
        solution_id: str,
        workspace_dir: str | None = None,
        solution_file_path: str | None = None,
        submission_file_path: str | None = None,
    ) -> None:
        updates: list[str] = []
        params: list[str] = []

        if workspace_dir is not None:
            updates.append("workspace_dir = ?")
            params.append(workspace_dir)
        if solution_file_path is not None:
            updates.append("solution_file_path = ?")
            params.append(solution_file_path)
        if submission_file_path is not None:
            updates.append("submission_file_path = ?")
            params.append(submission_file_path)

        if not updates:
            return

        params.append(solution_id)
        self._execute(
            f"UPDATE solutions SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )

    def get(self, solution_id: str) -> dict | None:
        row = self._fetchone("SELECT * FROM solutions WHERE id = ?", (solution_id,))
        if row and row.get("parent_ids"):
            try:
                row["parent_ids"] = json.loads(row["parent_ids"])
            except Exception:
                pass
        return row

    def get_by_generation(self, generation: int) -> list[dict]:
        rows = self._fetchall(
            "SELECT * FROM solutions WHERE generation = ? ORDER BY created_at ASC",
            (generation,),
        )
        for row in rows:
            if row.get("parent_ids"):
                try:
                    row["parent_ids"] = json.loads(row["parent_ids"])
                except Exception:
                    pass
        return rows

    def list_active(self) -> list[dict]:
        rows = self._fetchall(
            """
            SELECT * FROM solutions
            WHERE status IN ('success', 'completed', 'active')
            ORDER BY fitness DESC, created_at ASC
            """
        )
        for row in rows:
            if row.get("parent_ids"):
                try:
                    row["parent_ids"] = json.loads(row["parent_ids"])
                except Exception:
                    pass
        return rows

    def delete(self, solution_id: str) -> None:
        self._execute("DELETE FROM solutions WHERE id = ?", (solution_id,))
