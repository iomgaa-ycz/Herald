from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from anthropic import AsyncAnthropic


@dataclass(slots=True)
class LLMConfig:
    model: str = "glm-5"
    max_tokens: int = 32*1024
    max_turns: int = 16
    api_key: str | None = None


@dataclass(slots=True)
class LLMResponse:
    text: str
    code_block: str | None
    model: str
    tokens_in: int
    tokens_out: int


ToolFn = Callable[..., Any] | Callable[..., Awaitable[Any]]


class LLMClient:
    """
    精简版 Claude 多轮工具调用客户端：
    - 仅保留多轮 Agent 调用
    - 基于 Anthropic Python SDK tool_runner
    - tools 直接传 Python 函数即可
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig()
        self.client = AsyncAnthropic(api_key=self.config.api_key)

    async def call_with_tools(
        self,
        prompt: str,
        tools: list[ToolFn],
        system_prompt: str | None = None,
    ) -> LLMResponse:
        if not tools:
            raise ValueError("tools 不能为空，当前版本仅支持带工具的多轮调用")

        runner = self.client.beta.messages.tool_runner(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            tools=tools,
            system=system_prompt if system_prompt else None,
            messages=[{"role": "user", "content": prompt}],
        )

        final_message = None
        turn_count = 0

        async for message in runner:
            final_message = message
            turn_count += 1
            if turn_count >= self.config.max_turns:
                break

        if final_message is None:
            raise RuntimeError("未收到模型返回结果")

        text = self._extract_text(final_message)
        usage = getattr(final_message, "usage", None)

        return LLMResponse(
            text=text,
            code_block=self.extract_code_block(text),
            model=self.config.model,
            tokens_in=getattr(usage, "input_tokens", 0) or 0,
            tokens_out=getattr(usage, "output_tokens", 0) or 0,
        )

    @staticmethod
    def _extract_text(message: Any) -> str:
        """
        从 Anthropic message.content 中提取最终文本。
        """
        parts: list[str] = []

        for block in getattr(message, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)

        return "\n".join(parts).strip()

    @staticmethod
    def extract_code_block(text: str) -> str | None:
        pattern = r"```(?:python|py)\s*\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        return max(matches, key=len).strip() if matches else None


# ----------------------------
# 示例：定义工具
# ----------------------------

# async def get_weather(location: str) -> str:
#     return f"{location}：晴，26°C"


# def add(a: int, b: int) -> int:
#     return a + b


# ----------------------------
# 示例：调用
# ----------------------------

# import asyncio
#
# async def main():
#     client = LLMClient()
#     resp = await client.call_with_tools(
#         prompt="先调用天气工具查询上海天气，再计算 23 + 19，最后用中文总结。",
#         tools=[get_weather, add],
#         system_prompt="你是一个会主动调用工具的助手。",
#     )
#     print(resp.text)
#     print(resp.code_block)
#     print(resp.tokens_in, resp.tokens_out)
#
# asyncio.run(main())