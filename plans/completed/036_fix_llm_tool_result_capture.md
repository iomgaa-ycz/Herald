# 036 修复 LLMClient turns 中 tool result 丢失导致 execute fact 提取失败

## 元信息
- 状态: active
- 创建: 2026-03-30
- 负责人: Claude

## 1. 摘要

`LLMClient.execute_task()` 仅处理 `AssistantMessage`，忽略了 `UserMessage`。Claude Agent SDK 中工具执行结果通过 `UserMessage.content` 中的 `ToolResultBlock` 返回，导致 turns 记录中所有 `tool_call["result"]` 都是 `None`，下游 `DraftPES._extract_execute_fact()` 因无法获取 `exit_code` 而抛出 `ValueError`。

## 2. 故障链路

```
async for message in query():
  AssistantMessage → ToolUseBlock 记录到 pending_tool_calls ✅
  UserMessage → ToolResultBlock 需要回写到 pending_tool_calls ❌ (被忽略)
  ResultMessage → 构造 LLMResponse ✅

→ 所有 tool_call["result"] = None
→ _parse_exec_fact_from_tool_call() 中 exit_code = None → return None
→ _extract_execute_fact() 抛出 ValueError
```

## 3. 拟议变更

| 操作 | 文件 | 函数/位置 | 说明 |
|------|------|-----------|------|
| `[MODIFY]` | `core/llm.py:8` | import 区 | 新增 `UserMessage` 导入 |
| `[MODIFY]` | `core/llm.py:117` | `execute_task()` | 增加 `elif isinstance(message, UserMessage)` 分支，提取 `ToolResultBlock` 回写 `pending_tool_calls` |

## 4. 验证计划

1. 代码审查：确认 `UserMessage` 分支正确处理 `content` 为 `str` 和 `list` 两种情况
2. 重新运行 draft PES，确认 `_extract_execute_fact()` 成功提取到 `exit_code`
