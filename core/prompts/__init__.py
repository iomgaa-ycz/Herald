"""Prompt 模块。

提供基于 spec + fragments + templates 的 Prompt 装配能力。
"""

from __future__ import annotations

from core.prompts.manager import PromptManager
from core.prompts.types import PromptSpec, TemplateSpec

__all__ = [
    "PromptManager",
    "PromptSpec",
    "TemplateSpec",
]
