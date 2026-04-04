"""MutatePES 单谱系变异实现。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from core.pes.draft import DraftPES
from core.pes.gene_utils import parse_genes_from_code, rank_mutation_candidates
from core.pes.types import PESSolution
from core.utils.utils import utc_now_iso

logger = logging.getLogger(__name__)


class MutatePES(DraftPES):
    """Gene 级变异 PES，继承 DraftPES 的 execute 产物契约。

    新增能力：
    - plan 阶段注入父代码、mutation_candidates、parent_genes
    - execute 阶段前将父代码落盘为 solution_parent.py
    - summarize 阶段记录 target_slot 和 fitness 变化
    """

    def build_prompt_context(
        self,
        phase: str,
        solution: PESSolution,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        """扩展 prompt 上下文，注入变异专用信息。

        Args:
            phase: 当前阶段名称
            solution: 当前 PESSolution 对象
            parent_solution: 父方案（可选）

        Returns:
            包含变异专用信息的上下文字典
        """

        context = super().build_prompt_context(phase, solution, parent_solution)

        if phase == "plan" and parent_solution is not None:
            context.update(self._build_mutation_plan_context(parent_solution))

        if phase in ("execute", "summarize"):
            context["target_slot"] = solution.target_slot

        return context

    def _build_mutation_plan_context(
        self,
        parent_solution: PESSolution,
    ) -> dict[str, Any]:
        """构造 plan 阶段的变异上下文。

        Args:
            parent_solution: 父方案对象

        Returns:
            包含 parent_genes 和 mutation_candidates 的字典
        """

        extra: dict[str, Any] = {}

        parent_code = self._get_parent_code(parent_solution.id)
        if parent_code is not None:
            parent_genes = parse_genes_from_code(parent_code)
            extra["parent_genes"] = parent_genes

            mutate_history = self._get_mutate_history()
            candidates = rank_mutation_candidates(
                parent_genes=list(parent_genes.keys()),
                summarize_insight=parent_solution.summarize_insight or "",
                mutate_history=mutate_history,
            )
            extra["mutation_candidates"] = candidates

        return extra

    def _get_parent_code(self, parent_id: str) -> str | None:
        """从 DB 获取父方案的完整代码。

        Args:
            parent_id: 父方案 ID

        Returns:
            父方案代码字符串，不存在时返回 None
        """

        if self.db is None or not hasattr(self.db, "get_full_code"):
            return None
        return self.db.get_full_code(parent_id)

    def _get_mutate_history(self) -> list[dict[str, Any]]:
        """获取本 run 内的 mutate 历史记录。

        Returns:
            含 slot 和 fitness_delta 的历史列表
        """

        if self.db is None or not hasattr(self.db, "list_solutions_by_run_and_operation"):
            return []

        run_id = self.runtime_context.get("run_id")
        if run_id is None:
            return []

        solutions = self.db.list_solutions_by_run_and_operation(
            run_id=run_id,
            operation="mutate",
            status="completed",
        )

        history: list[dict[str, Any]] = []
        for sol in solutions:
            mutated_slot = sol.get("mutated_slot")
            if mutated_slot is None:
                continue
            history.append({
                "slot": mutated_slot,
                "fitness_delta": 0.0,
            })
        return history

    async def _run_from_event(
        self,
        agent_profile: object,
        generation: int,
    ) -> None:
        """覆写事件驱动运行，注入 parent_solution。

        Args:
            agent_profile: Agent 配置文件
            generation: 当前代数
        """

        parent_solution = self._resolve_parent_solution()
        try:
            await self.run(
                agent_profile=agent_profile,
                generation=generation,
                parent_solution=parent_solution,
            )
        except Exception:
            logger.exception(
                "事件驱动 MutatePES 运行失败 [generation=%s]",
                generation,
            )

    def _resolve_parent_solution(self) -> PESSolution | None:
        """从 execution_context 中解析 parent_solution。

        Returns:
            重建的 PESSolution 对象，不存在时返回 None
        """

        parent_id = self._execution_context.get("parent_solution_id")
        if parent_id is None or self.db is None:
            return None

        row = self.db.get_solution(parent_id)
        if row is None:
            logger.warning("parent_solution_id=%s 对应的 solution 不存在", parent_id)
            return None

        parent_ids_raw = row.get("parent_ids", "[]")
        if isinstance(parent_ids_raw, str):
            try:
                parent_ids = json.loads(parent_ids_raw)
            except json.JSONDecodeError:
                parent_ids = []
        else:
            parent_ids = parent_ids_raw or []

        return PESSolution(
            id=row["id"],
            operation=row.get("operation", "draft"),
            generation=row.get("generation", 0),
            status=row.get("status", "completed"),
            created_at=row.get("created_at", ""),
            parent_ids=parent_ids,
            lineage=row.get("lineage"),
            run_id=row.get("run_id"),
            finished_at=row.get("finished_at"),
            fitness=row.get("fitness"),
            metrics={
                "metric_name": row.get("metric_name"),
                "metric_value": row.get("metric_value"),
                "metric_direction": row.get("metric_direction"),
            },
            plan_summary=row.get("plan_summary", ""),
            execute_summary=row.get("execute_summary", ""),
            summarize_insight=row.get("summarize_insight", ""),
        )

    async def handle_phase_response(
        self,
        phase: str,
        solution: PESSolution,
        response: object,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        """消费 phase 响应，扩展 plan 阶段的 target_slot 解析。

        Args:
            phase: 当前阶段名称
            solution: 当前 PESSolution 对象
            response: LLM 响应对象
            parent_solution: 父方案（可选）

        Returns:
            阶段处理结果字典
        """

        response_text = self._extract_response_text(response)

        if phase == "plan":
            solution.plan_summary = response_text
            target_slot = self._parse_target_slot(response_text)
            solution.target_slot = target_slot
            if parent_solution is not None:
                self._place_parent_code(parent_solution.id)
            return {
                "phase": phase,
                "response_text": response_text,
                "target_slot": target_slot,
            }

        if phase == "execute":
            return self._handle_execute_response(
                solution=solution,
                response=response,
                response_text=response_text,
            )

        if phase == "summarize":
            solution.summarize_insight = response_text
            solution.status = "completed"
            solution.finished_at = utc_now_iso()
            self._archive_completed_solution(solution)
            self._write_genes(solution)
            self._write_l2_knowledge(solution)
            self._emit_task_complete_event(solution=solution, status="completed")
            return {"phase": phase, "response_text": response_text}

        raise ValueError(f"不支持的 MutatePES phase: {phase}")

    def _parse_target_slot(self, plan_text: str) -> str | None:
        """从 plan 输出中解析选中的变异 Slot。

        优先匹配 "选中 Slot: XXX" 格式，降级匹配 GENE:XXX 格式。

        Args:
            plan_text: plan 阶段的响应文本

        Returns:
            slot 名称（大写），无法解析时返回 None
        """

        match = re.search(
            r"选中\s*Slot\s*[:：]\s*[`]?(\w+)[`]?",
            plan_text,
            re.IGNORECASE,
        )
        if match is not None:
            return match.group(1).upper()

        match = re.search(r"GENE[:\s_]*(\w+)", plan_text, re.IGNORECASE)
        if match is not None:
            slot = match.group(1).upper()
            if slot not in ("START", "END"):
                return slot

        logger.warning("未能从 plan 输出中解析 target_slot")
        return None

    def _place_parent_code(self, parent_id: str) -> None:
        """将父代码落盘到 workspace/working/solution_parent.py。

        Args:
            parent_id: 父方案 ID
        """

        parent_code = self._get_parent_code(parent_id)
        if parent_code is None:
            logger.warning("无法获取父代码，跳过 solution_parent.py 落盘")
            return

        if self.workspace is None:
            return

        working_dir = getattr(self.workspace, "working_dir", None)
        if working_dir is None:
            return

        parent_path = Path(working_dir) / "solution_parent.py"
        parent_path.write_text(parent_code, encoding="utf-8")
        logger.info("父代码已落盘: %s", parent_path)
