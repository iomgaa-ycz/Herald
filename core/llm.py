"""基于 Claude Agent SDK 的 LLM 客户端。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    query,
)


@dataclass(slots=True)
class LLMConfig:
    """LLM 配置。"""

    model: str = "glm-5"
    max_tokens: int = 32 * 1024
    max_turns: int = 16
    permission_mode: str = "bypassPermissions"


@dataclass(slots=True)
class LLMResponse:
    """Agent SDK 统一响应。"""

    result: str
    turns: list[dict[str, Any]]
    model: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    duration_ms: int
    session_id: str | None


class LLMClient:
    """基于 Claude Agent SDK query() 的统一客户端。"""

    def __init__(self, config: LLMConfig | None = None) -> None:
        """初始化客户端。"""

        self.config = config or LLMConfig()

    def _build_options(
        self,
        *,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        allowed_tools: list[str] | None = None,
        mcp_servers: dict[str, Any] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ClaudeAgentOptions:
        """构造 ClaudeAgentOptions。"""

        return ClaudeAgentOptions(
            model=self.config.model,
            system_prompt=system_prompt,
            max_turns=max_turns or self.config.max_turns,
            allowed_tools=allowed_tools or [],
            permission_mode=self.config.permission_mode,
            cwd=cwd,
            env=env or {},
            mcp_servers=mcp_servers or {},
            setting_sources=["user", "project", "local"],
        )

    async def execute_task(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        allowed_tools: list[str] | None = None,
        mcp_servers: dict[str, Any] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> LLMResponse:
        """执行 Agent 任务。

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            max_turns: 最大轮次
            allowed_tools: 允许的内置 Agent 工具列表
            mcp_servers: MCP 服务器配置
            cwd: 工作目录
            env: 环境变量
        """

        options = self._build_options(
            system_prompt=system_prompt,
            max_turns=max_turns,
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers,
            cwd=cwd,
            env=env,
        )

        turns: list[dict[str, Any]] = []
        pending_tool_calls: dict[str, dict[str, Any]] = {}

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                turn: dict[str, Any] = {
                    "role": "assistant",
                    "text": "",
                    "tool_calls": [],
                }
                for block in message.content:
                    if isinstance(block, TextBlock):
                        turn["text"] += block.text
                    elif isinstance(block, ToolUseBlock):
                        tc: dict[str, Any] = {
                            "name": block.name,
                            "input": block.input,
                            "result": None,
                        }
                        turn["tool_calls"].append(tc)
                        pending_tool_calls[block.id] = tc
                    elif isinstance(block, ToolResultBlock):
                        target = pending_tool_calls.get(block.tool_use_id)
                        if target is not None:
                            target["result"] = block.content
                if turn["text"] or turn["tool_calls"]:
                    turns.append(turn)

            elif isinstance(message, ResultMessage):
                usage = message.usage or {}
                return LLMResponse(
                    result=message.result or "",
                    turns=turns,
                    model=self.config.model,
                    tokens_in=usage.get("input_tokens", 0),
                    tokens_out=usage.get("output_tokens", 0),
                    cost_usd=message.total_cost_usd,
                    duration_ms=message.duration_ms,
                    session_id=message.session_id,
                )

        raise RuntimeError("未收到 ResultMessage")
