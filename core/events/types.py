"""事件类型定义。"""


from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class EventTypes:
    """事件类型常量。"""

    PES_START = "pes:start"
    PES_STOP = "pes:stop"


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
