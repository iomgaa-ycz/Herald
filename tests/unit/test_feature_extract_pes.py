"""FeatureExtractPES 单元测试。"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from core.agent.profile import AgentProfile
from core.events.bus import EventBus
from core.events.types import TaskCompleteEvent, TaskExecuteEvent
from core.pes.config import PESConfig, PhaseConfig, load_pes_config
from core.pes.feature_extract import FeatureExtractPES
from core.pes.registry import PESRegistry
from core.pes.schema import TaskSpec
from core.prompts.manager import PromptManager


def setup_function() -> None:
    """每个测试前重置全局单例。"""
    EventBus.reset()
    PESRegistry.reset()


# ---------------------------------------------------------------------------
# 测试桩
# ---------------------------------------------------------------------------


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

    def __init__(self, responses: list[str] | None = None) -> None:
        """初始化测试桩。

        Args:
            responses: 按顺序返回的响应文本列表，默认全部返回 "ok"
        """
        self.calls: list[dict[str, object]] = []
        self._responses = responses or []
        self._call_index = 0

    async def execute_task(self, prompt: str, **kwargs: object) -> DummyResponse:
        """记录调用并返回固定响应。"""
        self.calls.append({"prompt": prompt, **kwargs})
        if self._call_index < len(self._responses):
            result = self._responses[self._call_index]
        else:
            result = "ok"
        self._call_index += 1
        return DummyResponse(result=result, turns=[])


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


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _build_config() -> PESConfig:
    """构造 FeatureExtract 最小可运行配置。"""
    return PESConfig(
        name="feature_extract",
        operation="feature_extract",
        solution_file_name="data_profile.md",
        submission_file_name=None,
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
                tool_names=[],
                max_retries=1,
                allowed_tools=["Bash", "Read", "Glob", "Grep", "Skill"],
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

    return DummyWorkspace(
        root=root,
        data_dir=data_dir,
        working_dir=working_dir,
        logs_dir=logs_dir,
        db_path=db_path,
    )


def _build_prompt_manager() -> PromptManager:
    """构造指向仓库配置目录的真实 PromptManager。"""
    base_dir = Path(__file__).resolve().parents[2] / "config" / "prompts"
    return PromptManager(
        template_dir=base_dir / "templates",
        fragments_dir=base_dir / "fragments",
        spec_path=base_dir / "prompt_spec.yaml",
    )


def _make_execute_response_text(
    task_type: str = "tabular",
    competition_name: str = "test-comp",
    objective: str = "predict target",
    metric_name: str = "auc",
    metric_direction: str = "maximize",
    data_profile: str = "100 rows, 10 features",
    genome_template: str = "tabular",
) -> str:
    """构造包含 JSON code block 的 execute 阶段响应文本。"""
    payload = {
        "task_spec": {
            "task_type": task_type,
            "competition_name": competition_name,
            "objective": objective,
            "metric_name": metric_name,
            "metric_direction": metric_direction,
        },
        "data_profile": data_profile,
        "genome_template": genome_template,
    }
    return f"分析完成。\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"


def _make_execute_event(pes: FeatureExtractPES) -> TaskExecuteEvent:
    """构造最小 TaskExecuteEvent 以触发完成事件发射。"""

    return TaskExecuteEvent(
        task_name="feature_extract",
        target_pes_id=pes.instance_id,
        generation=0,
    )


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------


def test_feature_extract_yaml_config_loads() -> None:
    """feature_extract.yaml 可被正常加载。"""
    config = load_pes_config("config/pes/feature_extract.yaml")

    assert config.name == "feature_extract"
    assert config.operation == "feature_extract"
    assert config.solution_file_name == "data_profile.md"
    assert config.submission_file_name is None
    assert config.get_phase("execute").allowed_tools == [
        "Bash",
        "Read",
        "Glob",
        "Grep",
        "Skill",
    ]
    assert config.get_phase("execute").max_turns == 12
    assert config.get_phase("plan").max_turns == 3


def test_feature_extract_skill_contract_keeps_execute_phase_skill_enabled() -> None:
    """Task 14 落地后，execute phase 保留 Skill，源码目录完整。"""

    config = load_pes_config("config/pes/feature_extract.yaml")
    project_root = Path(__file__).resolve().parents[2]
    skill_source_dir = (
        project_root
        / "core"
        / "prompts"
        / "skills"
        / "feature-extract-data-preview"
    )

    assert config.get_phase("execute").allowed_tools is not None
    assert "Skill" in config.get_phase("execute").allowed_tools
    assert (skill_source_dir / "SKILL.md").exists()
    assert (
        skill_source_dir / "scripts" / "preview_support.py"
    ).exists()
    assert (
        skill_source_dir / "scripts" / "preview_competition.py"
    ).exists()
    assert (
        skill_source_dir / "scripts" / "preview_description.py"
    ).exists()
    assert (skill_source_dir / "scripts" / "preview_table.py").exists()
    assert (
        skill_source_dir / "scripts" / "preview_submission.py"
    ).exists()

    skill_text = (skill_source_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "preview_competition.py" in skill_text
    assert "preview_submission.py" in skill_text


def test_handle_plan_phase() -> None:
    """plan 阶段正确更新 plan_summary。"""
    pes = FeatureExtractPES(
        config=_build_config(),
        llm=DummyLLM(),
        prompt_manager=DummyPromptManager(),
    )
    solution = pes.create_solution(generation=0)

    result = asyncio.run(
        pes.handle_phase_response(
            phase="plan",
            solution=solution,
            response=DummyResponse(result="探索计划：先看数据", turns=[]),
            parent_solution=None,
        )
    )

    assert result["phase"] == "plan"
    assert solution.plan_summary == "探索计划：先看数据"


def test_handle_execute_phase_parses_json(tmp_path: Path) -> None:
    """execute 阶段能从 JSON code block 解析 TaskSpec。"""
    workspace = _build_workspace(tmp_path)
    pes = FeatureExtractPES(
        config=_build_config(),
        llm=DummyLLM(),
        workspace=workspace,
        prompt_manager=DummyPromptManager(),
    )
    solution = pes.create_solution(generation=0)

    response_text = _make_execute_response_text(
        task_type="tabular",
        metric_name="auc",
        metric_direction="maximize",
    )

    result = asyncio.run(
        pes.handle_phase_response(
            phase="execute",
            solution=solution,
            response=DummyResponse(result=response_text, turns=[]),
            parent_solution=None,
        )
    )

    assert result["task_spec"]["task_type"] == "tabular"
    assert result["task_spec"]["metric_name"] == "auc"
    assert result["genome_template"] == "tabular"
    assert result["schema"].task_type == "tabular"
    assert "def build_model(config: dict[str, object])" in result["template_content"]
    assert solution.metadata["genome_template"] == "tabular"
    assert solution.metadata["schema_task_type"] == "tabular"


def test_handle_execute_phase_persists_files(tmp_path: Path) -> None:
    """execute 阶段将 task_spec.json 和 data_profile.md 写入 workspace。"""
    workspace = _build_workspace(tmp_path)
    pes = FeatureExtractPES(
        config=_build_config(),
        llm=DummyLLM(),
        workspace=workspace,
        prompt_manager=DummyPromptManager(),
    )
    solution = pes.create_solution(generation=0)

    response_text = _make_execute_response_text(
        data_profile="训练集 100 行 10 列，无缺失值",
    )

    asyncio.run(
        pes.handle_phase_response(
            phase="execute",
            solution=solution,
            response=DummyResponse(result=response_text, turns=[]),
            parent_solution=None,
        )
    )

    # 检查 task_spec.json
    task_spec_path = workspace.working_dir / "task_spec.json"
    assert task_spec_path.exists()
    task_spec_data = json.loads(task_spec_path.read_text(encoding="utf-8"))
    assert task_spec_data["task_type"] == "tabular"

    # 检查 data_profile.md
    profile_path = workspace.working_dir / "data_profile.md"
    assert profile_path.exists()
    assert "训练集 100 行 10 列" in profile_path.read_text(encoding="utf-8")

    # 检查工件路径
    assert solution.workspace_dir == str(workspace.working_dir)
    assert solution.solution_file_path == str(workspace.working_dir / "data_profile.md")


def test_handle_summarize_emits_complete() -> None:
    """summarize 阶段设置 completed 状态并发出 TaskCompleteEvent。"""
    received_events: list[TaskCompleteEvent] = []

    def on_complete(event: TaskCompleteEvent) -> None:
        received_events.append(event)

    EventBus.get().on(TaskCompleteEvent.EVENT_TYPE, on_complete)

    pes = FeatureExtractPES(
        config=_build_config(),
        llm=DummyLLM(),
        prompt_manager=DummyPromptManager(),
    )
    pes.received_execute_event = _make_execute_event(pes)
    solution = pes.create_solution(generation=0)

    asyncio.run(
        pes.handle_phase_response(
            phase="summarize",
            solution=solution,
            response=DummyResponse(result="数据分析总结", turns=[]),
            parent_solution=None,
        )
    )

    assert solution.status == "completed"
    assert solution.summarize_insight == "数据分析总结"
    assert solution.finished_at is not None
    assert len(received_events) == 1
    assert received_events[0].task_name == "feature_extract"
    assert received_events[0].status == "completed"


def test_handle_summarize_emits_output_context(tmp_path: Path) -> None:
    """summarize 事件携带可供 DraftPES 消费的 output_context。"""

    received_events: list[TaskCompleteEvent] = []

    def on_complete(event: TaskCompleteEvent) -> None:
        received_events.append(event)

    EventBus.get().on(TaskCompleteEvent.EVENT_TYPE, on_complete)

    workspace = _build_workspace(tmp_path)
    pes = FeatureExtractPES(
        config=_build_config(),
        llm=DummyLLM(),
        workspace=workspace,
        prompt_manager=DummyPromptManager(),
    )
    pes.received_execute_event = _make_execute_event(pes)
    solution = pes.create_solution(generation=0)

    execute_response = _make_execute_response_text(
        data_profile="训练集 100 行 10 列，无缺失值",
    )
    asyncio.run(
        pes.handle_phase_response(
            phase="execute",
            solution=solution,
            response=DummyResponse(result=execute_response, turns=[]),
            parent_solution=None,
        )
    )
    asyncio.run(
        pes.handle_phase_response(
            phase="summarize",
            solution=solution,
            response=DummyResponse(result="数据分析总结", turns=[]),
            parent_solution=None,
        )
    )

    assert len(received_events) == 1
    output_context = received_events[0].output_context
    assert output_context["task_spec"]["task_type"] == "tabular"
    assert output_context["data_profile"] == "训练集 100 行 10 列，无缺失值"
    assert output_context["schema"].task_type == "tabular"
    assert (
        "def build_model(config: dict[str, object])"
        in output_context["template_content"]
    )


def test_run_full_cycle(tmp_path: Path) -> None:
    """FeatureExtractPES 结合真实 PromptManager 走完三阶段。"""
    execute_response = _make_execute_response_text()
    llm = DummyLLM(responses=["探索计划", execute_response, "总结报告"])
    workspace = _build_workspace(tmp_path)

    pes = FeatureExtractPES(
        config=load_pes_config("config/pes/feature_extract.yaml"),
        llm=llm,
        workspace=workspace,
        runtime_context={"competition_dir": "/tmp/test-comp"},
        prompt_manager=_build_prompt_manager(),
    )

    solution = asyncio.run(
        pes.run(
            agent_profile=AgentProfile(
                name="test-agent",
                display_name="Test Agent",
                prompt_text="",
            ),
            generation=0,
        )
    )

    assert solution.status == "completed"
    assert solution.plan_summary == "探索计划"
    assert solution.summarize_insight == "总结报告"
    assert set(solution.phase_outputs.keys()) == {"plan", "execute", "summarize"}
    assert len(llm.calls) == 3
    assert "feature_extract_plan" in str(llm.calls[0]["prompt"])
    assert "feature_extract_execute" in str(llm.calls[1]["prompt"])
    assert "feature_extract_summarize" in str(llm.calls[2]["prompt"])

    # 验证 workspace 工件
    assert (workspace.working_dir / "task_spec.json").exists()
    assert (workspace.working_dir / "data_profile.md").exists()

    # 验证 TaskSpec 可解析为 dataclass
    task_spec_data = json.loads(
        (workspace.working_dir / "task_spec.json").read_text(encoding="utf-8")
    )
    task_spec = TaskSpec(**task_spec_data)
    assert task_spec.task_type == "tabular"
    assert task_spec.metric_name == "auc"


def test_parse_structured_output_extracts_json() -> None:
    """_parse_structured_output 能正确提取 JSON code block。"""
    pes = FeatureExtractPES(
        config=_build_config(),
        llm=DummyLLM(),
        prompt_manager=DummyPromptManager(),
    )

    text = '先做分析\n\n```json\n{"task_spec": {"task_type": "tabular"}, "data_profile": "ok", "genome_template": "tabular"}\n```\n完成'

    result = pes._parse_structured_output(text)
    assert result["task_spec"]["task_type"] == "tabular"
    assert result["data_profile"] == "ok"
    assert result["genome_template"] == "tabular"


def test_parse_structured_output_takes_last_json_block() -> None:
    """存在多个 JSON block 时，取最后一个。"""
    pes = FeatureExtractPES(
        config=_build_config(),
        llm=DummyLLM(),
        prompt_manager=DummyPromptManager(),
    )

    text = '```json\n{"old": true}\n```\n\n最终结果：\n\n```json\n{"task_spec": {"task_type": "generic"}, "data_profile": "final", "genome_template": "generic"}\n```'

    result = pes._parse_structured_output(text)
    assert result["task_spec"]["task_type"] == "generic"
    assert result["data_profile"] == "final"


def test_parse_structured_output_fails_on_no_json() -> None:
    """无 JSON code block 时抛出 ValueError。"""
    pes = FeatureExtractPES(
        config=_build_config(),
        llm=DummyLLM(),
        prompt_manager=DummyPromptManager(),
    )

    with pytest.raises(ValueError, match="未找到 JSON code block"):
        pes._parse_structured_output("这是纯文本，没有 JSON")


def test_genome_template_defaults_to_generic(tmp_path: Path) -> None:
    """无效的 genome_template 降级为 'generic'。"""
    workspace = _build_workspace(tmp_path)
    pes = FeatureExtractPES(
        config=_build_config(),
        llm=DummyLLM(),
        workspace=workspace,
        prompt_manager=DummyPromptManager(),
    )
    solution = pes.create_solution(generation=0)

    response_text = _make_execute_response_text(genome_template="invalid_type")

    asyncio.run(
        pes.handle_phase_response(
            phase="execute",
            solution=solution,
            response=DummyResponse(result=response_text, turns=[]),
            parent_solution=None,
        )
    )

    assert solution.metadata["genome_template"] == "generic"


# ---------------------------------------------------------------------------
# 回放资产辅助函数
# ---------------------------------------------------------------------------

REPLAY_DIR = Path(__file__).resolve().parents[1] / "cases" / "replays"
MANIFEST_DIR = Path(__file__).resolve().parents[1] / "cases" / "competitions"

# MLE-Bench 数据根目录（可通过环境变量覆盖）
_TEST_DATA_ROOT = Path(
    os.environ.get("HERALD_TEST_DATA_ROOT", "~/.cache/mle-bench/data")
).expanduser()


def _load_replay(case_name: str) -> dict[str, str | dict]:
    """加载回放用例的所有文件内容。

    Args:
        case_name: 回放用例目录名

    Returns:
        包含 input / plan / execute_raw / summarize / expected 的字典
    """
    case_dir = REPLAY_DIR / case_name
    return {
        "input": json.loads((case_dir / "input.json").read_text(encoding="utf-8")),
        "plan": (case_dir / "plan.txt").read_text(encoding="utf-8"),
        "execute_raw": (case_dir / "execute_raw.txt").read_text(encoding="utf-8"),
        "summarize": (case_dir / "summarize.txt").read_text(encoding="utf-8"),
        "expected": json.loads(
            (case_dir / "expected.json").read_text(encoding="utf-8")
        ),
    }


# ---------------------------------------------------------------------------
# 基于真实回放的测试用例
# ---------------------------------------------------------------------------


def test_parse_real_tabular_replay() -> None:
    """从真实 LLM 回放的 execute_raw.txt 中解析出合法 TaskSpec。"""
    replay = _load_replay("feature_extract_tabular_success_v1")
    expected = replay["expected"]

    pes = FeatureExtractPES(
        config=_build_config(),
        llm=DummyLLM(),
        prompt_manager=DummyPromptManager(),
    )

    parsed = pes._parse_structured_output(replay["execute_raw"])

    # 校验与 expected.json 一致
    assert parsed["task_spec"] == expected["task_spec"]
    assert parsed["genome_template"] == expected["genome_template"]
    assert parsed["data_profile"] == expected["data_profile"]

    # 校验 TaskSpec dataclass 可构造
    task_spec = TaskSpec(**parsed["task_spec"])
    assert task_spec.task_type == "tabular"
    assert task_spec.metric_name == "auc"
    assert task_spec.metric_direction == "maximize"


def test_execute_phase_with_real_replay(tmp_path: Path) -> None:
    """用真实回放的 execute 输出验证 handle_phase_response 和文件落盘。"""
    replay = _load_replay("feature_extract_tabular_success_v1")
    expected = replay["expected"]

    workspace = _build_workspace(tmp_path)
    pes = FeatureExtractPES(
        config=_build_config(),
        llm=DummyLLM(),
        workspace=workspace,
        prompt_manager=DummyPromptManager(),
    )
    solution = pes.create_solution(generation=0)

    result = asyncio.run(
        pes.handle_phase_response(
            phase="execute",
            solution=solution,
            response=DummyResponse(result=replay["execute_raw"], turns=[]),
            parent_solution=None,
        )
    )

    # 校验解析结果
    assert result["task_spec"] == expected["task_spec"]
    assert result["genome_template"] == expected["genome_template"]

    # 校验文件落盘
    task_spec_path = workspace.working_dir / "task_spec.json"
    assert task_spec_path.exists()
    task_spec_data = json.loads(task_spec_path.read_text(encoding="utf-8"))
    assert task_spec_data["task_type"] == "tabular"
    assert task_spec_data["metric_name"] == "auc"

    profile_path = workspace.working_dir / "data_profile.md"
    assert profile_path.exists()
    profile_text = profile_path.read_text(encoding="utf-8")
    assert len(profile_text) > 0

    # 校验 genome_template 合法
    assert solution.metadata["genome_template"] in ("tabular", "generic")


def test_full_cycle_with_real_replay(tmp_path: Path) -> None:
    """用真实回放走完 FeatureExtractPES 三阶段闭环。"""
    replay = _load_replay("feature_extract_tabular_success_v1")

    llm = DummyLLM(
        responses=[
            replay["plan"],
            replay["execute_raw"],
            replay["summarize"],
        ]
    )
    workspace = _build_workspace(tmp_path)

    pes = FeatureExtractPES(
        config=load_pes_config("config/pes/feature_extract.yaml"),
        llm=llm,
        workspace=workspace,
        runtime_context={"competition_dir": "/data/tabular-playground"},
        prompt_manager=_build_prompt_manager(),
    )

    solution = asyncio.run(
        pes.run(
            agent_profile=AgentProfile(
                name="test-agent",
                display_name="Test Agent",
                prompt_text="",
            ),
            generation=0,
        )
    )

    # 三阶段闭环
    assert solution.status == "completed"
    assert set(solution.phase_outputs.keys()) == {"plan", "execute", "summarize"}

    # workspace 工件
    assert (workspace.working_dir / "task_spec.json").exists()
    assert (workspace.working_dir / "data_profile.md").exists()

    # TaskSpec 可解析
    task_spec_data = json.loads(
        (workspace.working_dir / "task_spec.json").read_text(encoding="utf-8")
    )
    task_spec = TaskSpec(**task_spec_data)
    assert task_spec.task_type == "tabular"
    assert task_spec.metric_name == "auc"

    # genome_template 合法
    assert solution.metadata["genome_template"] in ("tabular", "generic")


def test_degraded_replay_handles_missing_metric(tmp_path: Path) -> None:
    """降级 case：metric 缺失时仍能正确解析。"""
    replay = _load_replay("feature_extract_degraded_v1")

    workspace = _build_workspace(tmp_path)
    pes = FeatureExtractPES(
        config=_build_config(),
        llm=DummyLLM(),
        workspace=workspace,
        prompt_manager=DummyPromptManager(),
    )
    solution = pes.create_solution(generation=0)

    result = asyncio.run(
        pes.handle_phase_response(
            phase="execute",
            solution=solution,
            response=DummyResponse(result=replay["execute_raw"], turns=[]),
            parent_solution=None,
        )
    )

    # metric_name 为空但解析成功
    assert result["task_spec"]["metric_name"] == ""
    assert result["task_spec"]["metric_direction"] == ""
    assert result["task_spec"]["task_type"] == "tabular"

    # TaskSpec dataclass 仍可构造
    task_spec = TaskSpec(**result["task_spec"])
    assert task_spec.metric_name == ""

    # 文件落盘
    assert (workspace.working_dir / "task_spec.json").exists()
    assert (workspace.working_dir / "data_profile.md").exists()

    # genome_template 合法
    assert solution.metadata["genome_template"] in ("tabular", "generic")


def test_competition_manifest_valid() -> None:
    """竞赛 manifest YAML 字段完整且数据目录存在。"""
    required_fields = {
        "competition_id",
        "task_type",
        "metric_name",
        "metric_direction",
        "relative_root",
        "required_public_files",
    }

    manifests = sorted(MANIFEST_DIR.glob("*.yaml"))
    assert len(manifests) >= 2, f"至少需要 2 个 manifest，找到 {len(manifests)}"

    for manifest_path in manifests:
        with open(manifest_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # 字段完整性
        missing = required_fields - set(data.keys())
        assert not missing, f"{manifest_path.name} 缺少字段: {missing}"

        # 数据目录存在性（仅在数据根目录可用时检查）
        data_dir = _TEST_DATA_ROOT / data["relative_root"]
        if _TEST_DATA_ROOT.exists():
            assert data_dir.exists(), f"{manifest_path.name}: 数据目录不存在 {data_dir}"
            for filename in data["required_public_files"]:
                assert (data_dir / filename).exists(), (
                    f"{manifest_path.name}: 文件不存在 {data_dir / filename}"
                )
