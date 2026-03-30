"""run 级人类可读日志文件测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.prompts.manager import PromptManager
from core.workspace import Workspace


def _build_competition_dir(tmp_path: Path) -> Path:
    """构造最小竞赛目录。"""

    competition_dir = tmp_path / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text("id,target\n1,0\n", encoding="utf-8")
    return competition_dir


def _build_prompt_manager() -> PromptManager:
    """构造指向仓库内配置目录的 PromptManager。"""

    base_dir = Path(__file__).resolve().parents[2] / "config" / "prompts"
    return PromptManager(
        template_dir=base_dir / "templates",
        fragments_dir=base_dir / "fragments",
        spec_path=base_dir / "prompt_spec.yaml",
    )


def _build_draft_execute_context(workspace: Workspace) -> dict[str, Any]:
    """构造 draft_execute 模板渲染所需的最小上下文。"""

    return {
        "solution": {
            "id": "solution-1",
            "status": "running",
            "plan_summary": "使用最小 baseline 方案。",
            "genes": {},
        },
        "task_spec": {
            "task_type": "tabular",
            "competition_name": "demo",
            "objective": "maximize auc",
            "metric_name": "auc",
            "metric_direction": "max",
        },
        "workspace": workspace.summary(),
        "allowed_tools": ["Bash", "Read"],
    }


def test_run_log_path_property(tmp_path: Path) -> None:
    """Workspace.run_log_path 指向 working_dir/run.log。"""

    workspace = Workspace(tmp_path / "workspace")
    assert workspace.run_log_path == workspace.working_dir / "run.log"


def test_workspace_summary_contains_run_log_path(tmp_path: Path) -> None:
    """summary() 返回含 run_log_path 键。"""

    competition_dir = _build_competition_dir(tmp_path)
    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)

    summary = workspace.summary()

    assert "run_log_path" in summary
    assert summary["run_log_path"] == str(workspace.run_log_path)


def test_draft_execute_prompt_contains_tee_and_run_log(tmp_path: Path) -> None:
    """draft_execute prompt 包含 tee 指令和 run.log 路径。"""

    competition_dir = _build_competition_dir(tmp_path)
    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)

    pm = _build_prompt_manager()
    context = _build_draft_execute_context(workspace)
    prompt = pm.build_prompt(operation="draft", phase="execute", context=context)

    assert "tee" in prompt
    assert "run.log" in prompt
    assert str(workspace.run_log_path) in prompt


def test_draft_execute_prompt_contains_pipefail(tmp_path: Path) -> None:
    """draft_execute prompt 包含 set -o pipefail 保证 exit_code 正确传播。"""

    competition_dir = _build_competition_dir(tmp_path)
    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)

    pm = _build_prompt_manager()
    context = _build_draft_execute_context(workspace)
    prompt = pm.build_prompt(operation="draft", phase="execute", context=context)

    assert "set -o pipefail" in prompt
