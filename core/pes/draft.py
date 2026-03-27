"""DraftPES 骨架实现。"""

from __future__ import annotations

from typing import Any

from core.pes.base import BasePES
from core.pes.types import PESSolution


class DraftPES(BasePES):
    """DraftPES 的最小骨架。"""

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
        """占位处理 phase 响应，留待下一轮补齐。"""

        del solution, response, parent_solution
        raise NotImplementedError(
            f"DraftPES phase={phase} 业务逻辑待下一轮实现"
        )
