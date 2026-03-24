"""运行时配置类。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RunConfig:
    """运行时路径配置。

    Attributes:
        workspace_dir: 工作空间根目录路径
        competition_dir: 竞赛数据目录路径（必填）
    """

    workspace_dir: str = "workspace"
    competition_dir: str = ""
