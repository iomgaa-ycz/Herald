# 034 增强 FeatureExtract 数据分析深度与运行环境感知

## 元信息
- 状态: draft
- 创建: 2026-03-30
- 负责人: Claude

## 背景

当前 `feature-extract-data-preview` skill 的分析深度不足：仅提供 dtype 分布、缺失值、样本记录等基础统计。导致下游 DraftPES 生成的代码缺乏关键上下文（如 `n_jobs=-1` 在 192 核服务器上导致 LightGBM 训练极慢，本应在数据分析阶段就给出建议）。

需要增强三个方面：
1. **深层特征分析** — 数值统计、基数分析、分布特征、字符串模式检测
2. **运行环境感知** — CPU/GPU/内存探测 + 按数据规模和模型类型给出建议
3. **训练集划分建议** — 是否多折、是否按时间分割、推荐 fold 数

## 变更清单

### 1. `preview_support.py` — 增强特征分析

**文件**: `core/prompts/skills/feature-extract-data-preview/scripts/preview_support.py`

`[MODIFY]` `summarize_table_file()` — 增加返回字段：

```python
# 新增返回字段
"numeric_stats": [                  # 数值特征统计
    {"column": "f_00", "min": -3.8, "max": 4.1, "mean": 0.01, "std": 1.0,
     "q25": -0.67, "q75": 0.68, "skew": 0.02, "nunique": 799000}
],
"categorical_stats": [              # 类别特征统计
    {"column": "f_07", "nunique": 11, "top_values": [0, 1, 2], "dtype": "int64"}
],
"high_cardinality_columns": [...],  # nunique > 1000 的列
"string_pattern_columns": [         # 固定长度字符串特征
    {"column": "f_27", "fixed_length": 10, "char_set": "A-Z", "nunique": 49306}
],
"target_analysis": {                # 目标变量分析（如存在 target 列）
    "column": "target", "task_type": "binary_classification",
    "class_distribution": {"0": 0.514, "1": 0.486}, "is_balanced": true
},
"datetime_columns": [...],         # 检测到的日期/时间列
"constant_columns": [...],         # 方差为 0 的列
"feature_count_by_type": {"numeric": 16, "categorical": 14, "string": 1}
```

新增私有函数（复用已加载的 DataFrame）：
- `_build_numeric_stats(df)` — `describe()` + `skew()` + `nunique()`
- `_build_categorical_stats(df, threshold=50)` — 非数值列或 nunique < threshold 的整数列
- `_detect_string_patterns(df)` — 对 object 列检测固定长度和字符集
- `_analyze_target(df)` — 如存在 `target` 列，判断任务类型和分布
- `_detect_datetime_columns(df)` — `pd.to_datetime` 试探
- `_detect_constant_columns(df)` — `nunique() == 1`

### 2. `preview_support.py` — 新增运行环境探测

`[NEW]` `collect_runtime_environment()` 函数：

```python
def collect_runtime_environment() -> dict[str, Any]:
    """探测本机运行环境。"""
    import multiprocessing
    env = {
        "cpu_count": multiprocessing.cpu_count(),
        "memory_gb": _get_memory_gb(),         # /proc/meminfo 或 sysctl
        "gpu_available": _check_gpu(),          # torch.cuda.is_available()
        "gpu_name": _get_gpu_name(),            # torch.cuda.get_device_name()
        "gpu_memory_gb": _get_gpu_memory_gb(),
    }
    return env
```

### 3. `preview_support.py` — 新增训练建议生成

`[NEW]` `generate_training_recommendations()` 函数：

```python
def generate_training_recommendations(
    table_summary: dict,
    env_info: dict,
    genome_template: str = "tabular",
) -> dict[str, Any]:
```

对 `genome_template == "tabular"`，基于数据规模和硬件生成建议：

**模型资源建议**（参考 `config/genome_templates/tabular.py` 中的常用模型）：

