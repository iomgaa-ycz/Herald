"""LLM 配置类。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LLMConfig:
    """LLM 配置。"""

    model: str = "glm-5"
    max_tokens: int = 32 * 1024
    max_turns: int = 16
    permission_mode: str = "bypassPermissions"
