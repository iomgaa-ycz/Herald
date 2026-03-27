"""DraftPES 最小 schema 定义。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TaskSpec:
    """任务规格。"""

    task_type: str
    competition_name: str
    objective: str
    metric_name: str
    metric_direction: str


@dataclass(slots=True)
class SlotContract:
    """单个 slot 的契约。"""

    function_name: str
    params: list[dict[str, str]]
    return_type: str


@dataclass(slots=True)
class GenomeSchema:
    """Genome 结构定义。"""

    task_type: str
    slots: dict[str, SlotContract | None]