| 模型类型 | GPU 建议 | n_jobs 建议 | 说明 |
|---------|---------|------------|------|
| LightGBM | 不推荐（<500万行） | min(cpu_count, 16) | 线程数超 16 同步开销增大 |
| XGBoost | 可选（>100万行） | min(cpu_count, 16) | GPU `tree_method='gpu_hist'` |
| CatBoost | 可选（>100万行） | - | GPU 原生支持 |
| PyTorch/DL | 强烈推荐（若有GPU） | - | 仅在 GPU 可用时建议使用 |

**验证集划分建议**：
- 检测到日期/时间列 → 推荐时间分割
- 数据量 < 10 万 → 推荐 5-fold
- 数据量 10-100 万 → 推荐 5-fold 或 3-fold
- 数据量 > 100 万 → 推荐 3-fold 或单次 holdout
- 目标不平衡 → 推荐 StratifiedKFold

### 4. `render_preview_report()` — 整合新 section

**文件**: `core/prompts/skills/feature-extract-data-preview/scripts/preview_support.py`

`[MODIFY]` `render_preview_report()` 末尾追加两个 section：
- `## 运行环境` — `collect_runtime_environment()` 结果
- `## 训练建议` — `generate_training_recommendations()` 结果

同步修改 `preview_competition.py` 的调用。

### 5. `SKILL.md` (data-preview) — 更新文档

**文件**: `core/prompts/skills/feature-extract-data-preview/SKILL.md`

`[MODIFY]` 最小输出契约增加：
- 数值特征的统计量（min/max/mean/std/skew）
- 类别特征基数分析
- 目标变量分布分析
- 运行环境信息（CPU 核数、GPU 可用性、内存）
- 训练建议（n_jobs、GPU 使用、验证集划分策略）

### 6. `SKILL.md` (report-format) — 新增 section 结构

**文件**: `core/prompts/skills/feature-extract-report-format/SKILL.md`

`[MODIFY]` 固定标题结构从 6 个 section 扩展为 8 个：

```markdown
# 数据概况报告
## 1. 数据集概览          （不变）
## 2. 特征分析            （增强：加入统计量、基数表格）
## 3. 缺失值              （不变）
## 4. 目标变量            （增强：加入平衡性判断）
## 5. 提交格式            （不变）
## 6. 运行环境            （新增）
## 7. 训练建议            （新增）
## 8. 关键发现与建模建议   （保留，序号变更）
```

新增 section 最小字段：

| Section | 必填字段 |
|---------|----------|
| 6. 运行环境 | CPU 核数、内存、GPU 可用性 |
| 7. 训练建议 | 推荐模型列表、n_jobs 建议、GPU 建议、验证集划分策略 |

### 7. `feature_extract_execute.j2` — 同步模板

**文件**: `config/prompts/templates/feature_extract_execute.j2`

`[MODIFY]` JSON 输出 schema 的 `data_profile` 说明中增加对新增 section 6-7 的要求。

## 不变更的文件

- `tabular.py` — 模板骨架不变，Agent 参考 data_profile 中的建议自行设置参数
- `core/pes/feature_extract.py` — 解析逻辑不需要改，data_profile 仍然是 Markdown 字符串
- `core/workspace.py` — 环境信息由 skill 脚本收集，不需要改 workspace

## 验证计划

1. 直接运行增强后的 preview 脚本验证输出：
   ```bash
   conda run -n herald python core/prompts/skills/feature-extract-data-preview/scripts/preview_competition.py \
     --data-dir workspace/data
   ```
2. 确认输出包含新增的特征统计、运行环境、训练建议
3. 重新运行 `scripts/run_real_l1.sh`，检查：
   - `data_profile.md` 包含 8 个 section
   - DraftPES 生成的 solution.py 中 `n_jobs` 设置合理（非 -1）
   - 训练时间在合理范围内（30-60 分钟而非 4-5 小时）
