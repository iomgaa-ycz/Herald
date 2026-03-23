from __future__ import annotations

from core.database.repositories.base import BaseRepository
from core.database.repositories.gene import GeneRepository


class PopulationQueries(BaseRepository):
    """种群/代际分析查询。"""

    def __init__(self, conn, genes: GeneRepository) -> None:
        super().__init__(conn)
        self._genes = genes

    def get_active_solutions(self) -> list[dict]:
        rows = self._fetchall(
            """
            SELECT *
            FROM solutions
            WHERE status IN ('success', 'completed', 'active')
            ORDER BY fitness DESC, created_at ASC
            """
        )
        for row in rows:
            row["genes"] = self._genes.get_by_solution(row["id"])
        return rows

    def get_population_summary(self) -> dict:
        summary = self._fetchone(
            """
            SELECT
                COUNT(*) AS total,
                MAX(fitness) AS best_fitness,
                MIN(fitness) AS worst_fitness,
                AVG(fitness) AS avg_fitness
            FROM solutions
            WHERE fitness IS NOT NULL
            """
        ) or {
            "total": 0,
            "best_fitness": None,
            "worst_fitness": None,
            "avg_fitness": None,
        }

        members = self._fetchall(
            """
            SELECT
                id, generation, fitness, status, operation,
                mutated_slot, created_at
            FROM solutions
            ORDER BY generation ASC, fitness DESC, created_at ASC
            """
        )
        summary["solutions"] = members
        return summary

    def get_generation_stats(self) -> list[dict]:
        return self._fetchall("SELECT * FROM generation_stats ORDER BY generation ASC")

    def get_slot_history(self, slot: str) -> list[dict]:
        return self._genes.get_slot_history(slot)
