"""Workspace project skill 暴露测试。"""

from __future__ import annotations

from pathlib import Path

from core.workspace import Workspace


def _build_competition_dir(tmp_path: Path) -> Path:
    """构造最小竞赛目录。"""

    competition_dir = tmp_path / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text("id,target\n1,0\n", encoding="utf-8")
    return competition_dir


def _build_project_skills(project_root: Path) -> Path:
    """构造项目级 `.claude/skills/`。"""

    skills_dir = project_root / ".claude" / "skills" / "demo-skill"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "SKILL.md").write_text("# demo skill\n", encoding="utf-8")
    return skills_dir.parent


def test_expose_project_skills_creates_symlink(tmp_path: Path) -> None:
    """存在 project skills 时会在 working 目录创建软链接。"""

    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    competition_dir = _build_competition_dir(tmp_path)
    expected_target = _build_project_skills(project_root)

    workspace = Workspace(project_root / "workspace")
    workspace.create(competition_dir)

    skills_link = workspace.expose_project_skills(project_root)

    assert skills_link is not None
    assert skills_link.is_symlink()
    assert skills_link.resolve() == expected_target.resolve()
    assert (skills_link / "demo-skill" / "SKILL.md").exists()


def test_expose_project_skills_skips_when_missing(tmp_path: Path) -> None:
    """缺少 project skills 时安全跳过。"""

    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    competition_dir = _build_competition_dir(tmp_path)

    workspace = Workspace(project_root / "workspace")
    workspace.create(competition_dir)

    skills_link = workspace.expose_project_skills(project_root)

    assert skills_link is None
    assert not workspace.visible_project_skills_dir.exists()


def test_summary_exposes_project_skills_dir(tmp_path: Path) -> None:
    """工作空间摘要会暴露当前可见的 project skills 路径。"""

    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    competition_dir = _build_competition_dir(tmp_path)
    _build_project_skills(project_root)

    workspace = Workspace(project_root / "workspace")
    workspace.create(competition_dir)
    workspace.expose_project_skills(project_root)

    summary = workspace.summary()

    assert summary["project_skills_dir"] == str(workspace.visible_project_skills_dir)
