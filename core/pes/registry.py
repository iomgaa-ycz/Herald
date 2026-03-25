"""PES 实例注册表。"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.pes.base import BasePES


class PESRegistry:
    """PES 实例生命周期管理器。"""

    _instance: PESRegistry | None = None

    def __init__(self) -> None:
        """初始化注册表。"""

        self._instances: dict[str, BasePES] = {}
        self._counters: dict[str, int] = defaultdict(int)

    @classmethod
    def get_instance(cls) -> PESRegistry:
        """获取全局单例。"""

        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例。"""

        cls._instance = None

    def register(self, pes: BasePES) -> str:
        """注册 PES 实例并返回实例 ID。"""

        base_name = pes.config.name.strip() or pes.__class__.__name__.lower()
        self._counters[base_name] += 1
        instance_id = f"{base_name}#{self._counters[base_name]:03d}"
        self._instances[instance_id] = pes
        return instance_id

    def get(self, instance_id: str) -> BasePES | None:
        """按实例 ID 获取 PES。"""

        return self._instances.get(instance_id)

    def get_by_base_name(self, base_name: str) -> list[BasePES]:
        """按基础名称获取所有实例。"""

        prefix = f"{base_name.strip()}#"
        return [
            instance
            for instance_id, instance in self._instances.items()
            if instance_id.startswith(prefix)
        ]

    def unregister(self, instance_id: str) -> bool:
        """注销指定实例。"""

        return self._instances.pop(instance_id, None) is not None
