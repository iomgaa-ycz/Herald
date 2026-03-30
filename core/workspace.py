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

import json
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
        self.working_claude_dir = self.working_dir / ".claude"
        self.visible_project_skills_dir = self.working_claude_dir / "skills"
        self.history_dir = self.root / "history"
        self.logs_dir = self.root / "logs"
        self.best_dir = self.root / "best"
        self.database_dir = self.root / "database"
        self.db_path = self.database_dir / "herald.db"
        self.metadata_path = self.root / "metadata.json"
        self.run_log_path = self.working_dir / "run.log"

    def create(self, competition_dir: str | Path) -> Workspace:
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

    def expose_project_skills(self, skills_source_dir: str | Path) -> Path | None:
        """将 project skills 源目录暴露到 working 目录。

        Args:
            skills_source_dir: skills 源目录（如 ``core/prompts/skills``）

        Returns:
            ``working/.claude/skills`` 路径；若源目录不存在则返回 ``None``
        """

        source = Path(skills_source_dir).expanduser().resolve()
        if not source.exists():
            return None

        self.working_claude_dir.mkdir(parents=True, exist_ok=True)
        skills_link = self.visible_project_skills_dir
        if skills_link.is_symlink() and skills_link.resolve() == source:
            return skills_link

        if skills_link.is_symlink() or skills_link.is_file():
            skills_link.unlink()
        elif skills_link.exists():
            shutil.rmtree(skills_link)

        skills_link.symlink_to(source, target_is_directory=True)
        return skills_link

    def _link_competition_data(self, competition_dir: Path) -> None:
        """软链接竞赛数据到 data/ 目录。

        优先链接 prepared/public/ 中的内容（mle-bench 格式），
        若不存在则直接链接根目录（N1eBanG 格式）。
        """
        src = Path(competition_dir).expanduser().resolve()

        # 检查是否存在 prepared/public/ 子目录
        public_dir = src / "prepared" / "public"
        data_src = public_dir if public_dir.exists() else src

        for item in data_src.iterdir():
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
            meta_tmp = self.best_dir / ".metadata.json.tmp"
            meta_tmp.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            meta_tmp.replace(self.best_dir / "metadata.json")

    def read_best_metadata(self) -> dict[str, Any] | None:
        """读取 best/metadata.json。"""

        metadata_path = self.best_dir / "metadata.json"
        if not metadata_path.exists():
            return None
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def write_run_metadata(self, metadata: dict[str, Any]) -> Path:
        """写入 run 级 metadata.json。"""

        metadata_tmp_path = self.root / ".metadata.json.tmp"
        metadata_tmp_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        metadata_tmp_path.replace(self.metadata_path)
        return self.metadata_path

    def read_run_metadata(self) -> dict[str, Any] | None:
        """读取 run 级 metadata.json。"""

        if not self.metadata_path.exists():
            return None
        return json.loads(self.metadata_path.read_text(encoding="utf-8"))

    def update_run_finished_at(self, finished_at: str) -> None:
        """回写 run 级 metadata.json 的完成时间。"""

        metadata = self.read_run_metadata()
        if metadata is None:
            return

        metadata["finished_at"] = finished_at
        self.write_run_metadata(metadata)

    def get_working_solution_path(self) -> Path:
        """获取当前工作 solution.py 路径。"""
        return self.working_dir / "solution.py"

    def get_working_submission_path(self, file_name: str = "submission.csv") -> Path:
        """获取当前工作 submission.csv 路径。

        Args:
            file_name: 提交文件名

        Returns:
            提交工件路径
        """

        return self.working_dir / file_name

    def get_working_file_path(self, file_name: str) -> Path:
        """获取 working/ 目录下指定文件路径。

        Args:
            file_name: 工件文件名

        Returns:
            工件路径
        """

        return self.working_dir / file_name

    def read_working_text(self, file_name: str) -> str | None:
        """读取 working/ 下文本工件。

        Args:
            file_name: 工件文件名

        Returns:
            文件内容；不存在时返回 None
        """

        file_path = self.get_working_file_path(file_name)
        if not file_path.exists():
            return None
        return file_path.read_text(encoding="utf-8")

    def read_working_solution(self, file_name: str = "solution.py") -> str:
        """读取工作区中的 solution.py。

        Args:
            file_name: 代码文件名

        Returns:
            代码文本

        Raises:
            ValueError: 文件不存在、不可读或为空
        """

        file_path = self.get_working_file_path(file_name)
        if not file_path.exists():
            raise ValueError(f"工作区未找到代码文件: {file_path}")

        try:
            code = file_path.read_text(encoding="utf-8")
        except OSError as error:
            raise ValueError(f"读取代码文件失败: {file_path}") from error

        if not code.strip():
            raise ValueError(f"代码文件为空: {file_path}")
        return code

    def read_working_submission(self, file_name: str = "submission.csv") -> str:
        """读取工作区中的 submission.csv。"""

        file_path = self.get_working_file_path(file_name)
        if not file_path.exists():
            raise ValueError(f"工作区未找到提交文件: {file_path}")

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as error:
            raise ValueError(f"读取提交文件失败: {file_path}") from error

        if not content.strip():
            raise ValueError(f"提交文件为空: {file_path}")
        return content

    def read_runtime_artifact(self, file_name: str) -> str | None:
        """读取 execute 阶段生成的运行时工件。

        Args:
            file_name: 工件文件名，例如 `stdout.log`

        Returns:
            文本内容；不存在时返回 None
        """

        return self.read_working_text(file_name)

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

        project_skills_dir = ""
        if (
            self.visible_project_skills_dir.exists()
            or self.visible_project_skills_dir.is_symlink()
        ):
            project_skills_dir = str(self.visible_project_skills_dir)

        return {
            "workspace_root": str(self.root),
            "data_dir": str(self.data_dir),
            "working_dir": str(self.working_dir),
            "history_dir": str(self.history_dir),
            "logs_dir": str(self.logs_dir),
            "db_path": str(self.db_path),
            "run_log_path": str(self.run_log_path),
            "project_skills_dir": project_skills_dir,
        }
