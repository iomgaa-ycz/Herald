# 013: 清理 System Context 与 Agent Prompt 边界

## 元信息
- 状态: in_progress
- 创建: 2026-03-28
- 更新: 2026-03-28
- 负责人: Codex

## 1.1 摘要

本轮目标是落实 Prompt 分层约束：`system_context.md` 只保留所有 Agent、所有 phase 都成立的全局系统规则；具体的 Agent 身份、风格、偏好统一只写在 agent prompt 中。

本轮不改任务协议，不改 `PromptManager` 逻辑，重点是把内容边界理顺并加最小测试防回退。

## 1.2 审查点（Review Required）

| # | 决策项 | 当前倾向 | 说明 |
|---|--------|----------|------|
| 1 | `system_context.md` 是否保留“你是某类 Agent”措辞 | 否 | 这属于 persona，不属于全局规则 |
| 2 | `kaggle_master.md` 是否补全 persona | 是 | 当前只有占位句，无法承载 agent 定义 |
| 3 | 是否修改模板结构 | 否 | 当前模板已显式区分 `static_fragments_text` 与 `agent.prompt_text` |

## 1.3 拟议变更（Proposed Changes）

### A. 收缩全局系统规则

- [MODIFY] `config/prompts/fragments/system_context.md`
  - 删除 Agent 身份定义
  - 删除 persona 风格措辞
  - 仅保留全局稳定规则：
    - MVP / 禁止过度工程化
    - 先验证再扩展
    - 任务、Agent、结果边界
    - 输出与事实约束

### B. 补全 Agent Persona

- [MODIFY] `config/agents/prompts/kaggle_master.md`
  - 明确 `kaggle_master` 的角色定位
  - 明确其执行风格、验证偏好、风险取向
  - 不写任务目标、不写固定 task spec、不写 phase 专属要求

### C. 边界回归测试

- [MODIFY] `tests/unit/test_agent_registry.py`
  - 增加对 `kaggle_master` persona 内容的断言
  - 增加对 `system_context.md` 全局规则定位的断言

## 1.4 验证计划（Verification Plan）

1. Agent 加载验证
   - `AgentRegistry.load("kaggle_master")` 成功
   - `prompt_text` 含明确 persona 描述

2. 边界验证
   - `system_context.md` 不再声明“你是某个 Agent”
   - `system_context.md` 含“全局系统规则”类约束

3. 回归验证
   - `test_agent_registry.py`
   - `test_prompt_manager.py`
   - `test_draft_pes.py`

## 1.5 风险

- 当前只有一个 Agent，persona 设计仍偏占位，但至少边界会正确
- 后续若新增多个 Agent，需要继续遵守相同分层，不应再把 persona 回填到 `system_context.md`
