---
name: feature-extract-data-preview
description: 在 FeatureExtract 阶段需要稳定预览竞赛数据时使用。适用于读取 `train.csv`、`test.csv`、`sample_submission.csv`、`description.md`，输出文件清单、样本规模、列统计、缺失值、目标列候选与 submission 约束，避免临时拼接一次性的 Bash 或 Python 片段。
---

# FeatureExtract 数据预览

在 `FeatureExtractPES.execute` 阶段，需要先摸清竞赛数据结构，再生成 `task_spec` / `data_profile` 时使用这个 skill。

## 何时使用

- 需要快速确认 `data/` 目录里有哪些关键文件
- 需要稳定预览 `train/test/sample_submission/description`
- 需要拿到后续编写 `data_profile.md` 所需的最小事实
- 想避免在每次运行中重复手写一次性 `python -c` 片段

## 推荐调用顺序

1. 先运行完整预览：

```bash
python .claude/skills/feature-extract-data-preview/scripts/preview_competition.py --data-dir data
```

2. 若某一部分还需要更细粒度信息，再单独调用：

```bash
python .claude/skills/feature-extract-data-preview/scripts/preview_description.py --file data/description.md
python .claude/skills/feature-extract-data-preview/scripts/preview_table.py --file data/train.csv
python .claude/skills/feature-extract-data-preview/scripts/preview_table.py --file data/test.csv
python .claude/skills/feature-extract-data-preview/scripts/preview_submission.py --file data/sample_submission.csv --test-file data/test.csv
```

## 每个脚本负责什么

- `preview_support.py`
  - 共享库；负责关键文件发现、表格统计、description 摘要、submission 约束解析与统一渲染
- `preview_competition.py`
  - 首选入口；一次输出完整预览
- `preview_description.py`
  - 仅输出描述文件预览与 metric 关键词
- `preview_table.py`
  - 仅输出单个表格文件的规模、列、dtype、缺失值与样本记录
- `preview_submission.py`
  - 仅输出 `sample_submission.csv` 的列顺序、目标列候选和行数约束

## 最小输出契约

完整预览至少要覆盖：

- 文件清单
- `train/test` 的总行数、列数、列名、dtype 分布
- 缺失值列及其比例
- `sample_submission.csv` 的列顺序
- 目标列候选
- 若存在 `test.csv`，则 submission 行数应与 test 行数一致

## 使用约束

- 这个 skill 只负责“预览事实”，不负责最终 `data_profile.md` 的固定格式编排
- 若文件缺失，只报告缺失，不要编造内容
- 若输出已足够，不要再额外拼接冗长的临时脚本
