"""兼容入口：导出 PES 抽象。"""

from core.pes import (
    BasePES,
    HookManager,
    PESConfig,
    PESSolution,
    PhaseConfig,
    hookimpl,
    load_pes_config,
)

__all__ = [
    "BasePES",
    "HookManager",
    "PESConfig",
    "PESSolution",
    "PhaseConfig",
    "hookimpl",
    "load_pes_config",
]
