"""PES 抽象基类。"""

from __future__ import annotations

import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.pes.config import PESConfig
from core.pes.hooks import (
    FailureHookContext,
    HookManager,
    PhaseHookContext,
    PromptHookContext,
    RunHookContext,
)
from core.pes.types import PESSolution
from core.utils.utils import utc_now_iso

if TYPE_CHECKING:
    from core.prompts.manager import PromptManager

logger = logging.getLogger(__name__)


def _normalize_tool_registry(
    tools: dict[str, Any] | list[Any] | None,
) -> dict[str, Any]:
    """将工具集合归一化为 name -> callable。"""

    if tools is None:
        return {}
    if isinstance(tools, dict):
        return tools

    registry: dict[str, Any] = {}
    for tool in tools:
        tool_name = getattr(tool, "__name__", "").strip()
        if not tool_name:
            raise ValueError(f"无法识别工具名: {tool!r}")
        registry[tool_name] = tool
    return registry


def _filter_tools_by_names(
    tools: dict[str, Any],
    names: list[str],
) -> list[Any]:
    """按名称过滤工具。"""

    selected_tools: list[Any] = []
    for name in names:
        if name in tools:
            selected_tools.append(tools[name])
    return selected_tools


class BasePES(ABC):
    """固定 Plan / Execute / Summarize 三阶段的 PES 基类。"""

    def __init__(
        self,
        config: PESConfig,
        llm: Any,
        db: Any | None = None,
        workspace: Any | None = None,
        tools: dict[str, Any] | list[Any] | None = None,
        hooks: HookManager | None = None,
        runtime_context: dict[str, Any] | None = None,
        prompt_manager: PromptManager | None = None,
    ) -> None:
        """初始化 PES 基类。"""

        self.config = config
        self.llm = llm
        self.db = db
        self.workspace = workspace
        self.tools = _normalize_tool_registry(tools)
        self.hooks = hooks or HookManager()
        self.runtime_context = runtime_context or {}
        self.prompt_manager = prompt_manager or self._create_default_prompt_manager()

    async def run(
        self,
        generation: int = 0,
        parent_solution: PESSolution | None = None,
    ) -> PESSolution:
        """执行完整 PES 三阶段流程。"""

        solution = self.create_solution(
            generation=generation,
            parent_solution=parent_solution,
        )
        self._persist_solution_created(solution)
        self.hooks.dispatch(
            "before_run",
            RunHookContext(
                pes_name=self.config.name,
                phase=None,
                solution=solution,
                parent_solution=parent_solution,
            ),
        )

        try:
            solution = await self.plan(solution, parent_solution=parent_solution)
            solution = await self.execute(solution, parent_solution=parent_solution)
            if solution.status != "failed":
                solution = await self.summarize(
                    solution,
                    parent_solution=parent_solution,
                )
            return solution
        finally:
            self.hooks.dispatch_non_blocking(
                "after_run",
                RunHookContext(
                    pes_name=self.config.name,
                    phase=None,
                    solution=solution,
                    parent_solution=parent_solution,
                ),
            )

    async def plan(
        self,
        solution: PESSolution,
        parent_solution: PESSolution | None = None,
    ) -> PESSolution:
        """执行 plan phase。"""

        return await self._run_phase("plan", solution, parent_solution)

    async def execute(
        self,
        solution: PESSolution,
        parent_solution: PESSolution | None = None,
    ) -> PESSolution:
        """执行 execute phase。"""

        return await self._run_phase("execute", solution, parent_solution)

    async def summarize(
        self,
        solution: PESSolution,
        parent_solution: PESSolution | None = None,
    ) -> PESSolution:
        """执行 summarize phase。"""

        return await self._run_phase("summarize", solution, parent_solution)

    def create_solution(
        self,
        generation: int,
        parent_solution: PESSolution | None = None,
    ) -> PESSolution:
        """创建默认 solution。"""

        solution_id = str(uuid.uuid4())
        parent_ids = [] if parent_solution is None else [parent_solution.id]
        lineage = solution_id[:8]
        if parent_solution is not None and parent_solution.lineage:
            lineage = f"{parent_solution.lineage}_{solution_id[:8]}"

        return PESSolution(
            id=solution_id,
            operation=self.config.operation,
            generation=generation,
            status="running",
            created_at=utc_now_iso(),
            parent_ids=parent_ids,
            lineage=lineage,
            run_id=self.runtime_context.get("run_id"),
        )

    async def _run_phase(
        self,
        phase: str,
        solution: PESSolution,
        parent_solution: PESSolution | None,
    ) -> PESSolution:
        """统一执行单个 phase。"""

        phase_context = PhaseHookContext(
            pes_name=self.config.name,
            phase=phase,
            solution=solution,
        )
        self.hooks.dispatch("before_phase", phase_context)

        try:
            prompt_context = self.build_prompt_context(
                phase=phase,
                solution=solution,
                parent_solution=parent_solution,
            )
            prompt_context["allowed_tools"] = self.config.get_phase(phase).tool_names
            prompt = self.render_prompt(phase, prompt_context)
            prompt_hook_context = PromptHookContext(
                pes_name=self.config.name,
                phase=phase,
                solution=solution,
                prompt=prompt,
                context=prompt_context,
            )
            self.hooks.dispatch("before_prompt", prompt_hook_context)
            response = await self.call_phase_model(
                phase=phase,
                prompt=prompt_hook_context.prompt,
            )
            self._log_llm_call(
                solution=solution,
                phase=phase,
                prompt=prompt_hook_context.prompt,
                response=response,
            )
            parsed_output = await self.handle_phase_response(
                phase=phase,
                solution=solution,
                response=response,
                parent_solution=parent_solution,
            )
            solution.phase_outputs[phase] = response.text
            phase_context.prompt = prompt_hook_context.prompt
            phase_context.response_text = response.text
            phase_context.parsed_output = parsed_output
            self.hooks.dispatch("after_phase", phase_context)
            self._persist_solution_status(solution)
            return solution
        except Exception as error:
            self.handle_phase_failure(
                phase=phase,
                solution=solution,
                error=error,
            )
            raise

    def build_prompt_context(
        self,
        phase: str,
        solution: PESSolution,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        """构造通用 Prompt 上下文。"""

        context: dict[str, Any] = dict(self.runtime_context)
        context["phase"] = phase
        context["solution"] = solution.to_prompt_payload()
        context["operation"] = self.config.operation
        context["pes_name"] = self.config.name
        if parent_solution is not None:
            context["parent_solution"] = parent_solution.to_prompt_payload()
        if self.workspace is not None and hasattr(self.workspace, "summary"):
            context["workspace"] = self.workspace.summary()
        return context

    def render_prompt(self, phase: str, context: dict[str, Any]) -> str:
        """使用 PromptManager 渲染 Prompt。"""

        return self.prompt_manager.build_prompt(
            operation=self.config.operation,
            phase=phase,
            context=context,
        )

    def _create_default_prompt_manager(self) -> PromptManager:
        """创建默认 PromptManager 实例。"""

        from core.prompts.manager import PromptManager

        base_dir = Path(__file__).parent.parent.parent / "config" / "prompts"
        return PromptManager(
            template_dir=base_dir / "templates",
            fragments_dir=base_dir / "fragments",
            spec_path=base_dir / "prompt_spec.yaml",
        )

    async def call_phase_model(self, phase: str, prompt: str) -> Any:
        """按 phase 配置调用模型。"""

        phase_config = self.config.get_phase(phase)
        last_error: Exception | None = None
        visible_tools = _filter_tools_by_names(self.tools, phase_config.tool_names)

        for _ in range(phase_config.max_retries):
            try:
                if visible_tools:
                    return await self.llm.call_with_tools(
                        prompt=prompt,
                        tools=visible_tools,
                    )
                return await self.llm.call(prompt)
            except Exception as error:
                last_error = error

        if last_error is None:
            raise RuntimeError(f"phase={phase} 未收到模型响应")
        raise last_error

    def handle_phase_failure(
        self,
        phase: str,
        solution: PESSolution,
        error: Exception,
    ) -> None:
        """统一 phase 失败处理。"""

        solution.status = "failed"
        solution.finished_at = utc_now_iso()
        self.hooks.dispatch_non_blocking(
            "on_phase_failed",
            FailureHookContext(
                pes_name=self.config.name,
                phase=phase,
                solution=solution,
                error=error,
            ),
        )
        self._persist_solution_status(solution)
        logger.exception(
            "PES phase 失败 [phase=%s, solution_id=%s]", phase, solution.id
        )

    def _persist_solution_created(self, solution: PESSolution) -> None:
        """持久化初始 solution。"""

        if self.db is None or not hasattr(self.db, "insert_solution"):
            return
        self.db.insert_solution(solution.to_record())

    def _persist_solution_status(self, solution: PESSolution) -> None:
        """持久化 solution 状态。"""

        if self.db is None or not hasattr(self.db, "update_solution_status"):
            return
        self.db.update_solution_status(
            solution_id=solution.id,
            status=solution.status,
            fitness=solution.fitness,
            metric_name=(
                solution.metrics.get("metric_name")
                if solution.metrics is not None
                else None
            ),
            metric_value=(
                solution.metrics.get("metric_value")
                if solution.metrics is not None
                else None
            ),
            metric_direction=(
                solution.metrics.get("metric_direction")
                if solution.metrics is not None
                else None
            ),
            execute_summary=solution.execute_summary or None,
            summarize_insight=solution.summarize_insight or None,
            finished_at=solution.finished_at,
        )

    def _log_llm_call(
        self,
        solution: PESSolution,
        phase: str,
        prompt: str,
        response: Any,
    ) -> None:
        """记录 LLM 调用。"""

        if self.db is None or not hasattr(self.db, "log_llm_call"):
            return
        self.db.log_llm_call(
            solution_id=solution.id,
            phase=phase,
            purpose=f"{self.config.operation}_{phase}",
            model=getattr(response, "model", None),
            input_messages=[{"role": "user", "content": prompt}],
            output_text=getattr(response, "text", None),
            tokens_in=getattr(response, "tokens_in", None),
            tokens_out=getattr(response, "tokens_out", None),
            latency_ms=getattr(response, "latency_ms", None),
            cost_usd=getattr(response, "cost_usd", None),
        )

    def _stringify_prompt_value(self, value: Any) -> str:
        """将上下文字段转为 Prompt 中可展示的字符串。"""

        if is_dataclass(value):
            value = asdict(value)
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        if isinstance(value, Path):
            return str(value)
        return str(value)

    @abstractmethod
    async def handle_phase_response(
        self,
        phase: str,
        solution: PESSolution,
        response: Any,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        """消费 phase 响应并更新 solution。"""
