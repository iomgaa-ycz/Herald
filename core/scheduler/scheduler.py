"""任务调度器实现。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.events.bus import EventBus
from core.events.types import TaskCompleteEvent, TaskDispatchEvent

logger = logging.getLogger(__name__)


class Scheduler:
    """串行任务调度器。

    支持单阶段或多阶段串行发出任务，等待每个任务完成后发出下一个。
    """

    def __init__(
        self,
        competition_dir: str,
        max_tasks: int = 1,
        task_name: str = "draft",
        agent_name: str = "kaggle_master",
        context: dict[str, Any] | None = None,
        task_stages: list[tuple[str, int]] | None = None,
        stage_max_retries: dict[str, int] | None = None,
    ) -> None:
        """初始化调度器。

        Args:
            competition_dir: 竞赛数据目录路径
            max_tasks: 最大任务数
            task_name: 任务名称（默认 draft）
            agent_name: Agent 名称（默认 kaggle_master）
            context: 额外上下文信息
            task_stages: 多阶段任务定义，格式为 [(task_name, count), ...]
            stage_max_retries: 各 stage 最大重试次数，如 {"feature_extract": 2}
        """
        self.competition_dir = competition_dir
        self.max_tasks = max_tasks
        self.task_name = task_name
        self.agent_name = agent_name
        self.context = context or {}
        self.task_stages = task_stages
        self._stage_max_retries = stage_max_retries or {}

        self._completed_count = 0
        self._total_tasks = 0
        self._current_task_event: asyncio.Event | None = None
        self._current_stage_name: str | None = None
        self._current_stage_outputs: list[dict[str, Any]] = []
        self._last_task_status: str | None = None
        self.shared_context: dict[str, Any] = {}
        self._db: object | None = None

    def run(self) -> None:
        """主入口，阻塞直到所有任务完成。"""
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        """异步主循环。"""
        task_stages = self._resolve_task_stages()
        self._total_tasks = sum(count for _, count in task_stages)

        # 注册任务完成监听器
        EventBus.get().on(TaskCompleteEvent.EVENT_TYPE, self._on_task_complete)

        logger.info(
            "调度器启动: total_tasks=%d, task_stages=%s, agent=%s",
            self._total_tasks,
            task_stages,
            self.agent_name,
        )

        generation = 0
        for stage_name, count in task_stages:
            generation = await self._run_stage(
                stage_name=stage_name,
                count=count,
                start_generation=generation,
            )

        logger.info("调度器完成: 共执行 %d 个任务", self._completed_count)

    def _resolve_task_stages(self) -> list[tuple[str, int]]:
        """解析最终使用的 stage 配置。"""

        if self.task_stages is not None:
            return list(self.task_stages)
        return [(self.task_name, self.max_tasks)]

    async def _run_stage(
        self,
        stage_name: str,
        count: int,
        start_generation: int,
    ) -> int:
        """串行执行单个 stage，支持失败重试。

        Args:
            stage_name: 当前阶段任务名
            count: 当前阶段任务数
            start_generation: 当前阶段起始 generation

        Returns:
            下一阶段可用的 generation 起点
        """

        self._current_stage_name = stage_name
        self._current_stage_outputs = []
        max_retries = self._stage_max_retries.get(stage_name, 0)
        logger.info(
            "开始执行 stage: task=%s, count=%d, max_retries=%d",
            stage_name,
            count,
            max_retries,
        )

        generation = start_generation
        for task_idx in range(count):
            for attempt in range(1 + max_retries):
                self._last_task_status = None
                self._dispatch_task(index=generation, task_name=stage_name)
                await self._wait_current_task()
                self._completed_count += 1
                logger.info("任务完成: %d/%d", self._completed_count, self._total_tasks)

                if self._last_task_status == "completed":
                    break

                # 任务失败，判断是否重试
                if attempt < max_retries:
                    logger.warning(
                        "stage '%s' 任务 %d 失败（attempt %d/%d），准备重试",
                        stage_name,
                        task_idx,
                        attempt + 1,
                        1 + max_retries,
                    )
                    generation += 1
                else:
                    logger.error(
                        "stage '%s' 任务 %d 在 %d 次尝试后仍失败",
                        stage_name,
                        task_idx,
                        1 + max_retries,
                    )

            generation += 1

        self._merge_stage_outputs()
        logger.info(
            "stage 执行完成: task=%s, shared_context_keys=%s",
            stage_name,
            sorted(self.shared_context.keys()),
        )
        return generation

    def _dispatch_task(self, index: int, task_name: str) -> None:
        """发出一个任务分发事件。

        Args:
            index: 任务序号（用作 generation）
            task_name: 当前 stage 的任务名
        """
        self._current_task_event = asyncio.Event()

        context = {
            "competition_dir": self.competition_dir,
            **self.context,
            **self.shared_context,
        }

        # mutate 阶段需要注入 parent
        if task_name == "mutate":
            parent_id = self._select_best_parent_id()
            if parent_id is not None:
                context["parent_solution_id"] = parent_id
                logger.info("mutate 阶段选择 parent: %s", parent_id)
            else:
                logger.warning("mutate 阶段未找到可用 parent，将以无 parent 模式运行")

        EventBus.get().emit(
            TaskDispatchEvent(
                task_name=task_name,
                agent_name=self.agent_name,
                generation=index,
                context=context,
            )
        )

        logger.info(
            "任务已分发: task=%s, agent=%s, generation=%d, context_keys=%s",
            task_name,
            self.agent_name,
            index,
            sorted(context.keys()),
        )

    async def _wait_current_task(self) -> None:
        """等待当前任务完成。"""
        if self._current_task_event:
            await self._current_task_event.wait()

    def _on_task_complete(self, event: TaskCompleteEvent) -> None:
        """任务完成回调。

        Args:
            event: 任务完成事件
        """
        logger.info(
            "收到任务完成事件: task=%s, status=%s, solution_id=%s",
            event.task_name,
            event.status,
            event.solution_id,
        )

        if (
            self._current_stage_name is not None
            and event.task_name != self._current_stage_name
        ):
            logger.info(
                "忽略非当前 stage 的完成事件: current_stage=%s, event_task=%s",
                self._current_stage_name,
                event.task_name,
            )
            return

        self._last_task_status = event.status

        if event.status == "completed" and event.output_context:
            self._current_stage_outputs.append(dict(event.output_context))

        if self._current_task_event:
            self._current_task_event.set()

    def set_db(self, db: object) -> None:
        """注入数据库引用，用于 parent 选择。"""
        self._db = db

    def _select_best_parent_id(self) -> str | None:
        """选择 fitness 最高的 completed solution 作为 parent。

        Returns:
            最优 solution 的 ID，无可用 solution 时返回 None
        """

        if self._db is None or not hasattr(self._db, "solutions"):
            return None

        run_id = self.context.get("run_id")
        best_fitness_fn = getattr(self._db, "get_best_fitness", None)
        if not callable(best_fitness_fn):
            return None

        best = best_fitness_fn(run_id=run_id)
        if best is None:
            return None

        solutions_repo = getattr(self._db, "solutions", None)
        if solutions_repo is None or not hasattr(solutions_repo, "list_active"):
            return None

        active_solutions = solutions_repo.list_active()
        for sol in active_solutions:
            if sol.get("fitness") == best:
                if run_id is None or sol.get("run_id") == run_id:
                    return sol["id"]
        return None

    def _merge_stage_outputs(self) -> None:
        """合并当前 stage 产出到共享上下文。"""

        merged_keys: list[str] = []
        for output_context in self._current_stage_outputs:
            self.shared_context.update(output_context)
            merged_keys.extend(output_context.keys())

        if merged_keys:
            logger.info(
                "stage 产出已合并: stage=%s, merged_keys=%s",
                self._current_stage_name,
                sorted(set(merged_keys)),
            )
