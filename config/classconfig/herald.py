"""Herald 全局配置类。"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.classconfig.llm import LLMConfig
from config.classconfig.pes import PESConfig


@dataclass
class HeraldConfig:
    """Herald 全局配置，组合 LLM 和 PES 配置。"""

    llm: LLMConfig = field(default_factory=LLMConfig)
    pes: PESConfig = field(default_factory=lambda: PESConfig(
        name="",
        operation="",
        solution_file_name="",
        submission_file_name=None,
        phases={},
    ))
