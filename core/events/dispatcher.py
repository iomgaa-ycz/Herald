"""任务分发器实现。"""

from __future__ import annotations

import logging

from core.agent import AgentRegistry
from core.events.bus import EventBus
from core.events.types import TaskDispatchEvent, TaskExecuteEvent
from core.pes.registry import PESRegistry

logger = logging.getLogger(__name__)


class TaskDispatcher:
    """消费 TaskDispatchEvent 并转为 TaskExecuteEvent。"""

    def __init__(self) -> None:
        """初始化分发器。"""

        self.agent_registry = AgentRegistry.get()
        self.pes_registry = PESRegistry.get_instance()

    def handle_dispatch(self, event: TaskDispatchEvent) -> None:
        """处理任务分发事件。"""

        agent = self.agent_registry.load(event.agent_name)
        instances = self.pes_registry.get_by_base_name(event.task_name)
        if not instances:
            logger.error("PES 实例不存在: task_name=%s", event.task_name)
            return

        pes = instances[0]
        execute_event = TaskExecuteEvent(
            target_pes_id=pes.instance_id,
            task_name=event.task_name,
            agent=agent,
            generation=event.generation,
            context=dict(event.context),
        )
        EventBus.get().emit(execute_event)


def setup_task_dispatcher() -> TaskDispatcher:
    """注册任务分发器并返回实例。"""

    dispatcher = TaskDispatcher()
    EventBus.get().on(TaskDispatchEvent.EVENT_TYPE, dispatcher.handle_dispatch)
    return dispatcher
