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


def _build_skills_source(tmp_path: Path) -> Path:
    """构造 skills 源目录。"""

    skills_dir = tmp_path / "skills" / "demo-skill"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "SKILL.md").write_text("# demo skill\n", encoding="utf-8")
    return skills_dir.parent


def test_expose_project_skills_creates_symlink(tmp_path: Path) -> None:
    """存在 skills 源目录时会在 working 目录创建软链接。"""

    competition_dir = _build_competition_dir(tmp_path)
    skills_source = _build_skills_source(tmp_path)

    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)

    skills_link = workspace.expose_project_skills(skills_source)

    assert skills_link is not None
    assert skills_link.is_symlink()
    assert skills_link.resolve() == skills_source.resolve()
    assert (skills_link / "demo-skill" / "SKILL.md").exists()


def test_expose_project_skills_skips_when_missing(tmp_path: Path) -> None:
    """skills 源目录不存在时安全跳过。"""

    competition_dir = _build_competition_dir(tmp_path)

    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)

    skills_link = workspace.expose_project_skills(tmp_path / "nonexistent")

    assert skills_link is None
    assert not workspace.visible_project_skills_dir.exists()


def test_summary_exposes_project_skills_dir(tmp_path: Path) -> None:
    """工作空间摘要会暴露当前可见的 project skills 路径。"""

    competition_dir = _build_competition_dir(tmp_path)
    skills_source = _build_skills_source(tmp_path)

    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)
    workspace.expose_project_skills(skills_source)

    summary = workspace.summary()

    assert summary["project_skills_dir"] == str(workspace.visible_project_skills_dir)
