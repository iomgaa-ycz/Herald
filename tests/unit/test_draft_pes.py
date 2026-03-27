"""DraftPES 接口层单元测试。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from core.events.bus import EventBus
from core.pes.base import BasePES
from core.pes.config import PESConfig, PhaseConfig, load_pes_config
from core.pes.draft import DraftPES
from core.pes.registry import PESRegistry
from core.pes.schema import GenomeSchema, SlotContract, TaskSpec
from core.pes.types import PESSolution


def setup_function() -> None:
    """每个测试前重置全局单例。"""

    EventBus.reset()
    PESRegistry.reset()


@dataclass(slots=True)
class DummyResponse:
    """测试用模型响应。"""

    result: str
    turns: list[dict[str, object]]
    model: str = "dummy-model"
    tokens_in: int = 1
    tokens_out: int = 1
    cost_usd: float | None = None
    duration_ms: int = 0
    session_id: str | None = None


class DummyLLM:
    """记录模型调用参数的测试桩。"""

    def __init__(self) -> None:
        """初始化测试桩。"""

        self.calls: list[dict[str, object]] = []

    async def execute_task(self, prompt: str, **kwargs: object) -> DummyResponse:
        """记录调用并返回固定响应。"""

        self.calls.append({"prompt": prompt, **kwargs})
        return DummyResponse(result="ok", turns=[])


class DummyPromptManager:
    """绕过真实 Prompt 装配的测试桩。"""

    def build_prompt(
        self,
        operation: str,
        phase: str,
        context: dict[str, object],
    ) -> str:
        """返回固定 Prompt。"""

        del operation, context
        return f"prompt:{phase}"


@dataclass(slots=True)
class DummyWorkspace:
    """最小工作空间测试桩。"""

    working_dir: Path
    db_path: Path

    def summary(self) -> dict[str, str]:
        """返回最小工作空间摘要。"""

        return {
            "working_dir": str(self.working_dir),
            "db_path": str(self.db_path),
        }


class PassthroughPES(BasePES):
    """用于验证 `cwd` / `env` 透传的最小 PES。"""

    def build_phase_model_options(
        self,
        phase: str,
        solution: PESSolution,
        parent_solution: PESSolution | None,
    ) -> dict[str, object]:
        """仅在 execute phase 返回模型调用参数。"""

        del solution, parent_solution
        if phase != "execute":
            return {}
        return {
            "cwd": "/tmp/herald-working",
            "env": {"HERALD_DB_PATH": "/tmp/herald.db"},
        }

    async def handle_phase_response(
        self,
        phase: str,
        solution: PESSolution,
        response: object,
        parent_solution: PESSolution | None,
    ) -> dict[str, object]:
        """消费响应并返回最小结果。"""

        del response, parent_solution
        solution.metadata["phase"] = phase
        return {"phase": phase}


def _build_config(name: str = "draft") -> PESConfig:
    """构造最小可运行配置。"""

    return PESConfig(
        name=name,
        operation=name,
        solution_file_name="solution.py",
        submission_file_name="submission.csv",
        phases={
            "plan": PhaseConfig(
                name="plan",
                template_name=None,
                tool_names=[],
                max_retries=1,
                allowed_tools=[],
                max_turns=1,
            ),
            "execute": PhaseConfig(
                name="execute",
                template_name=None,
                tool_names=["db_cli"],
                max_retries=1,
                allowed_tools=["Bash"],
                max_turns=12,
            ),
            "summarize": PhaseConfig(
                name="summarize",
                template_name=None,
                tool_names=[],
                max_retries=1,
                allowed_tools=[],
                max_turns=1,
            ),
        },
    )


def test_schema_types_can_be_constructed() -> None:
    """最小 schema 可正常构造。"""

    task_spec = TaskSpec(
        task_type="tabular_ml",
        competition_name="demo",
        objective="maximize accuracy",
        metric_name="accuracy",
        metric_direction="max",
    )
    slot_contract = SlotContract(
        function_name="build_model",
        params=[{"name": "features", "type": "DataFrame"}],
        return_type="Model",
    )
    genome_schema = GenomeSchema(
        task_type="tabular_ml",
        slots={"MODEL": slot_contract, "FEATURE": None},
    )

    assert task_spec.metric_name == "accuracy"
    assert genome_schema.slots["MODEL"] == slot_contract
    assert genome_schema.slots["FEATURE"] is None


def test_load_draft_yaml_config() -> None:
    """`draft.yaml` 可被正常加载。"""

    config = load_pes_config("config/pes/draft.yaml")

    assert config.name == "draft"
    assert config.operation == "draft"
    assert config.solution_file_name == "solution.py"
    assert config.submission_file_name == "submission.csv"
    assert config.get_phase("execute").allowed_tools == [
        "Bash",
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
    ]
    assert config.get_phase("execute").max_turns == 12


def test_base_pes_execute_phase_passes_cwd_and_env() -> None:
    """`BasePES` 能将 phase 级 `cwd` / `env` 透传给 LLM。"""

    llm = DummyLLM()
    pes = PassthroughPES(
        config=_build_config("passthrough"),
        llm=llm,
        prompt_manager=DummyPromptManager(),
    )
    solution = pes.create_solution(generation=0)

    asyncio.run(pes.execute_phase(solution))

    assert len(llm.calls) == 1
    assert llm.calls[0]["prompt"] == "prompt:execute"
    assert llm.calls[0]["cwd"] == "/tmp/herald-working"
    assert llm.calls[0]["env"] == {"HERALD_DB_PATH": "/tmp/herald.db"}


def test_draft_pes_builds_execute_model_options_from_workspace() -> None:
    """`DraftPES` 能从 workspace 构造 execute phase 参数。"""

    workspace = DummyWorkspace(
        working_dir=Path("/tmp/herald-working"),
        db_path=Path("/tmp/herald.db"),
    )
    pes = DraftPES(
        config=_build_config(),
        llm=DummyLLM(),
        workspace=workspace,
        prompt_manager=DummyPromptManager(),
    )
    solution = pes.create_solution(generation=0)

    model_options = pes.build_phase_model_options("execute", solution, None)

    assert model_options["cwd"] == "/tmp/herald-working"
    assert model_options["env"] == {"HERALD_DB_PATH": "/tmp/herald.db"}


def test_draft_pes_handle_phase_response_is_explicit_placeholder() -> None:
    """`DraftPES` 当前应显式提示业务逻辑待实现。"""

    pes = DraftPES(
        config=_build_config(),
        llm=DummyLLM(),
        prompt_manager=DummyPromptManager(),
    )
    solution = pes.create_solution(generation=0)

    try:
        asyncio.run(
            pes.handle_phase_response(
                phase="plan",
                solution=solution,
                response=DummyResponse(result="ok", turns=[]),
                parent_solution=None,
            )
        )
    except NotImplementedError as error:
        assert "待下一轮实现" in str(error)
    else:
        raise AssertionError("预期 DraftPES.handle_phase_response 抛出 NotImplementedError")
