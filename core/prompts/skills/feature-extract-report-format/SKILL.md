---
name: feature-extract-report-format
description: 在 FeatureExtract 阶段编写 data_profile 时使用。规定 data_profile.md 的固定标题结构、最小字段覆盖与格式约束，确保下游 DraftPES 能稳定消费。
---

# FeatureExtract 数据报告格式

在 `FeatureExtractPES.execute` 阶段，完成数据预览后编写 `data_profile` 时使用这个 skill。

## 何时使用

- 需要将预览事实整理为 `data_profile` 输出
- 需要确保 `data_profile.md` 可被下游 `DraftPES` 稳定消费
- 想避免输出"一段话总结"导致信息丢失和可读性不足

## 固定标题结构

`data_profile` 的值必须是一段完整的 Markdown 文本，严格遵循以下 6 个 section 的标题和顺序：

```markdown
# 数据概况报告

## 1. 数据集概览
- 竞赛名称: <名称>
- 任务类型: <分类/回归/排序/其他>
- 训练集规模: <行数> 行 x <列数> 列
- 测试集规模: <行数> 行 x <列数> 列

## 2. 特征分析
- 数值特征: <列名列表及类型说明>
- 类别特征: <列名列表及基数>
- 高基数特征: <唯一值 > 1000 的特征及唯一值数>

## 3. 缺失值
- <缺失列名及缺失比例列表>
- 若无缺失值，写"无缺失值"

## 4. 目标变量
- 列名: <target 列名>
- 类型: <连续/二分类/多分类>
- 分布: <类别比例或值域范围>

## 5. 提交格式
- 列顺序: <sample_submission.csv 的列顺序>
- ID 列: <ID 列名>
- 目标列: <预测目标列名>
- 行数约束: <应与 test 行数一致，写明具体数字>

## 6. 关键发现与建模建议
- <竞赛描述中的特殊提示>
- <数据特性对建模方案的影响>
```

## 最小字段覆盖

每个 section 至少要包含以下信息：

| Section | 必填字段 |
|---------|----------|
| 1. 数据集概览 | 竞赛名称、任务类型、训练集规模、测试集规模 |
| 2. 特征分析 | 至少区分数值特征与类别特征 |
| 3. 缺失值 | 明确有无缺失值 |
| 4. 目标变量 | 列名、类型 |
| 5. 提交格式 | 列顺序、目标列 |
| 6. 关键发现 | 至少一条建模相关观察 |

## 降级策略

- 若某个 section 的信息确实无法从数据中获取，使用"信息不足"或"未提供"标注，但**不能省略该 section 标题**
- 6 个 section 标题必须始终完整出现

## 使用约束

- 这个 skill 只负责"格式约束"，数据事实获取请使用 `feature-extract-data-preview` skill
- 不要在 data_profile 中编造数据事实，只整理已确认的预览结果
- data_profile 是 JSON payload 的 `"data_profile"` 字段值，最终会被写入 `working/data_profile.md`
