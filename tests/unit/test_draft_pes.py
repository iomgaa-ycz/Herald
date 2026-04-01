"""DraftPES 接口层单元测试。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from core.agent.profile import AgentProfile
from core.database.herald_db import HeraldDB
from core.events.bus import EventBus
from core.pes.base import BasePES
from core.pes.config import PESConfig, PhaseConfig, load_pes_config
from core.pes.draft import DraftPES
from core.pes.registry import PESRegistry
from core.pes.schema import GenomeSchema, SlotContract, TaskSpec
from core.pes.types import PESSolution
from core.prompts.manager import PromptManager


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

    def __init__(
        self,
        responses: list[str] | None = None,
        execute_code: str | None = None,
    ) -> None:
        """初始化测试桩。"""

        self.calls: list[dict[str, object]] = []
        self.responses = responses or []
        self.execute_code = execute_code
        self._index = 0

    async def execute_task(self, prompt: str, **kwargs: object) -> DummyResponse:
        """记录调用并返回固定响应。"""

        self.calls.append({"prompt": prompt, **kwargs})
        turns: list[dict[str, object]] = []
        if (
            self.execute_code is not None
            and isinstance(kwargs.get("cwd"), str)
            and "draft_execute" in prompt
        ):
            working_dir = Path(kwargs["cwd"])
            solution_path = working_dir / "solution.py"
            solution_path.write_text(self.execute_code, encoding="utf-8")
            (working_dir / "submission.csv").write_text(
                "id,target\n1,0.9\n",
                encoding="utf-8",
            )
            (working_dir / "metrics.json").write_text(
                '{"val_metric_name":"accuracy","val_metric_value":0.91,"val_metric_direction":"max"}',
                encoding="utf-8",
            )
            turns = [
                {
                    "role": "assistant",
                    "text": "已写入并执行 solution.py。",
                    "tool_calls": [
                        {
                            "name": "Bash",
                            "input": {"command": "python solution.py"},
                            "result": {
                                "stdout": (
                                    "ok\n"
                                    '{"val_metric_name":"accuracy",'
                                    '"val_metric_value":0.91,'
                                    '"val_metric_direction":"max"}\n'
                                ),
                                "stderr": "",
                                "exit_code": 0,
                                "duration_ms": 10,
                            },
                        }
                    ],
                }
            ]

        if self._index < len(self.responses):
            result = self.responses[self._index]
        else:
            result = "ok"
        self._index += 1
        return DummyResponse(result=result, turns=turns)


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

    root: Path
    data_dir: Path
    working_dir: Path
    logs_dir: Path
    db_path: Path

    def summary(self) -> dict[str, str]:
        """返回最小工作空间摘要。"""

        return {
            "workspace_root": str(self.root),
            "data_dir": str(self.data_dir),
            "working_dir": str(self.working_dir),
            "logs_dir": str(self.logs_dir),
            "db_path": str(self.db_path),
        }

    def get_working_file_path(self, file_name: str) -> Path:
        """返回 working/ 下的文件路径。"""

        return self.working_dir / file_name

    def read_working_text(self, file_name: str) -> str | None:
        """读取 working/ 下文本文件。"""

        file_path = self.get_working_file_path(file_name)
        if not file_path.exists():
            return None
        return file_path.read_text(encoding="utf-8")

    def read_working_solution(self, file_name: str = "solution.py") -> str:
        """读取工作区中的 solution.py。"""

        file_path = self.get_working_file_path(file_name)
        if not file_path.exists():
            raise ValueError(f"工作区未找到代码文件: {file_path}")

        code = file_path.read_text(encoding="utf-8")
        if not code.strip():
            raise ValueError(f"代码文件为空: {file_path}")
        return code

    def read_working_submission(self, file_name: str = "submission.csv") -> str:
        """读取工作区中的 submission.csv。"""

        file_path = self.get_working_file_path(file_name)
        if not file_path.exists():
            raise ValueError(f"工作区未找到提交文件: {file_path}")

        content = file_path.read_text(encoding="utf-8")
        if not content.strip():
            raise ValueError(f"提交文件为空: {file_path}")
        return content

    def get_working_submission_path(self, file_name: str = "submission.csv") -> Path:
        """返回 working/ 下的 submission 路径。"""

        return self.working_dir / file_name

    def read_runtime_artifact(self, file_name: str) -> str | None:
        """读取运行时文本工件。"""

        return self.read_working_text(file_name)


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


def _build_prompt_manager() -> PromptManager:
    """构造指向仓库配置目录的真实 PromptManager。"""

    base_dir = Path(__file__).resolve().parents[2] / "config" / "prompts"
    return PromptManager(
        template_dir=base_dir / "templates",
        fragments_dir=base_dir / "fragments",
        spec_path=base_dir / "prompt_spec.yaml",
    )


def _build_runtime_context(competition_dir: str) -> dict[str, object]:
    """构造 DraftPES 运行所需的最小上下文。"""

    return {
        "competition_dir": competition_dir,
        "task_spec": {
            "task_type": "tabular_ml",
            "competition_name": "demo",
            "objective": "maximize accuracy",
            "metric_name": "accuracy",
            "metric_direction": "max",
        },
        "schema": {
            "task_type": "tabular_ml",
            "slots": {
                "MODEL": {
                    "function_name": "build_model",
                    "params": [
                        {"name": "features", "type": "DataFrame"},
                    ],
                    "return_type": "Model",
                }
            },
        },
        "data_profile": "训练集 100 行，8 个数值列，2 个类别列，标签列为 target，无明显缺失值。",
        "recent_error": "",
        "template_content": "def build_model(config: dict[str, object]) -> object:\n    return None\n",
    }


def _build_workspace(tmp_path: Path) -> DummyWorkspace:
    """构造带真实目录的测试工作空间。"""

    root = tmp_path / "workspace"
    data_dir = root / "data"
    working_dir = root / "working"
    logs_dir = root / "logs"
    db_path = root / "database" / "herald.db"

    for path in (data_dir, working_dir, logs_dir, db_path.parent):
        path.mkdir(parents=True, exist_ok=True)
    db_path.touch(exist_ok=True)
    (data_dir / "sample_submission.csv").write_text(
        "id,target\n1,0\n",
        encoding="utf-8",
    )

    return DummyWorkspace(
        root=root,
        data_dir=data_dir,
        working_dir=working_dir,
        logs_dir=logs_dir,
        db_path=db_path,
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
        "Skill",
    ]
    assert config.get_phase("execute").max_turns == 12
    assert config.get_phase("summarize").allowed_tools == ["Skill"]
    assert config.get_phase("summarize").max_turns == 2


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
        root=Path("/tmp/herald"),
        data_dir=Path("/tmp/herald/data"),
        working_dir=Path("/tmp/herald-working"),
        logs_dir=Path("/tmp/herald/logs"),
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


def test_draft_pes_handle_phase_response_updates_solution() -> None:
    """`DraftPES` 能以最小方式更新 phase 结果。"""

    pes = DraftPES(
        config=_build_config(),
        llm=DummyLLM(),
        prompt_manager=DummyPromptManager(),
    )
    solution = pes.create_solution(generation=0)
    result = asyncio.run(
        pes.handle_phase_response(
            phase="plan",
            solution=solution,
            response=DummyResponse(result="ok", turns=[]),
            parent_solution=None,
        )
    )

    assert result["phase"] == "plan"
    assert solution.plan_summary == "ok"


def test_draft_pes_run_with_real_prompt_manager(tmp_path: Path) -> None:
    """`DraftPES` 能结合真实 PromptManager 走完三阶段。"""

    workspace = _build_workspace(tmp_path)
    llm = DummyLLM(
        responses=["ok", "执行完成", "ok"],
        execute_code=(
            "def solve() -> None:\n"
            "    pass\n"
            "\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    solve()\n"
        ),
    )
    pes = DraftPES(
        config=load_pes_config("config/pes/draft.yaml"),
        llm=llm,
        workspace=workspace,
        runtime_context=_build_runtime_context(str(workspace.root)),
        prompt_manager=_build_prompt_manager(),
    )

    solution = asyncio.run(
        pes.run(
            agent_profile=AgentProfile(
                name="draft-agent",
                display_name="Draft Agent",
                prompt_text="",
            ),
            generation=0,
        )
    )

    assert solution.status == "completed"
    assert solution.plan_summary == "ok"
    assert "python solution.py" in solution.execute_summary
    assert "exit_code=0" in solution.execute_summary
    assert solution.summarize_insight == "ok"
    assert set(solution.phase_outputs.keys()) == {"plan", "execute", "summarize"}
    assert solution.solution_file_path == str(workspace.working_dir / "solution.py")
    assert solution.submission_file_path == str(
        workspace.working_dir / "submission.csv"
    )
    assert workspace.read_working_solution().startswith("def solve()")
    assert len(llm.calls) == 3
    assert "draft_plan" in str(llm.calls[0]["prompt"])
    assert "draft_execute" in str(llm.calls[1]["prompt"])
    assert "draft_summarize" in str(llm.calls[2]["prompt"])
    assert "训练集 100 行" in str(llm.calls[0]["prompt"])
    assert "训练集 100 行" in str(llm.calls[1]["prompt"])
    assert llm.calls[1]["cwd"] == str(workspace.working_dir)
    assert llm.calls[1]["env"] == {"HERALD_DB_PATH": str(workspace.db_path)}


# ── L2 知识写入测试 ──────────────────────────────────────────


SUMMARIZE_INSIGHT_SAMPLE = """\
# 摘要
采用 LightGBM 模型进行二分类，AUC 达到 0.91。特征交叉是主要提升手段。

