from __future__ import annotations

import json

from core.database.repositories.base import BaseRepository


class LineageQueries(BaseRepository):
    """谱系相关查询。"""

    def get_children(self, parent_solution_id: str) -> list[dict]:
        rows = self._fetchall(
            """
            SELECT * FROM solutions
            WHERE parent_ids IS NOT NULL
            ORDER BY created_at ASC
            """
        )

        matched: list[dict] = []
        for row in rows:
            raw = row.get("parent_ids")
            if not raw:
                continue
            try:
                parent_ids = json.loads(raw)
            except Exception:
                continue
            if parent_solution_id in parent_ids:
                row["parent_ids"] = parent_ids
                matched.append(row)
        return matched

    def get_lineage_chain(self, solution_id: str) -> list[dict]:
        current = self._fetchone("SELECT * FROM solutions WHERE id = ?", (solution_id,))
        if current is None:
            return []

        chain = [current]
        raw = current.get("parent_ids")

        try:
            parent_ids = json.loads(raw) if raw else []
        except Exception:
            parent_ids = []

        while parent_ids:
            parent_id = parent_ids[0]
            parent = self._fetchone("SELECT * FROM solutions WHERE id = ?", (parent_id,))
            if parent is None:
                break

            chain.append(parent)

            raw = parent.get("parent_ids")
            try:
                parent_ids = json.loads(raw) if raw else []
            except Exception:
                parent_ids = []

        return list(reversed(chain))