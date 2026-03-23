from __future__ import annotations

import json
from typing import Any

from core.database.repositories.base import BaseRepository


class GeneRepository(BaseRepository):
    """genes 表读写。"""

    def insert_batch(self, solution_id: str, genes: list[dict[str, Any]]) -> None:
        payloads: list[tuple] = []

        for gene in genes:
            contract_json = None
            if gene.get("contract") is not None:
                contract_json = json.dumps(
                    {
                        "function_name": gene["contract"]["function_name"],
                        "params": gene["contract"]["params"],
                        "return_type": gene["contract"]["return_type"],
                    }
                )

            payloads.append(
                (
                    solution_id,
                    gene["slot"],
                    gene.get("description"),
                    gene.get("rationale"),
                    contract_json,
                    json.dumps(gene.get("constraints", [])),
                    gene.get("version", 1),
                    gene.get("code_anchor"),
                )
            )

        self._executemany(
            """
            INSERT INTO genes (
                solution_id, slot, description, rationale,
                contract_json, constraints_json, version, code_anchor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payloads,
        )

    def get_by_solution(self, solution_id: str) -> list[dict]:
        rows = self._fetchall(
            "SELECT * FROM genes WHERE solution_id = ? ORDER BY id ASC",
            (solution_id,),
        )
        for row in rows:
            if row.get("contract_json"):
                try:
                    row["contract"] = json.loads(row["contract_json"])
                except Exception:
                    row["contract"] = None
            if row.get("constraints_json"):
                try:
                    row["constraints"] = json.loads(row["constraints_json"])
                except Exception:
                    row["constraints"] = None
        return rows

    def get_slot_history(self, slot: str) -> list[dict]:
        rows = self._fetchall(
            """
            SELECT
                g.*,
                s.generation,
                s.fitness,
                s.status,
                s.created_at,
                s.id AS solution_id
            FROM genes g
            JOIN solutions s ON s.id = g.solution_id
            WHERE g.slot = ?
            ORDER BY s.generation ASC, s.created_at ASC
            """,
            (slot,),
        )
        for row in rows:
            if row.get("contract_json"):
                try:
                    row["contract"] = json.loads(row["contract_json"])
                except Exception:
                    row["contract"] = None
            if row.get("constraints_json"):
                try:
                    row["constraints"] = json.loads(row["constraints_json"])
                except Exception:
                    row["constraints"] = None
        return rows