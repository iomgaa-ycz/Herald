"""FeatureExtract project skill 链路集成测试。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from core.agent.profile import AgentProfile
from core.events.bus import EventBus
from core.pes.config import load_pes_config
from core.pes.feature_extract import FeatureExtractPES
from core.pes.registry import PESRegistry
from core.workspace import Workspace


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


class RecordingLLM:
    """记录调用参数并按顺序返回预设响应。"""

    def __init__(self, responses: list[str]) -> None:
        """初始化测试桩。"""

        self.responses = responses
        self.calls: list[dict[str, object]] = []
        self._index = 0

    async def execute_task(self, prompt: str, **kwargs: object) -> DummyResponse:
        """记录调用并返回当前响应。"""

        self.calls.append({"prompt": prompt, **kwargs})
        result = self.responses[self._index]
        self._index += 1
        return DummyResponse(result=result, turns=[])


class DummyPromptManager:
    """返回固定 prompt 的测试桩。"""

    def build_prompt(
        self,
        operation: str,
        phase: str,
        context: dict[str, object],
    ) -> str:
        """返回固定 prompt。"""

        del operation, context
        return f"prompt:{phase}"


def _build_competition_dir(project_root: Path) -> Path:
    """构造最小竞赛目录。"""

    competition_dir = project_root / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text(
        "id,feature,target\n1,0.1,0\n2,0.2,1\n",
        encoding="utf-8",
    )
    (competition_dir / "test.csv").write_text(
        "id,feature\n3,0.3\n",
        encoding="utf-8",
    )
    (competition_dir / "sample_submission.csv").write_text(
        "id,target\n3,0\n",
        encoding="utf-8",
    )
    (competition_dir / "description.md").write_text(
        "# Demo Competition\n\nmetric: auc\n",
        encoding="utf-8",
    )
    return competition_dir


def _build_project_skills(project_root: Path) -> Path:
    """构造最小 project skill。"""

    skills_dir = project_root / ".claude" / "skills" / "demo-skill"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "SKILL.md").write_text(
        "# demo skill\n\nUse this skill for preview.\n",
        encoding="utf-8",
    )
    return skills_dir.parent


def _make_execute_response(data_profile: str) -> str:
    """构造 execute 阶段结构化输出。"""

    payload = {
        "task_spec": {
            "task_type": "tabular",
            "competition_name": "demo-competition",
            "objective": "predict target",
            "metric_name": "auc",
            "metric_direction": "maximize",
        },
        "data_profile": data_profile,
        "genome_template": "tabular",
    }
    return f"分析完成。\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"


def _build_agent() -> AgentProfile:
    """构造最小 agent profile。"""

    return AgentProfile(
        name="kaggle_master",
        display_name="Kaggle Master",
        prompt_text="你是数据竞赛专家。",
    )


def test_feature_extract_execute_sees_visible_project_skills(tmp_path: Path) -> None:
    """execute 阶段在 working 目录下能看到 project skills。"""

    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    competition_dir = _build_competition_dir(project_root)
    project_skills_dir = _build_project_skills(project_root)

    workspace = Workspace(project_root / "workspace")
    workspace.create(competition_dir)
    visible_skills_dir = workspace.expose_project_skills(project_root)

    llm = RecordingLLM(
        responses=[
            "先看 description 与数据文件。",
            _make_execute_response("训练集 2 行，1 个数值特征，无缺失值。"),
            "总结：这是标准 tabular 任务。",
        ]
    )
    pes = FeatureExtractPES(
        config=load_pes_config("config/pes/feature_extract.yaml"),
        llm=llm,
        workspace=workspace,
        runtime_context={
            "competition_dir": str(competition_dir),
            "run_id": "run-001",
        },
        prompt_manager=DummyPromptManager(),
    )

    solution = asyncio.run(pes.run(agent_profile=_build_agent()))

    execute_call = llm.calls[1]

    assert solution.status == "completed"
    assert visible_skills_dir is not None
    assert visible_skills_dir.is_symlink()
    assert visible_skills_dir.resolve() == project_skills_dir.resolve()
    assert execute_call["cwd"] == str(workspace.working_dir)
    assert "Skill" in execute_call["allowed_tools"]
    assert (
        workspace.working_dir / ".claude" / "skills" / "demo-skill" / "SKILL.md"
    ).exists()
    assert workspace.summary()["project_skills_dir"] == str(visible_skills_dir)


def test_feature_extract_execute_skips_missing_project_skills(tmp_path: Path) -> None:
    """缺少 project skills 时 execute 链路仍可继续。"""

    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    competition_dir = _build_competition_dir(project_root)

    workspace = Workspace(project_root / "workspace")
    workspace.create(competition_dir)
    visible_skills_dir = workspace.expose_project_skills(project_root)

    llm = RecordingLLM(
        responses=[
            "先看 description 与数据文件。",
            _make_execute_response("训练集 2 行，1 个数值特征，无缺失值。"),
            "总结：这是标准 tabular 任务。",
        ]
    )
    pes = FeatureExtractPES(
        config=load_pes_config("config/pes/feature_extract.yaml"),
        llm=llm,
        workspace=workspace,
        runtime_context={
            "competition_dir": str(competition_dir),
            "run_id": "run-001",
        },
        prompt_manager=DummyPromptManager(),
    )

    solution = asyncio.run(pes.run(agent_profile=_build_agent()))

    execute_call = llm.calls[1]

    assert solution.status == "completed"
    assert visible_skills_dir is None
    assert execute_call["cwd"] == str(workspace.working_dir)
    assert "Skill" in execute_call["allowed_tools"]
    assert not (workspace.working_dir / ".claude" / "skills").exists()
    assert workspace.summary()["project_skills_dir"] == ""
