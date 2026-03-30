---
name: feature-extract-data-preview
description: >-
  This skill should be used when the FeatureExtract Agent needs to
  "preview competition data", "analyze train.csv", "detect data types",
  "check missing values", "profile table statistics", or "collect runtime
  environment info". Provides deterministic scripts for stable data
  previewing, avoiding ad-hoc Bash/Python snippets.
---

# FeatureExtract 数据预览

在 `FeatureExtractPES.execute` 阶段，摸清竞赛数据结构并生成 `task_spec` / `data_profile` 时使用。

## 何时使用

- 确认 `data/` 目录中的关键文件清单
- 稳定预览 `train/test/sample_submission/description`
- 获取编写 `data_profile.md` 所需的最小事实集
- 避免每次运行中重复手写一次性 `python -c` 片段

## 推荐调用顺序

1. 运行完整预览（首选入口）：

```bash
python .claude/skills/feature-extract-data-preview/scripts/preview_competition.py --data-dir data
```

2. 若需更细粒度信息，单独调用子脚本：

```bash
python .claude/skills/feature-extract-data-preview/scripts/preview_description.py --file data/description.md
python .claude/skills/feature-extract-data-preview/scripts/preview_table.py --file data/train.csv
python .claude/skills/feature-extract-data-preview/scripts/preview_table.py --file data/test.csv
python .claude/skills/feature-extract-data-preview/scripts/preview_submission.py --file data/sample_submission.csv --test-file data/test.csv
```

## 脚本职责

| 脚本 | 职责 |
|------|------|
| `preview_support.py` | 共享库：关键文件发现、表格统计、description 摘要、submission 约束解析、运行环境检测、训练建议生成、统一渲染 |
| `preview_competition.py` | 首选入口：一次输出完整预览（含运行环境和训练建议） |
| `preview_description.py` | 仅输出描述文件预览与 metric 关键词 |
| `preview_table.py` | 仅输出单个表格文件的规模、列、dtype、缺失值与样本记录 |
| `preview_submission.py` | 仅输出 `sample_submission.csv` 的列顺序、目标列候选和行数约束 |

## 最小输出契约

完整预览至少覆盖：

- 文件清单
- `train/test` 的总行数、列数、列名、dtype 分布
- 缺失值列及其比例
- 数值特征统计量（min/max/mean/std/skew/nunique）
- 类别特征基数分析（nunique、top_values）
- 高基数列与固定长度字符串模式检测
- 目标变量分布分析（任务类型、类别比例、平衡性）
- 日期/时间列检测
- `sample_submission.csv` 的列顺序与目标列候选
- 若存在 `test.csv`，submission 行数应与 test 行数一致
- 运行环境信息（CPU 核数、内存、GPU 可用性及型号）
- 训练建议（推荐模型的 n_jobs/GPU 配置、验证集划分策略）

## 数据权威性规则

脚本输出的以下字段是经过硬件检测和算法计算的**权威值**，编写 data_profile 时**必须忠实引用，禁止用自身推断覆写**：

- **运行环境**：CPU 核数、内存大小、GPU 型号与显存（来自 `collect_runtime_environment()`）
- **训练建议**：n_jobs 推荐值、GPU 配置建议、验证策略（来自 `generate_training_recommendations()`）
- **数值统计量**：min/max/mean/std/skew/nunique（来自 `_build_numeric_stats()`）

违反此规则的典型错误：脚本输出 `n_jobs: 16`，但 data_profile 中写成 `n_jobs: -1`。

## 使用约束

- 此 skill 只负责"预览事实"，不负责最终 `data_profile.md` 的固定格式编排（格式由 `feature-extract-report-format` skill 定义）
- 若文件缺失，只报告缺失，不编造内容
- 若输出已足够，不再额外拼接冗长的临时脚本
