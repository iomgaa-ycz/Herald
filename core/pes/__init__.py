"""PES 模块导出。"""

from __future__ import annotations

from core.pes.config import PESConfig, PhaseConfig, load_pes_config
from core.pes.hooks import HookManager, hookimpl
from core.pes.types import PESSolution

__all__ = [
    "BasePES",
    "HookManager",
    "PESConfig",
    "PESRegistry",
    "PESSolution",
    "PhaseConfig",
    "hookimpl",
    "load_pes_config",
]


def __getattr__(name: str) -> object:
    """按需导出重模块，避免循环导入。"""

    if name == "BasePES":
        from core.pes.base import BasePES

        return BasePES
    if name == "PESRegistry":
        from core.pes.registry import PESRegistry

        return PESRegistry
    raise AttributeError(name)
