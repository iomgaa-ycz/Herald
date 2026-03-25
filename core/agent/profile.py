"""Agent 人格配置数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AgentProfile:
    """Agent 人格配置。"""

    name: str
    display_name: str
    prompt_text: str

    def to_prompt_payload(self) -> dict[str, Any]:
        """转换为 Prompt 可消费的上下文。"""

        return {
            "name": self.name,
            "display_name": self.display_name,
            "prompt_text": self.prompt_text,
        }
