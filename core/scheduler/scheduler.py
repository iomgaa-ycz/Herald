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
    ) -> None:
        """初始化调度器。

        Args:
            competition_dir: 竞赛数据目录路径
            max_tasks: 最大任务数
            task_name: 任务名称（默认 draft）
            agent_name: Agent 名称（默认 kaggle_master）
            context: 额外上下文信息
            task_stages: 多阶段任务定义，格式为 [(task_name, count), ...]
        """
        self.competition_dir = competition_dir
        self.max_tasks = max_tasks
        self.task_name = task_name
        self.agent_name = agent_name
        self.context = context or {}
        self.task_stages = task_stages

        self._completed_count = 0
        self._total_tasks = 0
        self._current_task_event: asyncio.Event | None = None
        self._current_stage_name: str | None = None
        self._current_stage_outputs: list[dict[str, Any]] = []
        self.shared_context: dict[str, Any] = {}

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
        """串行执行单个 stage。

        Args:
            stage_name: 当前阶段任务名
            count: 当前阶段任务数
            start_generation: 当前阶段起始 generation

        Returns:
            下一阶段可用的 generation 起点
        """

        self._current_stage_name = stage_name
        self._current_stage_outputs = []
        logger.info("开始执行 stage: task=%s, count=%d", stage_name, count)

        generation = start_generation
        for _ in range(count):
            self._dispatch_task(index=generation, task_name=stage_name)
            # 等待当前任务完成（使用 yield 确保事件循环有机会处理其他任务）
            await self._wait_current_task()
            self._completed_count += 1
            logger.info("任务完成: %d/%d", self._completed_count, self._total_tasks)
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

        if event.status == "completed" and event.output_context:
            self._current_stage_outputs.append(dict(event.output_context))

        if self._current_task_event:
            self._current_task_event.set()

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
