"""DraftPES 最小可运行实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.pes.base import BasePES
from core.pes.types import PESSolution
from core.utils.utils import utc_now_iso


class DraftPES(BasePES):
    """DraftPES 的最小可运行版本。"""

    def build_phase_model_options(
        self,
        phase: str,
        solution: PESSolution,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        """为 execute phase 提供工作目录与环境变量。"""

        del solution, parent_solution
        if phase != "execute" or self.workspace is None:
            return {}

        working_dir = getattr(self.workspace, "working_dir", None)
        db_path = getattr(self.workspace, "db_path", None)
        if working_dir is None or db_path is None:
            return {}

        return {
            "cwd": str(working_dir),
            "env": {
                "HERALD_DB_PATH": str(db_path),
            },
        }

    async def handle_phase_response(
        self,
        phase: str,
        solution: PESSolution,
        response: object,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        """以最小方式消费 phase 响应，保证 DraftPES.run() 可完成。"""

        del parent_solution
        response_text = self._extract_response_text(response)

        # Phase 1: 写入各阶段最小摘要
        if phase == "plan":
            solution.plan_summary = response_text
        elif phase == "execute":
            return self._handle_execute_response(solution, response_text)
        elif phase == "summarize":
            solution.summarize_insight = response_text
            solution.status = "completed"
            solution.finished_at = utc_now_iso()
            self._emit_task_complete_event(solution=solution, status="completed")
        else:
            raise ValueError(f"不支持的 DraftPES phase: {phase}")

        return {
            "phase": phase,
            "response_text": response_text,
        }

    def _handle_execute_response(
        self,
        solution: PESSolution,
        response_text: str,
    ) -> dict[str, Any]:
        """处理 execute 阶段的 tool-write 契约。"""

        self._attach_workspace_artifacts(solution)
        self._assert_tool_write_contract(solution)
        code = self._load_written_solution_code(solution)
        self._validate_python_code(solution=solution, code=code)
        self._persist_code_snapshot(solution=solution, code=code)
        solution.execute_summary = (
            "工具已成功写出 working/solution.py，并通过语法校验。"
        )

        return {
            "phase": "execute",
            "response_text": response_text,
            "code": code,
            "solution_file_path": solution.solution_file_path,
        }

    def _extract_response_text(self, response: object) -> str:
        """提取模型响应文本。"""

        result = getattr(response, "result", "")
        if result is None:
            return ""
        return str(result).strip()

    def _assert_tool_write_contract(self, solution: PESSolution) -> Path:
        """确认工具已将 solution.py 写入工作区。"""

        if self.workspace is None:
            raise ValueError("DraftPES 缺少 workspace，无法校验 tool-write 契约")

        get_path = getattr(self.workspace, "get_working_file_path", None)
        if callable(get_path):
            solution_path = get_path(self.config.solution_file_name)
        else:
            working_dir = getattr(self.workspace, "working_dir", None)
            if working_dir is None:
                raise ValueError("workspace 未提供 working_dir，无法校验 solution.py")
            solution_path = Path(working_dir) / self.config.solution_file_name

        if not solution_path.exists():
            detail = f"execute 阶段未写出代码文件: {solution_path}"
            self._log_contract_check(
                solution.id, "tool_write_solution_file", False, detail
            )
            raise ValueError(detail)

        self._log_contract_check(
            solution.id,
            "tool_write_solution_file",
            True,
            f"代码文件已生成: {solution_path}",
        )
        return solution_path

    def _load_written_solution_code(self, solution: PESSolution) -> str:
        """读取工作区中已写出的 solution.py。"""

        if self.workspace is None:
            raise ValueError("DraftPES 缺少 workspace，无法读取 solution.py")

        reader = getattr(self.workspace, "read_working_solution", None)
        if callable(reader):
            try:
                code = reader(self.config.solution_file_name)
            except ValueError as error:
                self._log_contract_check(
                    solution.id,
                    "tool_write_solution_content",
                    False,
                    str(error),
                )
                raise
            self._log_contract_check(
                solution.id,
                "tool_write_solution_content",
                True,
                "solution.py 内容非空且可读取",
            )
            return code

        working_dir = getattr(self.workspace, "working_dir", None)
        if working_dir is None:
            raise ValueError("workspace 未提供 working_dir，无法读取 solution.py")

        solution_path = Path(working_dir) / self.config.solution_file_name
        try:
            code = solution_path.read_text(encoding="utf-8")
        except OSError as error:
            detail = f"读取代码文件失败: {solution_path}"
            self._log_contract_check(
                solution.id,
                "tool_write_solution_content",
                False,
                detail,
            )
            raise ValueError(detail) from error

        if not code.strip():
            detail = f"代码文件为空: {solution_path}"
            self._log_contract_check(
                solution.id,
                "tool_write_solution_content",
                False,
                detail,
            )
            raise ValueError(detail)
        self._log_contract_check(
            solution.id,
            "tool_write_solution_content",
            True,
            "solution.py 内容非空且可读取",
        )
        return code

    def _validate_python_code(
        self,
        solution: PESSolution,
        code: str,
    ) -> None:
        """对生成代码做最小 Python 语法检查。"""

        try:
            compile(code, "<solution.py>", "exec")
        except SyntaxError as error:
            detail = f"solution.py 语法错误: line {error.lineno}, {error.msg}"
            self._log_contract_check(solution.id, "python_syntax", False, detail)
            raise ValueError(detail) from error

        self._log_contract_check(
            solution.id,
            "python_syntax",
            True,
            "solution.py 通过语法校验",
        )

    def _persist_code_snapshot(
        self,
        solution: PESSolution,
        code: str,
    ) -> None:
        """持久化完整代码快照。"""

        if self.db is None or not hasattr(self.db, "insert_code_snapshot"):
            return
        self.db.insert_code_snapshot(solution.id, code)

    def _attach_workspace_artifacts(self, solution: PESSolution) -> None:
        """在有工作空间时挂载最小工件路径。"""

        if self.workspace is None:
            return

        working_dir = getattr(self.workspace, "working_dir", None)
        if working_dir is None:
            return

        working_dir_path = Path(working_dir)
        working_dir_path.mkdir(parents=True, exist_ok=True)
        solution.workspace_dir = str(working_dir_path)

        solution_path = working_dir_path / self.config.solution_file_name
        solution.solution_file_path = str(solution_path)

        if self.config.submission_file_name:
            submission_path = working_dir_path / self.config.submission_file_name
            solution.submission_file_path = str(submission_path)
        self._persist_solution_artifacts(solution)
