# 044 draft_plan 差异化约束 + plan 阶段开放 Bash

## 元信息
- 状态: draft
- 创建: 2026-04-02
- 对应: TD.md §5.5 Task 5

## 1.1 摘要

让 Agent 在 draft plan 阶段能通过 Bash 调 CLI 查询前序 draft 经验，并通过 Skill 引导实现差异化。变更两个文件：`draft_plan.j2` 新增一句 Skill 引导（无条件渲染），`draft.yaml` plan phase 的 `allowed_tools` 加入 `Bash`。

## 1.2 审查点

- [x] `core/pes/draft.py` 无需修改——所有变量已在 prompt context 中
- [x] `draft.yaml` plan phase 已有 `max_turns: 3`，无需变更
- [ ] Skill 引导句的插入位置：放在"方案约束"小节末尾是否合理

## 1.3 设计决策与既有模式对齐

### 为什么不做 `generation > 0` 条件渲染

TD §4.5 原始设计用 `{% if generation > 0 %}` 条件判断，但这是多余的：
- 第一次 draft 调 `get-l2-insights` 返回空数组，Agent 自然知道无历史，Skill 中"空结果处理"已说明"直接按正常流程规划"
- 去掉条件判断，模板更简洁，逻辑统一

### 为什么不在模板中硬编码 CLI 命令

既有模式对比：

| 模板 | 引导方式 |
|------|----------|
| `feature_extract_execute.j2:83` | "严格遵循 `feature-extract-report-format` skill" |
| `draft_summarize.j2:97` | "请使用 `draft-summarize-format` skill" |
| `draft_plan.j2`（本次） | 应同理：引导使用 `draft-history-review` skill |

项目的既有模式是：**模板只引导 Agent 去使用某个 Skill，具体操作细节由 Skill 自己承载**。Task 4 创建的 `draft-history-review` Skill 已完整覆盖 CLI 命令、差异化维度、空结果处理和禁止事项。在模板中重复这些内容既冗余又增加维护成本。

## 1.4 拟议变更

### `config/prompts/templates/draft_plan.j2` [MODIFY]

在"## 方案约束"小节末尾新增一条：

```text
- 规划前请先使用 `draft-history-review` skill 查询前序 draft 经验，基于查询结果规划差异化方向，避免重复已有方案的核心策略
```

无条件渲染，无 Jinja2 逻辑分支。Agent 看到 Skill 名称后自行调用，首次 draft 查询返回空则正常规划。

### `config/pes/draft.yaml` [MODIFY]

plan phase `allowed_tools` 增加 `"Bash"`：

```yaml
  plan:
    template_name: null
    tool_names: []
    max_retries: 1
    allowed_tools: ["Bash", "Read", "Glob", "Grep"]  # [MODIFY] 新增 Bash
    max_turns: 3                                       # 不变
```

## 1.5 验证计划

| 验证项 | 方法 | 预期结果 |
|--------|------|----------|
| draft_plan.j2 含 Skill 引导 | 读取模板 | 包含 `draft-history-review` 字样 |
| draft_plan.j2 无硬编码 CLI | 全文搜索 | 无 `get-l2-insights` 命令行、无 `list-drafts` |
| draft_plan.j2 无 generation 条件分支 | 全文搜索 | 无 `{% if.*generation` |
| plan phase allowed_tools 含 Bash | 读取 draft.yaml | `allowed_tools` 列表包含 `"Bash"` |
| plan phase max_turns = 3 | 读取 draft.yaml | `max_turns` 为 3 |

## 涉及文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `config/prompts/templates/draft_plan.j2` | MODIFY | 方案约束末尾新增 Skill 引导（一行） |
| `config/pes/draft.yaml` | MODIFY | plan phase allowed_tools 加 Bash |
