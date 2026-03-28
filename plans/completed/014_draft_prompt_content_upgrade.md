# 014: Draft Prompt 内容升级

## 元信息
- 状态: draft
- 创建: 2026-03-28
- 更新: 2026-03-28
- 负责人: Claude

## 1.1 摘要

基于对 MLE-bench 参考系统的对比分析，本轮目标是补强 Draft Prompt 的"血肉"——专家身份锚定、时间/步骤预算感知、强制输出格式、持续优化引导。

骨架（三阶段分离 + 上下文注入）不变，重点改内容。

## 1.2 审查点（Review Required）

| # | 决策项 | 当前倾向 | 说明 |
|---|--------|----------|------|
| 1 | 专家身份放哪里 | `config/agents/kaggle_master.yaml` | 遵守013边界，persona 属于 agent 定义 |
| 2 | 时间/步骤预算从哪来 | `DraftPES` 注入 | 需 `TimeManager` 或占位变量 |
| 3 | 可用库清单是否硬编码 | 是 | MVP 阶段直接写死，后续可配置化 |
| 4 | 输出格式如何强制 | 模板硬约束 | 明确段落结构，不加"可选"措辞 |

## 1.3 流程图/伪代码

```
┌─────────────────────────────────────────────────────────────────┐
│                     Prompt 内容升级数据流                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  config/agents/kaggle_master.yaml                               │
│  ├── [MODIFY] 添加 prompt_text 字段                              │
│  ├── [NEW] 专家身份: "Kaggle Grandmaster 级别 ML 专家"            │
│  └── [NEW] 目标声明: "目标是取得奖牌级别分数"                      │
│                                                                 │
│  system_context.md [MODIFY]                                     │
│  ├── [KEEP] 简洁/可验证/不虚构                                   │
│  ├── [DELETE] "避免过度工程化"（与金牌目标冲突）                    │
│  ├── [DELETE] "尊重上下文边界"（框架内部概念）                      │
│  └── [NEW] 禁止手标/禁止抄袭/持续优化意识                          │
│                                                                 │
│  draft_plan.j2                                                  │
│  ├── [NEW] 时间/步骤预算注入: {{ time_budget }}/{{ step_budget }}│
│  ├── [NEW] 方案约束: 简单/不重复父方案/有评估指标                  │
│  └── [KEEP] Slot 方案输出格式                                    │
│                                                                 │
│  draft_execute.j2                                               │
│  ├── [NEW] 强制输出格式: 报告 → 代码 → 验证结果                   │
│  ├── [NEW] 代码完整性要求: 自包含/可运行/保存 submission          │
│  ├── [NEW] 可用库清单                                           │
│  └── [KEEP] Gene/模板骨架渲染                                    │
│                                                                 │
│  draft_summarize.j2                                             │
│  ├── [NEW] 竞争指标对齐: 与父方案/历史最优对比                    │
│  ├── [NEW] 优化建议: 基于剩余预算的迭代方向                       │
│  └── [KEEP] 观察/推断/建议三层结构                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 1.4 拟议变更

### A. `config/agents/kaggle_master.yaml` [MODIFY]

**当前状态**：只有 `name` 和 `display_name`

**变更为**：
```yaml
name: kaggle_master
display_name: Kaggle Master
prompt_text: |
  你是一名 Kaggle Grandmaster 级别的机器学习专家，具备：
  - 丰富的竞赛经验和特征工程能力
  - 对各类 ML 算法的深刻理解
  - 高效的调试和优化能力

  你的目标是取得奖牌级别的分数，而非仅仅完成提交。
```

### B. `config/prompts/fragments/system_context.md` [MODIFY]

**删除**（与金牌目标冲突）：
- "避免过度工程化" — 金牌可能需要复杂优化
- "尊重上下文边界" — 框架内部概念，Agent 不需关心

**保留**：
- MVP 优先
- 先验证再扩展
- 不虚构事实
- 输出简洁可验证

**新增**（来自参考系统）：
```markdown
## 竞赛约束

- 禁止手标数据：不得手动标注测试集标签
- 禁止抄袭：不得直接复制他人解决方案
- 持续优化：目标是最佳分数，而非首个可运行方案
```

### C. `config/prompts/templates/draft_plan.j2` [MODIFY]

**新增注入点**（第2行后）：
```jinja2
{% if time_budget or step_budget %}
# 资源预算

