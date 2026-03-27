# 008: LLMClient 迁移至 Claude Agent SDK

## 元信息
- 状态: draft
- 创建: 2026-03-27
- 更新: 2026-03-27

## 1.1 摘要

将 `core/llm.py` 从 Anthropic Messages API (`AsyncAnthropic` + `tool_runner`) 迁移到 Claude Agent SDK (`claude_agent_sdk.query`)。删除 `call()` / `call_with_tools()` 假 Agent 模式，统一为 `execute_task()` 真 Agent 模式。同步更新 `PhaseConfig` 新增 `allowed_tools` 和 `max_turns`，使每个 PES phase 可独立控制工具集和轮次。

## 1.2 审查点

| # | 决策项 | 当前倾向 | 说明 |
|---|--------|----------|------|
| 1 | Agent SDK 调用方式 | `query()` 一次性模式 | PES 每个 phase 独立调用，无需 `ClaudeSDKClient` 持续会话 |
| 2 | `permission_mode` 默认值 | `"bypassPermissions"` | 自动化场景无人交互，必须跳过权限确认 |
| 3 | `LLMResponse.code_block` 是否保留 | 删除 | 这是 DraftPES 特定解析逻辑，不属于通用响应 |
| 4 | `core/tools.py` 是否同步改为 MCP 格式 | 否，延后 | 008 只建设 `execute_task` 的 MCP 工具入参通道，实际转换留给后续计划 |
| 5 | `api_key` / `ANTHROPIC_BASE_URL` 如何传递 | `.claude/settings.local.json` 的 `env` 段 | Agent SDK 自动读取项目 `.claude/` 配置，无需 LLMConfig 持有 |
| 6 | `setting_sources` 设置 | `["user", "project", "local"]` | 确保 Agent SDK 同时读取系统级和项目级 `.claude/` 配置 |

## 1.3 流程与伪代码

### 调用链路变更

```
旧链路:
  BasePES._run_phase → call_phase_model → llm.call_with_tools(prompt, [python_fn])
                                          │ Anthropic Messages API + tool_runner
                                          └→ LLMResponse(text, code_block, model, tokens_in, tokens_out)

新链路:
  BasePES._run_phase → call_phase_model → llm.execute_task(prompt, allowed_tools=..., max_turns=...)
                                          │ Agent SDK query() → Claude Code Agent
                                          │ 内置工具: Bash, Read, Write, Edit, Glob, Grep
                                          │ 可选 MCP: mcp_servers={...}
                                          └→ LLMResponse(result, turns, model, tokens_in, tokens_out, cost_usd, duration_ms, session_id)
```

### LLMResponse 结构

```python
@dataclass(slots=True)
class LLMResponse:
    """Agent SDK 统一响应。"""

    result: str                      # ResultMessage.result — Agent 最终输出
    turns: list[dict[str, Any]]      # 所有轮次结构化记录（见下方格式）
    model: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    duration_ms: int
    session_id: str | None

# turns 中每个元素格式:
# {
#     "role": "assistant",
#     "text": "我来分析数据...",
#     "tool_calls": [
#         {
#             "name": "Bash",
#             "input": {"command": "python solution.py"},
#             "result": "Accuracy: 0.85\nDone.",
#         },
#     ],
# }
```

### LLMClient.execute_task 伪代码

```python
async def execute_task(
    self, prompt, *, system_prompt=None,
    max_turns=None, allowed_tools=None,
    mcp_servers=None, cwd=None, env=None,
) -> LLMResponse:
    options = ClaudeAgentOptions(
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

    turns: list[dict[str, Any]] = []
    pending_tool_calls: dict[str, dict] = {}  # tool_use_id → tool_call dict

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            turn = {"role": "assistant", "text": "", "tool_calls": []}
            for block in message.content:
                if isinstance(block, TextBlock):
                    turn["text"] += block.text
                elif isinstance(block, ToolUseBlock):
                    tc = {"name": block.name, "input": block.input, "result": None}
                    turn["tool_calls"].append(tc)
                    pending_tool_calls[block.id] = tc
                elif isinstance(block, ToolResultBlock):
                    target = pending_tool_calls.get(block.tool_use_id)
                    if target is not None:
                        target["result"] = block.content
            if turn["text"] or turn["tool_calls"]:
                turns.append(turn)

        elif isinstance(message, ResultMessage):
            return LLMResponse(
                result=message.result or "",
                turns=turns,
                model=self.config.model,
                tokens_in=(message.usage or {}).get("input_tokens", 0),
                tokens_out=(message.usage or {}).get("output_tokens", 0),
                cost_usd=message.total_cost_usd,
                duration_ms=message.duration_ms,
                session_id=message.session_id,
            )

    raise RuntimeError("未收到 ResultMessage")
```

### BasePES.call_phase_model 伪代码

```python
async def call_phase_model(self, phase, prompt):
    phase_config = self.config.get_phase(phase)
    last_error = None

    for _ in range(phase_config.max_retries):
        try:
            return await self.llm.execute_task(
                prompt=prompt,
                max_turns=phase_config.max_turns,
                allowed_tools=phase_config.allowed_tools or None,
                # mcp_servers 由子类覆盖 call_phase_model 时按需注入
            )
        except Exception as error:
            last_error = error

    raise last_error
```

## 1.4 拟议变更

