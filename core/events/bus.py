"""EventBus 核心实现。

同步/异步事件总线，支持：
- 单例模式全局访问
- 同步和异步事件处理
- 通配符事件监听
- 事件历史记录
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Callable

from core.events.types import Event

logger = logging.getLogger(__name__)

# 类型别名
EventHandler = Callable[[Event], None]
AsyncEventHandler = Callable[[Event], Any]  # Any 用于支持 asyncio.coroutine


class EventBus:
    """事件总线。

    使用单例模式，全局唯一实例。
    支持同步事件分发和异步事件处理。

    Example:
        >>> bus = EventBus.get()
        >>> bus.on("run:started", lambda e: print(f"Run started: {e}"))
        >>> bus.emit(Event(type="run:started", timestamp=time.time()))
    """

    _instance: EventBus | None = None

    def __init__(
        self,
        *,
        history_size: int = 100,
    ) -> None:
        """初始化 EventBus。

        Args:
            history_size: 事件历史记录最大条数
        """
        self._history: deque[Event] = deque(maxlen=history_size)
        self._sync_handlers: dict[str, list[EventHandler]] = {}
        self._async_handlers: dict[str, list[AsyncEventHandler]] = {}
        self._running_tasks: set[asyncio.Task] = set()

    @classmethod
    def get(cls) -> EventBus:
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（仅用于测试）。"""
        if cls._instance is not None:
            cls._instance._history.clear()
            cls._instance._sync_handlers.clear()
            cls._instance._async_handlers.clear()
            cls._instance._running_tasks.clear()
        cls._instance = None

    def on(self, event_type: str, handler: EventHandler) -> EventHandler:
        """注册同步事件监听器。

        Args:
            event_type: 事件类型，支持通配符 "run:*" 或 "*"（监听所有）
            handler: 事件处理函数

        Returns:
            注册的处理函数（可用于链式调用）
        """
        if event_type not in self._sync_handlers:
            self._sync_handlers[event_type] = []
        self._sync_handlers[event_type].append(handler)
        logger.debug("注册事件监听器 [event=%s, handler=%s]", event_type, handler.__name__)
        return handler

    def on_async(self, event_type: str, handler: AsyncEventHandler) -> AsyncEventHandler:
        """注册异步事件监听器。

        异步处理器在事件分发时会被调度执行，不阻塞主流程。

        Args:
            event_type: 事件类型
            handler: 异步事件处理函数

        Returns:
            注册的处理函数
        """
        if event_type not in self._async_handlers:
            self._async_handlers[event_type] = []
        self._async_handlers[event_type].append(handler)
        logger.debug("注册异步事件监听器 [event=%s, handler=%s]", event_type, handler.__name__)
        return handler

    def once(self, event_type: str, handler: EventHandler) -> EventHandler:
        """注册一次性监听器（触发一次后自动移除）。"""

        def wrapper(event: Event) -> None:
            self.off(event_type, wrapper)  # type: ignore[arg-type]
            handler(event)

        wrapper.__name__ = handler.__name__
        self.on(event_type, wrapper)
        return handler

    def off(self, event_type: str, handler: EventHandler | AsyncEventHandler) -> None:
        """移除事件监听器。"""
        if event_type in self._sync_handlers:
            try:
                self._sync_handlers[event_type].remove(handler)  # type: ignore[arg-type]
            except ValueError:
                pass
        if event_type in self._async_handlers:
            try:
                self._async_handlers[event_type].remove(handler)  # type: ignore[arg-type]
            except ValueError:
                pass

    def emit(self, event: Event) -> None:
        """同步分发事件。

        Args:
            event: 事件对象
        """
        # 记录历史
        self._history.append(event)

        # 收集匹配的同步处理器
        handlers = self._get_matching_handlers(event.type, self._sync_handlers)

        # 同步分发
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("事件处理异常 [event=%s, handler=%s]", event.type, handler.__name__)

        # 调度异步处理器
        self._schedule_async_handlers(event)

    def _get_matching_handlers(
        self, event_type: str, handler_map: dict[str, list]
    ) -> list:
        """获取匹配事件类型的处理器（支持通配符）。"""
        handlers = list(handler_map.get(event_type, []))

        # 检查通配符 "*"
        if "*" in handler_map:
            handlers.extend(handler_map["*"])

        # 检查前缀通配符 "prefix:*"
        for pattern, pattern_handlers in handler_map.items():
            if pattern.endswith(":*"):
                prefix = pattern[:-1]  # "run:*" -> "run:"
                if event_type.startswith(prefix):
                    handlers.extend(pattern_handlers)

        return handlers

    def emit_simple(self, event_type: str, **kwargs: Any) -> None:
        """快速分发简单事件。

        Args:
            event_type: 事件类型
            **kwargs: 事件数据
        """
        event = Event(type=event_type, timestamp=time.time(), **kwargs)
        self.emit(event)

    def _schedule_async_handlers(self, event: Event) -> None:
        """调度异步处理器。"""
        handlers = self._get_matching_handlers(event.type, self._async_handlers)

        for handler in handlers:
            try:
                # 尝试获取当前事件循环
                try:
                    loop = asyncio.get_running_loop()
                    task = loop.create_task(self._run_async_handler(handler, event))
                    self._running_tasks.add(task)
                    task.add_done_callback(self._running_tasks.discard)
                except RuntimeError:
                    # 没有运行中的事件循环，在新线程中运行
                    asyncio.run(self._run_async_handler(handler, event))
            except Exception:
                logger.exception(
                    "异步事件处理器调度失败 [event=%s, handler=%s]",
                    event.type,
                    handler.__name__,
                )

    async def _run_async_handler(self, handler: AsyncEventHandler, event: Event) -> None:
        """运行异步处理器。"""
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "异步事件处理异常 [event=%s, handler=%s]",
                event.type,
                handler.__name__,
            )

    @property
    def history(self) -> list[Event]:
        """获取事件历史记录。"""
        return list(self._history)

    def get_history_by_type(self, event_type: str) -> list[Event]:
        """按类型获取事件历史。"""
        return [e for e in self._history if e.type == event_type]

    def clear_history(self) -> None:
        """清空事件历史。"""
        self._history.clear()


# 便捷装饰器
def on_event(event_type: str) -> Callable[[EventHandler], EventHandler]:
    """事件监听器装饰器。

    Example:
        >>> @on_event("run:started")
        ... def handle_run_started(event: Event) -> None:
        ...     print(f"Run started at {event.timestamp}")
    """

    def decorator(handler: EventHandler) -> EventHandler:
        EventBus.get().on(event_type, handler)
        return handler

    return decorator


def on_event_async(event_type: str) -> Callable[[AsyncEventHandler], AsyncEventHandler]:
    """异步事件监听器装饰器。"""

    def decorator(handler: AsyncEventHandler) -> AsyncEventHandler:
        EventBus.get().on_async(event_type, handler)
        return handler

    return decorator
