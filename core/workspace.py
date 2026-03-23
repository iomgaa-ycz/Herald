"""Herald 工作空间管理。

职责：
1. 创建软链接映射竞赛数据
2. 管理 solution.py / submission.csv 的版本
3. 集中存放日志和最佳结果
4. 持久化 SQLite 数据库

目录结构：
workspace/
├── data/           # 软链接到竞赛数据
├── working/        # 当前工作目录（Agent 在此写 solution.py）
├── history/        # 所有版本
│   ├── gen0_abc123/
│   │   ├── solution.py
│   │   └── submission.csv
│   └── gen1_def456/
│       ├── solution.py
│       └── submission.csv
├── logs/           # 运行日志
├── best/           # 最佳结果
│   ├── solution.py
│   └── submission.csv
└── database/
    └── herald.db
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


class Workspace:
    """Herald 工作空间。"""

    def __init__(self, root: str | Path) -> None:
        """初始化工作空间。

        Args:
            root: 工作空间根目录
        """
        self.root = Path(root).expanduser().resolve()
        self.data_dir = self.root / "data"
        self.working_dir = self.root / "working"
        self.history_dir = self.root / "history"
        self.logs_dir = self.root / "logs"
        self.best_dir = self.root / "best"
        self.database_dir = self.root / "database"
        self.db_path = self.database_dir / "herald.db"

    def create(self, competition_dir: str | Path) -> "Workspace":
        """创建工作空间目录结构并链接数据。

        Args:
            competition_dir: 竞赛数据目录

        Returns:
            self（链式调用）
        """
        for d in (
            self.data_dir,
            self.working_dir,
            self.history_dir,
            self.logs_dir,
            self.best_dir,
            self.database_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

        self._link_competition_data(competition_dir)
        return self

    def _link_competition_data(self, competition_dir: Path) -> None:
        """软链接竞赛数据到 data/ 目录。"""
        src = Path(competition_dir).expanduser().resolve()
        for item in src.iterdir():
            dst = self.data_dir / item.name
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            dst.symlink_to(item)

    def save_version(
        self,
        code: str,
        submission: str,
        generation: int,
        solution_id: str,
    ) -> Path:
        """保存一个完整版本（solution + submission）。

        Args:
            code: solution.py 内容
            submission: submission.csv 内容
            generation: 代数
            solution_id: Solution ID

        Returns:
            版本目录路径
        """
        version_dir = self.history_dir / f"gen{generation}_{solution_id[:8]}"
        version_dir.mkdir(parents=True, exist_ok=True)

        (version_dir / "solution.py").write_text(code, encoding="utf-8")
        (version_dir / "submission.csv").write_text(submission, encoding="utf-8")
        return version_dir

    def promote_best(
        self,
        version_dir: Path,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """原子化更新最佳结果。

        Args:
            version_dir: 版本目录（包含 solution.py 和 submission.csv）
            metadata: 可选的元数据（fitness 等）
        """
        src_solution = version_dir / "solution.py"
        src_submission = version_dir / "submission.csv"

        tmp_solution = self.best_dir / ".solution.py.tmp"
        tmp_submission = self.best_dir / ".submission.csv.tmp"

        shutil.copy2(src_solution, tmp_solution)
        shutil.copy2(src_submission, tmp_submission)

        tmp_solution.replace(self.best_dir / "solution.py")
        tmp_submission.replace(self.best_dir / "submission.csv")

        if metadata:
            import json

            meta_tmp = self.best_dir / ".metadata.json.tmp"
            meta_tmp.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            meta_tmp.replace(self.best_dir / "metadata.json")

    def get_working_solution_path(self) -> Path:
        """获取当前工作 solution.py 路径。"""
        return self.working_dir / "solution.py"

    def get_log_path(self, name: str) -> Path:
        """获取日志文件路径。

        Args:
            name: 日志名称（不含扩展名）

        Returns:
            日志文件路径
        """
        return self.logs_dir / f"{name}.log"

    def summary(self) -> dict[str, str]:
        """返回工作空间路径摘要（可注入 Prompt）。"""
        return {
            "workspace_root": str(self.root),
            "data_dir": str(self.data_dir),
            "working_dir": str(self.working_dir),
            "history_dir": str(self.history_dir),
            "logs_dir": str(self.logs_dir),
            "db_path": str(self.db_path),
        }
