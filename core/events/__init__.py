"""事件系统模块。

用于多触发源启动 PES。

Usage:
    from core.events import EventBus, EventTypes, on_event

    bus = EventBus.get()

    # 注册 PES 启动监听器
    @on_event(EventTypes.PES_START)
    def handle_start(event):
        pes_registry[event.pes_name].run(event.config)

    # 触发启动
    bus.emit(PESCommandEvent(
        type=EventTypes.PES_START,
        timestamp=time.time(),
        pes_name="GenePES",
    ))
"""

from __future__ import annotations

from core.events.bus import EventBus, on_event, on_event_async
from core.events.types import Event, EventTypes, PESCommandEvent

__all__ = [
    "EventBus",
    "EventTypes",
    "Event",
    "PESCommandEvent",
    "on_event",
    "on_event_async",
]
