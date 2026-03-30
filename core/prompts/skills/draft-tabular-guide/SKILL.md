---
name: draft-tabular-guide
description: >-
  This skill should be used when the Draft Agent needs to "write solution.py
  for a tabular competition", "configure LightGBM/XGBoost parameters",
  "set n_jobs based on hardware", "choose validation strategy",
  "translate data_profile recommendations into code", or "avoid common
  tabular ML pitfalls". Provides hardware-aware parameter mapping and
  tabular competition best practices.
---

# 表格竞赛 Draft 指南

在 `DraftPES.execute` 阶段为表格（tabular）竞赛编写 `solution.py` 时使用。核心职责：将 `data_profile` 中的分析结论和资源建议翻译为正确的代码参数。

## 核心原则

1. **data_profile 是唯一真值来源** — 所有资源参数必须来自 data_profile §6（运行环境）和 §7（训练建议），不使用默认值或自行推断
2. **MVP 优先** — 先跑通 baseline，再优化
3. **禁止 n_jobs=-1** — 在高核数服务器上会导致线程同步灾难

## 资源参数映射表

从 data_profile §7 提取参数并映射到代码：

### LightGBM

| data_profile 字段 | 代码参数 | 映射规则 |
|-------------------|---------|---------|
| §7 n_jobs 建议值 N | `LGBMClassifier(n_jobs=N)` 或 `lgb.train(params={..., "num_threads": N})` | 直接使用推荐值 |
| §7 GPU 建议: 不使用 | 不设 GPU 参数 | LightGBM GPU 在中小数据集上无优势 |
| §7 GPU 建议: 使用 | `device='gpu'` | 仅在 §7 明确建议时启用 |

### XGBoost

| data_profile 字段 | 代码参数 | 映射规则 |
|-------------------|---------|---------|
| §7 n_jobs 建议值 N | `XGBClassifier(nthread=N)` 或 `xgb.train(params={..., "nthread": N})` | 直接使用推荐值 |
| §7 GPU 建议: 使用 | `tree_method='gpu_hist', device='cuda'` | 仅在 §7 明确建议且 §6 确认 GPU 可用时 |
| §7 GPU 建议: 不使用 | `tree_method='hist'` | 默认 CPU 模式 |

### CatBoost

| data_profile 字段 | 代码参数 | 映射规则 |
|-------------------|---------|---------|
| §7 GPU 建议: 使用 | `task_type='GPU'` | CatBoost GPU 原生支持 |
| §7 GPU 建议: 不使用 | 不设 task_type | 默认 CPU |

### 验证策略

| data_profile 字段 | 代码参数 | 映射规则 |
|-------------------|---------|---------|
| §7 策略: stratified_kfold, N 折 | `StratifiedKFold(n_splits=N, shuffle=True, random_state=42)` | 分类任务标配 |
| §7 策略: time_based_split | 按时间列排序后 `train_test_split` | 不 shuffle |
| §7 策略: holdout_or_3fold | `StratifiedKFold(n_splits=3)` 或 `train_test_split(test_size=0.2)` | 大数据集节省时间 |

## 常见反模式（必须避免）

### 1. n_jobs=-1 灾难

```python
# 错误：在 192 核服务器上导致训练时间从 30 分钟膨胀到 5+ 小时
model = LGBMClassifier(n_jobs=-1)

# 正确：使用 data_profile §7 的推荐值
model = LGBMClassifier(n_jobs=16)  # §7 建议值
```

**原因**：OpenMP 线程同步开销随核数非线性增长，超过 16 线程后收益递减甚至为负。

### 2. 忽略 data_profile 直接用默认参数

```python
# 错误：忽略 §7 的 GPU 建议
model = XGBClassifier()  # 默认 CPU，但 §7 可能建议用 GPU

# 正确：根据 §7 设置
model = XGBClassifier(tree_method='gpu_hist', device='cuda', nthread=16)
```

### 3. GPU 不可用时强制 GPU

```python
# 错误：§6 显示无 GPU 但仍设置 GPU 参数
model = XGBClassifier(tree_method='gpu_hist')  # 会报错

# 正确：先检查 §6 运行环境
model = XGBClassifier(tree_method='hist', nthread=16)
```

## 表格竞赛 MVP 代码结构

```python
# Phase 1: 数据加载
# 参考 data_profile §1 的数据规模和 §5 的提交格式
train = pd.read_csv("data/train.csv")
test = pd.read_csv("data/test.csv")

# Phase 2: 特征工程
# 参考 data_profile §2 的特征分析（数值/类别/高基数/字符串模式）
# 参考 data_profile §3 的缺失值情况

# Phase 3: 模型训练
# 参考 data_profile §7 设置所有资源参数
# n_jobs, GPU, 验证折数 必须与 §7 一致

# Phase 4: 预测与提交
# 参考 data_profile §5 的列顺序和 ID 列
submission = pd.DataFrame({"id": test["id"], "target": predictions})
submission.to_csv("submission.csv", index=False)
```

## data_profile 各 Section 在代码中的用途

| Section | 代码用途 |
|---------|---------|
| §1 数据集概览 | 确定任务类型（分类/回归）→ 选择模型类和损失函数 |
| §2 特征分析 | 特征工程策略：数值标准化、类别编码、高基数处理 |
| §3 缺失值 | 是否需要填充、填充策略 |
| §4 目标变量 | 损失函数、评估指标、是否需要采样策略 |
| §5 提交格式 | submission.csv 的列名、列顺序、行数 |
| §6 运行环境 | 决定是否可用 GPU、内存是否足够一次加载 |
| §7 训练建议 | **n_jobs、GPU 配置、验证折数** — 必须严格遵循 |
| §8 关键发现 | 特殊处理提示（如交互特征、时间依赖等） |

## 扩展说明

当前仅覆盖表格竞赛。未来如需支持其他竞赛类型，创建对应 skill：
- `draft-cv-guide/` — 计算机视觉竞赛（backbone 选择、数据增强、GPU 内存管理）
- `draft-nlp-guide/` — 自然语言处理竞赛（tokenizer、混合精度、transformer 配置）
