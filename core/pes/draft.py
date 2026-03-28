"""DraftPES 最小可运行实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.events.bus import EventBus
from core.events.types import TaskCompleteEvent
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
            solution.execute_summary = response_text
            self._attach_workspace_artifacts(solution)
        elif phase == "summarize":
            solution.summarize_insight = response_text
            solution.status = "completed"
            solution.finished_at = utc_now_iso()
            # 发出任务完成事件
            EventBus.get().emit(
                TaskCompleteEvent(
                    task_name=self.config.name,
                    pes_instance_id=self.instance_id,
                    status="completed",
                    solution_id=solution.id,
                )
            )
        else:
            raise ValueError(f"不支持的 DraftPES phase: {phase}")

        return {
            "phase": phase,
            "response_text": response_text,
        }

    def _extract_response_text(self, response: object) -> str:
        """提取模型响应文本。"""

        result = getattr(response, "result", "")
        if result is None:
            return ""
        return str(result).strip()

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
        solution_path.touch(exist_ok=True)
        solution.solution_file_path = str(solution_path)

        if self.config.submission_file_name:
            submission_path = working_dir_path / self.config.submission_file_name
            submission_path.touch(exist_ok=True)
            solution.submission_file_path = str(submission_path)
