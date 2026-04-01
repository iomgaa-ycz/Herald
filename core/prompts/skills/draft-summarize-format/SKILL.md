---
name: draft-summarize-format
description: >-
  This skill should be used when the Draft Agent needs to
  "write summarize_insight", "format draft summary",
  "structure the draft experiment conclusion", or
  "ensure downstream drafts and CLI can consume the output".
  Defines the fixed 5-section paragraph schema for draft summarize output.
---

# Draft Summarize 输出格式

在 `DraftPES.summarize` 阶段输出实验总结时使用。

## 何时使用

- 输出 `summarize_insight` 实验总结
- 确保输出结构化、可解析、可被后续 draft 和 CLI 消费
- 避免输出列点式总结导致信息密度低和因果关系丢失

## 固定标题结构

输出必须严格遵循以下 5 个 section 的标题和顺序。每个 section **必须是一段逻辑通顺的话，禁止使用列点、编号列表或孤立短语**。

```markdown
# 摘要
（一段话：策略 + 结果 + 核心发现）

# 策略选择
（一段话：模型、特征工程、验证策略、资源配置的选择及原因）

# 执行结果
（一段话：指标值、耗时、submission 状态、是否符合预期）

# 关键发现
（一段话：有因果逻辑的分析，不是孤立事实）

# 建议方向
（一段话：下次应该尝试什么不同的方向，为什么）
```

## 各 Section 职责

| Section | 职责 | 消费者 |
|---------|------|--------|
| 摘要 | 策略关键词 + 指标值 + 一句话核心发现 | `list-drafts` CLI 提取第一段作为简报（截断 300 字符） |
| 策略选择 | 模型类型、特征工程方法、验证策略、资源配置的选择及原因 | 后续 draft 用于差异化规划 |
| 执行结果 | 指标值、耗时、submission 状态、是否符合预期 | L2 知识写入、方案评估 |
| 关键发现 | 有因果逻辑的分析，不是孤立事实 | 后续 draft 避免重复错误 |
| 建议方向 | 下次应尝试的不同方向及理由 | 后续 draft 差异化探索 |

## 格式约束

- **段落而非列点**：消费者是 LLM Agent，段落能表达因果关系和逻辑链条，列点只能罗列孤立事实
- **摘要在前**：`list-drafts` CLI 只提取 "# 摘要" 小节的第一段（截断到 300 字符），作为可扫描简报。摘要应包含策略关键词和指标数值
- 明确区分三类信息：
  - `观察`：日志、指标、状态中能直接看到的事实
  - `推断`：基于事实做出的原因判断（必须标注为推断）
  - `建议`：下一轮应保留、修改或新增的方向
- 不要虚构未观察到的实验事实

## 成功 / 失败侧重

- **成功 case**：重点说明哪些决策值得复用，哪些仍需继续试验
- **失败 case**：重点输出失败根因、阻塞位置和最值得优先补强的能力

## 降级策略

- 若某 section 信息确实无法从执行日志和指标中获取，使用"信息不足"标注，但**不能省略该 section 标题**
- 5 个 section 标题必须始终完整出现