- 剩余时间: {{ time_budget | default("未知") }}
- 剩余步骤: {{ step_budget | default("未知") }}
{% endif %}
```

**新增方案约束**（任务要求部分后）：
```markdown
## 方案约束

- 初始方案应尽量简单，不要使用集成方法或复杂的超参数优化
- 需要参考父方案但避免重复已有方法
- 方案需包含合理的评估指标
- 不要建议进行探索性数据分析（EDA）
- 数据已准备好，无需额外处理
```

### C. `config/prompts/templates/draft_execute.j2` [MODIFY]

**替换"交付要求"部分为强制格式**：
```markdown
# 输出格式

你必须严格按以下结构输出，不能包含任何额外标题或多余文本：

## 执行报告
（1-3 段自然语言，描述实际实现内容）

## 代码实现
```python
# 完整、自包含、可直接运行的代码
# 必须保存预测结果到指定路径
```

## 验证结果
- 指标名: {{ metric_name }}
- 指标值: X.XX
- 提交路径: {{ workspace.working_dir }}/submission.csv
```

**新增可用库清单**（执行要求前）：
```markdown
# 可用工具

- 基础库: numpy, pandas, scipy
- 机器学习: scikit-learn, xgboost, lightgbm
- 深度学习: torch, torchvision, timm
- 优化: optuna
- 推荐优先使用 PyTorch 进行深度学习任务
```

**新增代码完整性要求**（执行要求部分）：
```markdown
## 代码要求

- 代码必须完整、自包含、可直接运行
- 必须在验证集上计算并打印评估指标
- 必须将测试集预测结果保存为 submission.csv
- 代码应在规定时间内运行完成
```

### D. `config/prompts/templates/draft_summarize.j2` [MODIFY]

**新增竞争指标对齐**（评估结果部分后）：
```jinja2
{% if parent_solution and parent_solution.metrics %}
# 指标对比

- 本轮: {{ metric_value }}
- 父方案: {{ parent_solution.metrics.metric_value }}
- 变化: {{ "提升" if metric_value > parent_solution.metrics.metric_value else "下降" }}
{% endif %}
```

**新增优化建议模板**（下轮建议部分）：
```markdown
## 迭代方向

{% if time_budget and time_budget != "未知" %}
基于剩余时间预算，建议：
- 若预算充裕：考虑特征工程/模型调参/算法对比
- 若预算紧张：聚焦验证当前方案，确保提交有效
{% endif %}
```

### E. `tests/unit/test_agent_registry.py` [MODIFY]

**新增断言**：
- 验证 `kaggle_master` agent 的 `prompt_text` 含 "Kaggle Grandmaster"
- 验证 `prompt_text` 含 "奖牌级别"

### G. `tests/unit/test_prompt_manager.py` [MODIFY]

**新增断言**:
- 验证 `system_context.md` 不含 "过度工程化"
- 验证 `system_context.md` 含 "禁止抄袭" 或 "持续优化"
- 验证 `draft_execute.j2` 含 "可用工具"
- 验证 `draft_execute.j2` 含强制输出格式标记

## 1.5 验证计划

1. **Agent 加载验证**
   - `AgentRegistry.load("kaggle_master").prompt_text` 含 "Kaggle Grandmaster"
   - `prompt_text` 含 "奖牌级别分数"

2. **System Context 验证**
   - `system_context.md` 不含 "过度工程化"
   - `system_context.md` 含 "持续优化" 或 "最佳分数"

3. **模板渲染验证**
   - `PromptManager.build_prompt("draft", "plan", context)` 成功
   - 输出含 "资源预算"（当注入时）

4. **格式约束验证**
   - `draft_execute.j2` 渲染后含 "执行报告/代码实现/验证结果" 结构
   - `draft_execute.j2` 渲染后含可用库清单

5. **回归验证**
   - `test_prompt_manager.py` 全部通过
   - `test_draft_pes.py` 全部通过

## 1.6 风险

- 时间/步骤预算需 `DraftPES` 层注入，若 `TimeManager` 未就绪需先用占位
- 可用库清单硬编码后续可能需配置化，但 MVP 阶段可接受