# 策略选择
使用 LightGBM + 5 折交叉验证。

# 执行结果
AUC=0.91，耗时 10ms。

# 关键发现
特征交叉对 AUC 提升约 0.02。

# 建议方向
下次尝试 XGBoost。
"""


def _build_pes_with_db(
    tmp_path: Path,
    *,
    summarize_response: str = SUMMARIZE_INSIGHT_SAMPLE,
) -> tuple[DraftPES, DummyWorkspace, HeraldDB]:
    """构造带真实 DB 的 DraftPES，用于 L2 写入测试。"""

    workspace = _build_workspace(tmp_path)
    db = HeraldDB(str(workspace.db_path))
    llm = DummyLLM(
        responses=["plan ok", "execute ok", summarize_response],
        execute_code=(
            "def solve() -> None:\n"
            "    pass\n"
            "\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    solve()\n"
        ),
    )
    pes = DraftPES(
        config=load_pes_config("config/pes/draft.yaml"),
        llm=llm,
        db=db,
        workspace=workspace,
        runtime_context=_build_runtime_context(str(workspace.root)),
        prompt_manager=_build_prompt_manager(),
    )
    return pes, workspace, db


def test_write_l2_success_case(tmp_path: Path) -> None:
    """summarize 完成后 l2_insights 有条目，evidence_type='support'。"""

    pes, workspace, db = _build_pes_with_db(tmp_path)

    solution = asyncio.run(
        pes.run(
            agent_profile=AgentProfile(
                name="draft-agent",
                display_name="Draft Agent",
                prompt_text="",
            ),
            generation=0,
        )
    )

    assert solution.status == "completed"

    # 验证 l2_insights 表有记录
    insights = db.get_l2_insights(slot="strategy")
    assert len(insights) >= 1

    insight = insights[0]
    assert insight["slot"] == "strategy"
    assert insight["task_type"] == "tabular_ml"
    assert "LightGBM" in insight["pattern"]
    assert insight["status"] == "active"

    # 验证 l2_evidence 表有记录
    evidence = db.get_l2_evidence(insight["id"])
    assert len(evidence) >= 1
    assert evidence[0]["evidence_type"] == "support"
    assert evidence[0]["solution_id"] == solution.id

    db.close()


def test_write_l2_failure_contradict(tmp_path: Path) -> None:
    """运行失败时 l2_evidence 中 evidence_type='contradict'。"""

    workspace = _build_workspace(tmp_path)
    db = HeraldDB(str(workspace.db_path))

    # 构造一个 execute 阶段运行失败的 DummyLLM（exit_code=1）
    llm = DummyLLM(responses=["plan ok", "execute ok", "summarize ok"])
    # 手动写一个 solution.py，但让 tool trace 返回 exit_code=1
    pes = DraftPES(
        config=load_pes_config("config/pes/draft.yaml"),
        llm=llm,
        db=db,
        workspace=workspace,
        runtime_context=_build_runtime_context(str(workspace.root)),
        prompt_manager=_build_prompt_manager(),
    )

    # 手动模拟失败路径
    solution = pes.create_solution(generation=0)
    solution.execute_summary = "solution.py 首次运行失败"
    solution.metadata["_l2_failure_context"] = {
        "reason": "runtime_error",
        "stderr_tail": "Traceback: ZeroDivisionError",
        "stdout_tail": "training started...",
    }
    solution.status = "failed"

    # 直接调用 _write_l2_knowledge
    pes._write_l2_knowledge(solution)

    insights = db.get_l2_insights(slot="strategy")
    assert len(insights) >= 1

    insight = insights[0]
    assert "FAILED" in insight["pattern"]
    assert "runtime_error" in insight["pattern"]

    evidence = db.get_l2_evidence(insight["id"])
    assert len(evidence) >= 1
    assert evidence[0]["evidence_type"] == "contradict"
    assert evidence[0]["solution_id"] == solution.id

    db.close()


def test_write_l2_db_error_no_block(tmp_path: Path) -> None:
    """L2 写入异常不影响 solution 状态和事件。"""

    class BrokenDB:
        """upsert_l2_insight 总是抛异常的 DB 桩。"""

        def upsert_l2_insight(self, **kwargs: object) -> int:
            raise RuntimeError("DB 写入失败")

    workspace = _build_workspace(tmp_path)
    llm = DummyLLM(
        responses=["plan ok", "execute ok", SUMMARIZE_INSIGHT_SAMPLE],
        execute_code=(
            "def solve() -> None:\n"
            "    pass\n"
            "\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    solve()\n"
        ),
    )
    pes = DraftPES(
        config=load_pes_config("config/pes/draft.yaml"),
        llm=llm,
        db=BrokenDB(),
        workspace=workspace,
        runtime_context=_build_runtime_context(str(workspace.root)),
        prompt_manager=_build_prompt_manager(),
    )

    # 应该正常完成，不因 L2 写入失败而崩溃
    solution = asyncio.run(
        pes.run(
            agent_profile=AgentProfile(
                name="draft-agent",
                display_name="Draft Agent",
                prompt_text="",
            ),
            generation=0,
        )
    )

    assert solution.status == "completed"


def test_no_l2_for_missing_solution_file(tmp_path: Path) -> None:
    """场景 1（solution.py 未写出）不写 L2。"""

    workspace = _build_workspace(tmp_path)
    db = HeraldDB(str(workspace.db_path))

    # DummyLLM 不写 solution.py（没有 execute_code）
    llm = DummyLLM(responses=["plan ok", "execute ok", "summarize ok"])
    pes = DraftPES(
        config=load_pes_config("config/pes/draft.yaml"),
        llm=llm,
        db=db,
        workspace=workspace,
        runtime_context=_build_runtime_context(str(workspace.root)),
        prompt_manager=_build_prompt_manager(),
    )

    with pytest.raises(ValueError, match="未写出代码文件"):
        asyncio.run(
            pes.run(
                agent_profile=AgentProfile(
                    name="draft-agent",
                    display_name="Draft Agent",
                    prompt_text="",
                ),
                generation=0,
            )
        )

    # 验证 l2_insights 表无记录
    insights = db.get_l2_insights(slot="strategy")
    assert len(insights) == 0

    db.close()
