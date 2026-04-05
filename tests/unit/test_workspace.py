"""Workspace 版本归档单元测试。"""

from __future__ import annotations

from pathlib import Path

from core.workspace import Workspace


def _build_workspace(tmp_path: Path) -> Workspace:
    """构造最小工作空间。"""

    competition_dir = tmp_path / "competition"
    public_dir = competition_dir / "prepared" / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "train.csv").write_text("id,target\n1,0\n", encoding="utf-8")

    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)
    return workspace


def test_save_version_creates_directory(tmp_path: Path) -> None:
    """save_version 会创建版本目录并写入真实工件。"""

    workspace = _build_workspace(tmp_path)

    version_dir = workspace.save_version(
        code="def solve() -> None:\n    pass\n",
        submission="id,target\n1,0.9\n",
        generation=2,
        solution_id="solution-abcdef12",
    )

    assert version_dir.exists()
    assert version_dir.name == "gen2_solution"
    assert (version_dir / "solution.py").read_text(encoding="utf-8").startswith(
        "def solve()"
    )
    assert (
        (version_dir / "submission.csv").read_text(encoding="utf-8")
        == "id,target\n1,0.9\n"
    )


def test_promote_best_updates_best_dir(tmp_path: Path) -> None:
    """promote_best 会同步更新 best 目录与 metadata。"""

    workspace = _build_workspace(tmp_path)
    version_dir = workspace.save_version(
        code="print('best')\n",
        submission="id,target\n1,0.7\n",
        generation=0,
        solution_id="solution-best-001",
    )

    workspace.promote_best(
        version_dir=version_dir,
        metadata={
            "solution_id": "solution-best-001",
            "generation": 0,
            "fitness": 0.7,
        },
    )

    assert (workspace.best_dir / "solution.py").read_text(encoding="utf-8") == "print('best')\n"
    assert (
        (workspace.best_dir / "submission.csv").read_text(encoding="utf-8")
        == "id,target\n1,0.7\n"
    )
    assert workspace.read_best_metadata() == {
        "solution_id": "solution-best-001",
        "generation": 0,
        "fitness": 0.7,
    }


def test_save_version_archives_and_clears_run_log(tmp_path: Path) -> None:
    """save_version 应将 run.log 拷贝到 history 并清空 working 下的 run.log。"""

    workspace = _build_workspace(tmp_path)

    # 模拟 execute 阶段写入 run.log
    workspace.run_log_path.write_text(
        '{"metric_name": "auc", "metric_value": 0.95}\n',
        encoding="utf-8",
    )

    version_dir = workspace.save_version(
        code="print('v1')\n",
        submission="id,target\n1,0.5\n",
        generation=1,
        solution_id="sol-runlog-test",
    )

    # run.log 应被归档到 history
    archived_log = version_dir / "run.log"
    assert archived_log.exists()
    assert "metric_value" in archived_log.read_text(encoding="utf-8")

    # working/run.log 应被清空
    assert workspace.run_log_path.exists()
    assert workspace.run_log_path.read_text(encoding="utf-8") == ""


def test_save_version_skips_run_log_when_absent(tmp_path: Path) -> None:
    """run.log 不存在时 save_version 不应报错。"""

    workspace = _build_workspace(tmp_path)

    # 确保 run.log 不存在
    if workspace.run_log_path.exists():
        workspace.run_log_path.unlink()

    version_dir = workspace.save_version(
        code="print('v2')\n",
        submission="id,target\n1,0.6\n",
        generation=2,
        solution_id="sol-nolog-test",
    )

    assert version_dir.exists()
    assert not (version_dir / "run.log").exists()


def test_read_best_metadata_returns_none_when_absent(tmp_path: Path) -> None:
    """best metadata 不存在时返回 None。"""

    workspace = _build_workspace(tmp_path)

    assert workspace.read_best_metadata() is None
