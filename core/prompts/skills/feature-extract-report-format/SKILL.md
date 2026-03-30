---
name: feature-extract-report-format
description: >-
  This skill should be used when the FeatureExtract Agent needs to
  "write data_profile", "format data analysis report", "structure data_profile.md",
  or "ensure downstream DraftPES can consume the output". Defines the fixed
  8-section Markdown schema, minimum field coverage, and data sourcing rules.
---

# FeatureExtract 数据报告格式

在 `FeatureExtractPES.execute` 阶段，完成数据预览后编写 `data_profile` 时使用。

## 何时使用

- 将预览事实整理为 `data_profile` 输出
- 确保 `data_profile.md` 可被下游 `DraftPES` 稳定消费
- 避免输出"一段话总结"导致信息丢失和可读性不足

## 固定标题结构

`data_profile` 的值必须是完整 Markdown 文本，严格遵循以下 8 个 section 的标题和顺序：

```markdown
# 数据概况报告

## 1. 数据集概览
- 竞赛名称: <名称>
- 任务类型: <分类/回归/排序/其他>
- 训练集规模: <行数> 行 x <列数> 列
- 测试集规模: <行数> 行 x <列数> 列

## 2. 特征分析
- 数值特征: <列名列表及统计量（min/max/mean/std/skew）>
- 类别特征: <列名列表及基数（nunique）>
- 高基数特征: <唯一值 > 1000 的特征及唯一值数>
- 字符串模式: <固定长度字符串特征的长度、字符集>

## 3. 缺失值
- <缺失列名及缺失比例列表>
- 若无缺失值，写"无缺失值"

## 4. 目标变量
- 列名: <target 列名>
- 类型: <连续/二分类/多分类>
- 分布: <类别比例或值域范围>
- 平衡性: <是否平衡，最大/最小类别比例>

## 5. 提交格式
- 列顺序: <sample_submission.csv 的列顺序>
- ID 列: <ID 列名>
- 目标列: <预测目标列名>
- 行数约束: <应与 test 行数一致，写明具体数字>

## 6. 运行环境
- CPU: <核数> [必须引用预览工具输出]
- 内存: <GB> [必须引用预览工具输出]
- GPU: <是否可用，型号，显存> [必须引用预览工具输出]

## 7. 训练建议
- 推荐模型: <引用预览工具输出的模型列表及配置>
- n_jobs 建议: <必须引用预览工具计算的推荐值，禁止自行设定为 -1>
- GPU 建议: <引用预览工具的 GPU 检测结果决定是否启用>
- 验证集划分: <引用预览工具的策略建议（k-fold/time-based/holdout）、fold 数、是否 Stratified>

## 8. 关键发现与建模建议
- <竞赛描述中的特殊提示>
- <数据特性对建模方案的影响>
```

## 最小字段覆盖

| Section | 必填字段 |
|---------|----------|
| 1. 数据集概览 | 竞赛名称、任务类型、训练集规模、测试集规模 |
| 2. 特征分析 | 数值特征统计量、类别特征基数、高基数列 |
| 3. 缺失值 | 明确有无缺失值 |
| 4. 目标变量 | 列名、类型、平衡性 |
| 5. 提交格式 | 列顺序、目标列 |
| 6. 运行环境 | CPU 核数、内存、GPU 可用性 |
| 7. 训练建议 | 推荐模型列表、n_jobs 建议、GPU 建议、验证集划分策略 |
| 8. 关键发现 | 至少一条建模相关观察 |

## 数据来源规则

§6 运行环境和 §7 训练建议的数值**必须来自预览工具脚本输出**（`feature-extract-data-preview` skill 的 `preview_competition.py`），禁止用自身判断替代。参考 `feature-extract-data-preview` skill 的"数据权威性规则"。

## 降级策略

- 若某个 section 的信息确实无法从数据中获取，使用"信息不足"或"未提供"标注，但**不能省略该 section 标题**
- 8 个 section 标题必须始终完整出现

## 使用约束

- 此 skill 只负责"格式约束"，数据事实获取使用 `feature-extract-data-preview` skill
- 不在 data_profile 中编造数据事实，只整理已确认的预览结果
- data_profile 是 JSON payload 的 `"data_profile"` 字段值，最终写入 `working/data_profile.md`
