"""事件类型定义。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

from core.agent.profile import AgentProfile


class EventTypes:
    """事件类型常量。"""

    PES_START = "pes:start"
    PES_STOP = "pes:stop"
    TASK_DISPATCH = "task:dispatch"
    TASK_EXECUTE = "task:execute"
    TASK_COMPLETE = "task:complete"


@dataclass(slots=True)
class Event:
    """事件基类。"""

    type: str
    timestamp: float


@dataclass(slots=True)
class PESCommandEvent(Event):
    """PES 命令事件。"""

    pes_name: str
    config: dict[str, Any] | None = None


@dataclass(slots=True)
class TaskDispatchEvent(Event):
    """任务分发事件。"""

    EVENT_TYPE: ClassVar[str] = EventTypes.TASK_DISPATCH
    type: str = EventTypes.TASK_DISPATCH
    timestamp: float = field(default_factory=time.time)
    task_name: str = ""
    agent_name: str = ""
    generation: int = 0
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TaskExecuteEvent(Event):
    """任务执行事件。"""

    EVENT_TYPE: ClassVar[str] = EventTypes.TASK_EXECUTE
    type: str = EventTypes.TASK_EXECUTE
    timestamp: float = field(default_factory=time.time)
    target_pes_id: str = ""
    task_name: str = ""
    agent: AgentProfile | None = None
    generation: int = 0
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TaskCompleteEvent(Event):
    """任务完成事件。"""

    EVENT_TYPE: ClassVar[str] = EventTypes.TASK_COMPLETE
    type: str = EventTypes.TASK_COMPLETE
    timestamp: float = field(default_factory=time.time)
    task_name: str = ""
    pes_instance_id: str = ""
    status: str = ""  # "completed" | "failed"
    solution_id: str = ""
    output_context: dict[str, Any] = field(default_factory=dict)
