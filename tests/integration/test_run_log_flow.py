"""run 级人类可读日志文件集成测试。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.agent.registry import AgentRegistry
from core.events import EventBus, setup_task_dispatcher
from core.pes.config import load_pes_config
from core.pes.draft import DraftPES
from core.pes.registry import PESRegistry
from core.prompts.manager import PromptManager
from core.workspace import Workspace


def setup_function() -> None:
    """每个测试前重置全局单例。"""

    EventBus.reset()
    AgentRegistry.reset()
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


def _build_prompt_manager() -> PromptManager:
    """构造指向仓库内配置目录的 PromptManager。"""

    base_dir = Path(__file__).resolve().parents[2] / "config" / "prompts"
    return PromptManager(
        template_dir=base_dir / "templates",
        fragments_dir=base_dir / "fragments",
        spec_path=base_dir / "prompt_spec.yaml",
    )


def _build_competition_dir(tmp_path: Path) -> Path:
    """构造最小竞赛目录（含 sample_submission.csv）。"""

    competition_dir = tmp_path / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text("id,target\n1,0\n", encoding="utf-8")
    (competition_dir / "sample_submission.csv").write_text(
        "id,target\n3,0.5\n", encoding="utf-8"
    )
    return competition_dir


def test_prompt_assembles_run_log_path(tmp_path: Path) -> None:
    """DraftPES 构建的 prompt context 包含 run_log_path。"""

    competition_dir = _build_competition_dir(tmp_path)
    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)

    summary = workspace.summary()

    assert "run_log_path" in summary
    assert summary["run_log_path"] == str(workspace.run_log_path)

    # 验证 prompt 模板渲染后包含 run_log_path
    pm = _build_prompt_manager()
    context = {
        "solution": {"id": "sol-1", "status": "running", "plan_summary": "test", "genes": {}},
        "task_spec": {
            "task_type": "tabular",
            "competition_name": "test-comp",
            "objective": "maximize auc",
            "metric_name": "auc",
            "metric_direction": "max",
        },
        "workspace": summary,
        "allowed_tools": ["Bash"],
    }
    prompt = pm.build_prompt(operation="draft", phase="execute", context=context)

    assert str(workspace.run_log_path) in prompt
    assert "tee" in prompt
    assert "pipefail" in prompt
