"""PES YAML 配置加载。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


PHASE_ORDER: tuple[str, str, str] = ("plan", "execute", "summarize")


@dataclass(slots=True)
class PhaseConfig:
    """单个 phase 的配置。"""

    name: str
    prompt_template: str
    tool_names: list[str]
    max_retries: int


@dataclass(slots=True)
class PESConfig:
    """单个 PES 类型的配置。"""

    name: str
    operation: str
    solution_file_name: str
    submission_file_name: str | None
    phases: dict[str, PhaseConfig]

    def get_phase(self, phase: str) -> PhaseConfig:
        """获取指定 phase 配置。"""

        if phase not in self.phases:
            raise KeyError(f"缺少 phase 配置: {phase}")
        return self.phases[phase]


def _build_phase_config(name: str, payload: dict[str, Any]) -> PhaseConfig:
    """从 YAML 节点构造 PhaseConfig。"""

    prompt_template = str(payload.get("prompt_template", "")).strip()
    if not prompt_template:
        raise ValueError(f"phase={name} 缺少 prompt_template")

    tool_names_raw = payload.get("tool_names", [])
    if not isinstance(tool_names_raw, list):
        raise ValueError(f"phase={name} 的 tool_names 必须为列表")

    max_retries = int(payload.get("max_retries", 1))
    if max_retries < 1:
        raise ValueError(f"phase={name} 的 max_retries 必须 >= 1")

    return PhaseConfig(
        name=name,
        prompt_template=prompt_template,
        tool_names=[str(item) for item in tool_names_raw],
        max_retries=max_retries,
    )


def load_pes_config(path: str | Path) -> PESConfig:
    """从 YAML 文件加载 PES 配置。"""

    config_path = Path(path).expanduser().resolve()
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    name = str(payload.get("name", "")).strip()
    operation = str(payload.get("operation", "")).strip()
    solution_file_name = str(payload.get("solution_file_name", "")).strip()
    submission_file_name_raw = payload.get("submission_file_name")

    if not name:
        raise ValueError("PES 配置缺少 name")
    if not operation:
        raise ValueError("PES 配置缺少 operation")
    if not solution_file_name:
        raise ValueError("PES 配置缺少 solution_file_name")

    phases_payload = payload.get("phases", {})
    if not isinstance(phases_payload, dict):
        raise ValueError("PES 配置缺少 phases 或格式非法")

    phases: dict[str, PhaseConfig] = {}
    for phase_name in PHASE_ORDER:
        if phase_name not in phases_payload:
            raise ValueError(f"PES 配置缺少必需 phase: {phase_name}")
        phase_payload = phases_payload[phase_name]
        if not isinstance(phase_payload, dict):
            raise ValueError(f"phase={phase_name} 配置必须为对象")
        phases[phase_name] = _build_phase_config(phase_name, phase_payload)

    submission_file_name = None
    if submission_file_name_raw is not None:
        submission_file_name = str(submission_file_name_raw).strip() or None

    return PESConfig(
        name=name,
        operation=operation,
        solution_file_name=solution_file_name,
        submission_file_name=submission_file_name,
        phases=phases,
    )
