"""PES Hook 系统。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pluggy

from core.pes.types import PESSolution

logger = logging.getLogger(__name__)

hookspec = pluggy.HookspecMarker("herald_pes")
hookimpl = pluggy.HookimplMarker("herald_pes")


@dataclass(slots=True)
class RunHookContext:
    """运行级 hook 上下文。"""

    pes_name: str
    phase: str | None
    solution: PESSolution
    parent_solution: PESSolution | None
    workspace: object | None = None
    db: object | None = None
    runtime_context: dict[str, Any] | None = None


@dataclass(slots=True)
class PromptHookContext:
    """Prompt hook 上下文。"""

    pes_name: str
    phase: str
    solution: PESSolution
    prompt: str
    context: dict[str, Any]


@dataclass(slots=True)
class PhaseHookContext:
    """Phase 级 hook 上下文。"""

    pes_name: str
    phase: str
    solution: PESSolution
    prompt: str | None = None
    response_text: str | None = None
    parsed_output: dict[str, Any] | None = None


@dataclass(slots=True)
class SolutionFileHookContext:
    """solution 文件已生成后的 hook 上下文。"""

    pes_name: str
    solution: PESSolution
    file_path: Path
    full_code: str
    response_text: str


@dataclass(slots=True)
class ExecuteMetricsHookContext:
    """execute metrics hook 上下文。"""

    pes_name: str
    solution: PESSolution
    metrics: dict[str, Any] | None
    response_text: str


@dataclass(slots=True)
class FailureHookContext:
    """phase 失败 hook 上下文。"""

    pes_name: str
    phase: str
    solution: PESSolution
    error: Exception


class PESHookSpec:
    """PES Hook 规范。"""

    @hookspec
    def before_run(self, context: RunHookContext) -> None:
        """run 开始前触发。"""

    @hookspec
    def before_phase(self, context: PhaseHookContext) -> None:
        """phase 开始前触发。"""

    @hookspec
    def before_prompt(self, context: PromptHookContext) -> None:
        """Prompt 渲染完成后、调用模型前触发。"""

    @hookspec
    def after_phase(self, context: PhaseHookContext) -> None:
        """phase 完成后触发。"""

    @hookspec
    def after_solution_file_ready(self, context: SolutionFileHookContext) -> None:
        """execute 阶段写入 solution 文件后触发。"""

    @hookspec
    def after_execute_metrics(self, context: ExecuteMetricsHookContext) -> None:
        """execute 阶段抽取 metrics 后触发。"""

    @hookspec
    def on_phase_failed(self, context: FailureHookContext) -> None:
        """phase 失败时触发。"""

    @hookspec
    def after_run(self, context: RunHookContext) -> None:
        """run 结束后触发。"""


class HookManager:
    """pluggy HookManager 轻量封装。"""

    def __init__(self) -> None:
        self._manager = pluggy.PluginManager("herald_pes")
        self._manager.add_hookspecs(PESHookSpec)

    def register(self, plugin: object, name: str | None = None) -> None:
        """注册 hook 插件。"""

        self._manager.register(plugin, name=name)

    def dispatch(self, hook_name: str, context: Any) -> None:
        """同步分发 hook。"""

        getattr(self._manager.hook, hook_name)(context=context)

    def dispatch_non_blocking(self, hook_name: str, context: Any) -> None:
        """分发 hook，插件异常仅记日志。"""

        try:
            self.dispatch(hook_name, context)
        except Exception:
            logger.exception("Hook 执行失败 [hook=%s]", hook_name)