### 核心改造

- [MODIFY] `core/llm.py`
  - 删除 `from anthropic import AsyncAnthropic`
  - 删除 `LLMClient.call_with_tools()` 方法
  - 删除 `LLMClient._extract_text()` 静态方法
  - 删除 `LLMClient.extract_code_block()` 静态方法
  - 删除 `ToolFn` 类型别名
  - 删除文件末尾示例注释
  - [NEW] `import claude_agent_sdk` 相关类型
  - [MODIFY] `LLMConfig`: 删除 `api_key`，新增 `permission_mode: str = "bypassPermissions"`
  - [MODIFY] `LLMResponse`: 删除 `text` + `code_block`，新增 `result`（最终输出）、`turns`（完整对话记录含工具调用及返回）、`cost_usd`、`duration_ms`、`session_id`
  - [NEW] `LLMClient.execute_task()` — 基于 `claude_agent_sdk.query()` 的统一方法
  - [NEW] `LLMClient._build_options()` — 构造 `ClaudeAgentOptions`

### 配置适配

- [MODIFY] `core/pes/config.py::PhaseConfig`
  - [NEW] `allowed_tools: list[str]` — 该 phase 允许的内置 Agent 工具
  - [NEW] `max_turns: int` — 该 phase 最大 Agent 轮次
  - [MODIFY] `_build_phase_config()` 解析新字段（带默认值，向后兼容）

- [MODIFY] `config/classconfig/llm.py::LLMConfig`
  - 同步 `core/llm.py` 的 LLMConfig 变更（删除 `api_key`，新增 `permission_mode`）

### 上游调用方适配

- [MODIFY] `core/pes/base.py::BasePES.call_phase_model()`
  - 将 `llm.call_with_tools()` / `llm.call()` 双路径替换为 `llm.execute_task()`
  - 传入 `phase_config.max_turns` 和 `phase_config.allowed_tools`
  - 删除 `_filter_tools_by_names` 对 Python callable 的过滤逻辑（MCP 工具注入留给子类覆盖）

- [MODIFY] `core/pes/base.py::BasePES._log_llm_call()`
  - `response.text` → `response.result`
  - 适配 `LLMResponse` 新增的 `cost_usd`, `duration_ms` 字段

- [MODIFY] `core/pes/base.py::BasePES._run_phase()`
  - `solution.phase_outputs[phase] = response.text` → `response.result`
  - `phase_context.response_text = response.text` → `response.result`

### 测试适配

- [MODIFY] `tests/integration/test_dispatch_flow.py`
  - `DummyLLM.call()` → `DummyLLM.execute_task()`，签名对齐新接口
  - `DummyResponse`: `text` → `result`，新增 `turns=[]`、`cost_usd`、`duration_ms`、`session_id` 字段
  - `_build_config()` 中 PhaseConfig 补充 `allowed_tools=[]`, `max_turns=1`

### 延后不改

- [NO-CHANGE] `core/tools.py` — 保留现有 Python callable 工具，后续计划转 MCP 格式。008 切断了其调用链路（`call_phase_model` 不再调 `_filter_tools_by_names` 传 callable 给 LLM），这些工具暂变为死代码，直到后续计划将其转为 MCP 格式通过 `mcp_servers` 注入
- [NO-CHANGE] `core/pes/base.py::BasePES.__init__` 中的 `self.tools` 属性和 `_normalize_tool_registry` — 保留工具注册机制骨架，供后续 MCP 改造复用
- [NO-CHANGE] `core/load_config.py` — ConfigManager 自动适配 dataclass 字段变更

## 1.5 验证计划

1. **单元验证**
   - `LLMConfig` 新字段默认值正确
   - `LLMResponse` 新字段可正常序列化
   - `PhaseConfig` 新字段 `allowed_tools` 和 `max_turns` 解析正确
   - `PhaseConfig` 向后兼容：YAML 未指定新字段时使用默认值

2. **集成验证**
   - `tests/integration/test_dispatch_flow.py` 使用 DummyLLM 全部通过
   - 验证 `BasePES._run_phase` → `call_phase_model` → `llm.execute_task()` 调用链畅通

3. **冒烟验证**（手工）
   - `conda activate herald && python -c "from core.llm import LLMClient, LLMConfig"` 导入无报错
   - `python -c "from claude_agent_sdk import query, ClaudeAgentOptions"` 导入无报错

## 2. 实施边界

- 只改 LLMClient 核心 + 必要的上下游适配
- 不改 `core/tools.py` 工具格式
- 不引入新的 PES 子类
- 不改 `core/main.py`
- 不写新的 Prompt 模板

## 3. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Agent SDK `query()` 在 `max_turns=1` + 无工具时是否退化为纯文本生成 | 验证：构造最简 options 调用 query，确认不会卡在工具等待 |
| `.claude/settings.local.json` 中的 `ANTHROPIC_BASE_URL` 能否被 Agent SDK 读取 | Agent SDK 通过 `setting_sources=["local"]` 加载 env 段；若失败则手动注入 `env` 参数 |
| `permission_mode="bypassPermissions"` 是否需要特殊权限 | Agent SDK 文档明确支持此模式，自动化场景推荐 |
| DummyLLM 接口变更导致其他测试断裂 | 搜索所有 DummyLLM 使用点，确保全部适配 |
