"""基于 Claude Agent SDK 的 LLM 客户端。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

logger = logging.getLogger(__name__)


def _text_from_content(content: str | list[dict[str, Any]] | None) -> str:
    """从 ToolResultBlock.content 提取纯文本。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    # list[dict] 形式，如 [{"type": "text", "text": "..."}]
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text", "")
            if text:
                parts.append(text)
    return "\n".join(parts)


@dataclass(slots=True)
class LLMConfig:
    """LLM 配置。"""

    model: str = "glm-5"
    max_tokens: int = 32 * 1024
    max_turns: int = 16
    permission_mode: str = "bypassPermissions"
    setting_sources: tuple[str, ...] = ("project",)

    def __post_init__(self) -> None:
        """归一化可迭代配置字段。"""

        self.setting_sources = tuple(str(item) for item in self.setting_sources)


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
            setting_sources=list(self.config.setting_sources),
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
        result_response: LLMResponse | None = None

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

            elif isinstance(message, UserMessage):
                # tool_use_result 是 CLI 级结构化数据（含 stdout/stderr），
                # 但没有 exit_code 也没有 parent_tool_use_id 关联。
                # ToolResultBlock 有 tool_use_id 关联和 is_error 标记。
                # 策略：通过 ToolResultBlock.tool_use_id 关联，合并两者。
                cli_result = (
                    message.tool_use_result
                    if isinstance(message.tool_use_result, dict)
                    else {}
                )
                content = message.content
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, ToolResultBlock):
                            continue
                        target = pending_tool_calls.get(block.tool_use_id)
                        if target is None:
                            continue
                        result: dict[str, Any] = {}
                        result["stdout"] = cli_result.get(
                            "stdout"
                        ) or _text_from_content(block.content)
                        result["stderr"] = cli_result.get("stderr", "")
                        result["exit_code"] = 1 if block.is_error else 0
                        target["result"] = result

            elif isinstance(message, ResultMessage):
                usage = message.usage or {}
                result_response = LLMResponse(
                    result=message.result or "",
                    turns=turns,
                    model=self.config.model,
                    tokens_in=usage.get("input_tokens", 0),
                    tokens_out=usage.get("output_tokens", 0),
                    cost_usd=message.total_cost_usd,
                    duration_ms=message.duration_ms,
                    session_id=message.session_id,
                )

        if result_response is None:
            raise RuntimeError("未收到 ResultMessage")
        return result_response
