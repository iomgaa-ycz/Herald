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

    持续发出任务，等待每个任务完成后发出下一个，直到达到 max_tasks。
    """

    def __init__(
        self,
        competition_dir: str,
        max_tasks: int = 1,
        task_name: str = "draft",
        agent_name: str = "kaggle_master",
        context: dict[str, Any] | None = None,
    ) -> None:
        """初始化调度器。

        Args:
            competition_dir: 竞赛数据目录路径
            max_tasks: 最大任务数
            task_name: 任务名称（默认 draft）
            agent_name: Agent 名称（默认 kaggle_master）
            context: 额外上下文信息
        """
        self.competition_dir = competition_dir
        self.max_tasks = max_tasks
        self.task_name = task_name
        self.agent_name = agent_name
        self.context = context or {}

        self._completed_count = 0
        self._current_task_event: asyncio.Event | None = None

    def run(self) -> None:
        """主入口，阻塞直到所有任务完成。"""
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        """异步主循环。"""
        # 注册任务完成监听器
        EventBus.get().on(TaskCompleteEvent.EVENT_TYPE, self._on_task_complete)

        logger.info(
            "调度器启动: max_tasks=%d, task=%s, agent=%s",
            self.max_tasks,
            self.task_name,
            self.agent_name,
        )

        for i in range(self.max_tasks):
            self._dispatch_task(i)
            # 等待当前任务完成（使用 yield 确保事件循环有机会处理其他任务）
            await self._wait_current_task()
            self._completed_count += 1
            logger.info("任务完成: %d/%d", self._completed_count, self.max_tasks)

        logger.info("调度器完成: 共执行 %d 个任务", self._completed_count)

    def _dispatch_task(self, index: int) -> None:
        """发出一个任务分发事件。

        Args:
            index: 任务序号（用作 generation）
        """
        self._current_task_event = asyncio.Event()

        context = {
            "competition_dir": self.competition_dir,
            **self.context,
        }

        EventBus.get().emit(
            TaskDispatchEvent(
                task_name=self.task_name,
                agent_name=self.agent_name,
                generation=index,
                context=context,
            )
        )

        logger.info(
            "任务已分发: task=%s, agent=%s, generation=%d",
            self.task_name,
            self.agent_name,
            index,
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

        if self._current_task_event:
            self._current_task_event.set()
