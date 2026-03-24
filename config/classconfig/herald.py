"""Herald 全局配置类。"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.classconfig.llm import LLMConfig
from config.classconfig.run import RunConfig
from core.pes.config import PESConfig


@dataclass
class HeraldConfig:
    """Herald 全局配置，组合 LLM、PES 和运行时配置。"""

    llm: LLMConfig = field(default_factory=LLMConfig)
    pes: PESConfig = field(default_factory=lambda: PESConfig(
        name="",
        operation="",
        solution_file_name="",
        submission_file_name=None,
        phases={},
    ))
    run: RunConfig = field(default_factory=RunConfig)
