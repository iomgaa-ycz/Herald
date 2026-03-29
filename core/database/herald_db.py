from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from core.database.connection import DatabaseConnection
from core.database.queries import LineageQueries, PopulationQueries
from core.database.repositories import (
    GeneRepository,
    L2Repository,
    SnapshotRepository,
    SolutionRepository,
    TracingRepository,
)


class HeraldDB:
    """
    聚合门面：
    - 对外只暴露一个 DB 实例
    - 内部按 repo / query 分层
    - 提供便捷的转发方法
    """

    def __init__(self, db_path: str) -> None:
        self.connection = DatabaseConnection(db_path)
        conn = self.connection.conn

        self.solutions = SolutionRepository(conn)
        self.genes = GeneRepository(conn)
        self.snapshots = SnapshotRepository(conn)
        self.tracing = TracingRepository(conn)
        self.l2 = L2Repository(conn)

        self.population = PopulationQueries(conn, self.genes)
        self.lineage = LineageQueries(conn)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.connection.transaction():
            yield

    def close(self) -> None:
        self.connection.close()

    # -----------------------------
    # 便捷方法
    # -----------------------------

    def insert_solution(self, solution: dict[str, Any]) -> None:
        with self.transaction():
            self.solutions.insert(solution)

    def update_solution_artifacts(
        self,
        solution_id: str,
        workspace_dir: str | None = None,
        solution_file_path: str | None = None,
        submission_file_path: str | None = None,
    ) -> None:
        with self.transaction():
            self.solutions.update_artifacts(
                solution_id=solution_id,
                workspace_dir=workspace_dir,
                solution_file_path=solution_file_path,
                submission_file_path=submission_file_path,
            )

    def update_solution_status(
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
        with self.transaction():
            self.solutions.update_status(
                solution_id=solution_id,
                status=status,
                fitness=fitness,
                metric_name=metric_name,
                metric_value=metric_value,
                metric_direction=metric_direction,
                execute_summary=execute_summary,
                summarize_insight=summarize_insight,
                finished_at=finished_at,
            )

    def get_solution(self, solution_id: str) -> dict | None:
        return self.solutions.get(solution_id)

    def delete_solution(self, solution_id: str) -> None:
        with self.transaction():
            self.solutions.delete(solution_id)

    def insert_genes(self, solution_id: str, genes: dict) -> None:
        with self.transaction():
            self.genes.insert_batch(solution_id, genes)

    def insert_code_snapshot(self, solution_id: str, full_code: str) -> None:
        with self.transaction():
            self.snapshots.insert(solution_id, full_code)

    def get_full_code(self, solution_id: str) -> str | None:
        return self.snapshots.get_full_code(solution_id)

    def get_latest_code_snapshot(self, solution_id: str) -> dict | None:
        """获取 solution 最新代码快照。"""

        return self.snapshots.get_latest(solution_id)

    def log_llm_call(self, **kwargs: object) -> str:
        with self.transaction():
            return self.tracing.log_llm_call(**kwargs)

    def log_exec(self, **kwargs: object) -> str:
        with self.transaction():
            return self.tracing.log_exec(**kwargs)

    def get_llm_calls(self, solution_id: str) -> list[dict]:
        """获取 solution 对应的 LLM 调用记录。"""

        return self.tracing.get_llm_calls(solution_id)

    def get_exec_logs(self, solution_id: str) -> list[dict]:
        """获取 solution 对应的执行日志。"""

        return self.tracing.get_exec_logs(solution_id)

    def log_contract_check(self, **kwargs: object) -> str:
        with self.transaction():
            return self.tracing.log_contract_check(**kwargs)

    def get_contract_checks(self, solution_id: str) -> list[dict]:
        """获取 solution 对应的契约检查记录。"""

        return self.tracing.get_contract_checks(solution_id)

    def upsert_l2_insight(self, **kwargs: object) -> int:
        with self.transaction():
            return self.l2.upsert_insight(**kwargs)

    def get_l2_insights(self, slot: str, task_type: str | None = None) -> list[dict]:
        return self.l2.get_insights(slot, task_type)

    def get_all_l2_insights(self) -> list[dict]:
        return self.l2.get_all_insights()

    def get_l2_evidence(self, insight_id: int) -> list[dict]:
        return self.l2.get_evidence(insight_id)

    def get_active_solutions(self) -> list[dict]:
        return self.population.get_active_solutions()

    def get_population_summary(self) -> dict:
        return self.population.get_population_summary()

    def get_generation_stats(self) -> list[dict]:
        return self.population.get_generation_stats()

    def get_slot_history(self, slot: str) -> list[dict]:
        return self.population.get_slot_history(slot)

    def get_solutions_by_generation(self, generation: int) -> list[dict]:
        return self.solutions.get_by_generation(generation)

    def get_lineage_chain(self, solution_id: str) -> list[dict]:
        return self.lineage.get_lineage_chain(solution_id)

    def get_children(self, parent_solution_id: str) -> list[dict]:
        return self.lineage.get_children(parent_solution_id)
