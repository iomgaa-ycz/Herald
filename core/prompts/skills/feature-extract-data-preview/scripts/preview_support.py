"""FeatureExtract 数据预览共享库。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

_DESCRIPTION_CANDIDATES: tuple[str, ...] = (
    "description.md",
    "README.md",
    "readme.md",
    "overview.md",
    "data_description.md",
)
_METRIC_PATTERNS: tuple[str, ...] = (
    "auc",
    "accuracy",
    "rmse",
    "mae",
    "f1",
    "logloss",
    "mse",
    "roc_auc",
)


def list_visible_files(data_dir: Path, limit: int = 50) -> list[str]:
    """列出数据目录下可见文件。

    Args:
        data_dir: 数据目录。
        limit: 最多返回多少个相对路径。

    Returns:
        排序后的相对路径列表。
    """

    normalized_dir = data_dir.expanduser().resolve()
    files = [
        str(path.relative_to(normalized_dir))
        for path in normalized_dir.rglob("*")
        if path.is_file()
    ]
    return sorted(files)[:limit]


def find_common_competition_files(data_dir: Path) -> dict[str, str]:
    """查找竞赛目录中的常见关键文件。

    Args:
        data_dir: 数据目录。

    Returns:
        `description` / `train` / `test` / `sample_submission` 到相对路径的映射。
        未找到时值为空字符串。
    """

    normalized_dir = data_dir.expanduser().resolve()
    files = [path for path in normalized_dir.rglob("*") if path.is_file()]

    detected = {
        "description": "",
        "train": "",
        "test": "",
        "sample_submission": "",
    }

    detected["description"] = _find_first_match(
        base_dir=normalized_dir,
        files=files,
        exact_names=_DESCRIPTION_CANDIDATES,
        keywords=("description", "readme", "overview"),
        suffixes=(".md", ".txt"),
    )
    detected["train"] = _find_first_match(
        base_dir=normalized_dir,
        files=files,
        exact_names=("train.csv",),
        keywords=("train",),
        suffixes=(".csv",),
    )
    detected["test"] = _find_first_match(
        base_dir=normalized_dir,
        files=files,
        exact_names=("test.csv",),
        keywords=("test",),
        suffixes=(".csv",),
    )
    detected["sample_submission"] = _find_first_match(
        base_dir=normalized_dir,
        files=files,
        exact_names=("sample_submission.csv",),
        keywords=("sample", "submission"),
        suffixes=(".csv",),
    )
    return detected


def summarize_table_file(
    csv_path: Path,
    sample_rows: int = 5,
    profile_rows: int = 2000,
) -> dict[str, Any]:
    """汇总表格文件预览。

    Args:
        csv_path: CSV 文件路径。
        sample_rows: 输出多少条样本记录。
        profile_rows: 最多读取多少行用于统计。

    Returns:
        供 Skill 直接输出的结构化摘要。
    """

    normalized_path = csv_path.expanduser().resolve()
    dataframe = pd.read_csv(normalized_path, nrows=profile_rows, low_memory=False)
    total_rows = _count_csv_rows(normalized_path)
    missing_columns = _build_missing_columns(dataframe)

    numeric_cols = dataframe.select_dtypes(include=("number",)).columns.tolist()
    non_numeric_cols = dataframe.select_dtypes(exclude=("number",)).columns.tolist()

    return {
        "file_name": normalized_path.name,
        "relative_parent": str(normalized_path.parent.name),
        "total_rows": total_rows,
        "sampled_rows": int(len(dataframe)),
        "column_count": int(len(dataframe.columns)),
        "columns": [str(column) for column in dataframe.columns.tolist()],
        "dtype_counts": _build_dtype_counts(dataframe),
        "missing_columns": missing_columns,
        "numeric_columns": [str(c) for c in numeric_cols],
        "non_numeric_columns": [str(c) for c in non_numeric_cols],
        "numeric_stats": _build_numeric_stats(dataframe),
        "categorical_stats": _build_categorical_stats(dataframe),
        "high_cardinality_columns": [
            str(c) for c in dataframe.columns if dataframe[c].nunique() > 1000
        ],
        "string_pattern_columns": _detect_string_patterns(dataframe),
        "target_analysis": _analyze_target(dataframe),
        "datetime_columns": _detect_datetime_columns(dataframe),
        "constant_columns": _detect_constant_columns(dataframe),
        "feature_count_by_type": {
            "numeric": len(numeric_cols),
            "non_numeric": len(non_numeric_cols),
        },
        "sample_records": _to_serializable_records(
            dataframe=dataframe,
            sample_rows=sample_rows,
        ),
    }


def summarize_description_file(
    file_path: Path,
    max_lines: int = 40,
) -> dict[str, Any]:
    """汇总描述文件预览。

    Args:
        file_path: 描述文件路径。
        max_lines: 最多读取多少行。

    Returns:
        描述文件的结构化摘要。
    """

    normalized_path = file_path.expanduser().resolve()
    lines = normalized_path.read_text(encoding="utf-8").splitlines()
    preview_lines = lines[:max_lines]
    preview_text = "\n".join(preview_lines).strip()
    detected_metrics = sorted(
        {
            pattern
            for pattern in _METRIC_PATTERNS
            if re.search(rf"\b{re.escape(pattern)}\b", preview_text, re.IGNORECASE)
        }
    )

    return {
        "file_name": normalized_path.name,
        "line_count": len(lines),
        "preview": preview_text,
        "detected_metric_keywords": detected_metrics,
    }


def summarize_submission_constraints(
    sample_submission_path: Path,
    test_path: Path | None = None,
) -> dict[str, Any]:
    """汇总 submission 约束。

    Args:
        sample_submission_path: `sample_submission.csv` 路径。
        test_path: 可选的 `test.csv` 路径。

    Returns:
        submission 的结构化约束摘要。
    """

    sample_path = sample_submission_path.expanduser().resolve()
    sample_dataframe = pd.read_csv(sample_path, nrows=20, low_memory=False)
    sample_columns = [str(column) for column in sample_dataframe.columns.tolist()]

    test_columns: list[str] = []
    expected_test_rows: int | None = None
    if test_path is not None and test_path.exists():
        normalized_test_path = test_path.expanduser().resolve()
        test_dataframe = pd.read_csv(normalized_test_path, nrows=20, low_memory=False)
        test_columns = [str(column) for column in test_dataframe.columns.tolist()]
        expected_test_rows = _count_csv_rows(normalized_test_path)

    target_columns = [
        column for column in sample_columns if column not in set(test_columns)
    ]
    if not target_columns and len(sample_columns) > 1:
        target_columns = sample_columns[1:]

    return {
        "file_name": sample_path.name,
        "total_rows": _count_csv_rows(sample_path),
        "column_order": sample_columns,
        "target_columns": target_columns,
        "id_like_columns": [
            column for column in sample_columns if column in test_columns
        ],
        "row_count_should_match_test": expected_test_rows,
        "sample_records": _to_serializable_records(
            dataframe=sample_dataframe,
            sample_rows=5,
        ),
    }


def render_preview_report(
    data_dir: Path,
    sample_rows: int = 5,
    profile_rows: int = 2000,
) -> str:
    """渲染完整竞赛预览报告。

    Args:
        data_dir: 数据目录。
        sample_rows: 表格样本记录数。
        profile_rows: 表格统计最多读取行数。

    Returns:
        Markdown 文本，供 Agent 直接阅读。
    """

    normalized_dir = data_dir.expanduser().resolve()
    detected_files = find_common_competition_files(normalized_dir)
    sections = [
        _render_section(
            title="文件清单",
            payload={
                "data_dir": str(normalized_dir),
                "visible_files": list_visible_files(normalized_dir),
                "detected_files": detected_files,
            },
        )
    ]

    description_path = _resolve_relative_file(
        normalized_dir, detected_files["description"]
    )
    if description_path is not None:
        sections.append(
            _render_section(
                title="描述文件预览",
                payload=summarize_description_file(description_path),
            )
        )

    train_path = _resolve_relative_file(normalized_dir, detected_files["train"])
    if train_path is not None:
        sections.append(
            _render_section(
                title="train 预览",
                payload=summarize_table_file(
                    csv_path=train_path,
                    sample_rows=sample_rows,
                    profile_rows=profile_rows,
                ),
            )
        )

    test_path = _resolve_relative_file(normalized_dir, detected_files["test"])
    if test_path is not None:
        sections.append(
            _render_section(
                title="test 预览",
                payload=summarize_table_file(
                    csv_path=test_path,
                    sample_rows=sample_rows,
                    profile_rows=profile_rows,
                ),
            )
        )

    submission_path = _resolve_relative_file(
        normalized_dir,
        detected_files["sample_submission"],
    )
    if submission_path is not None:
        sections.append(
            _render_section(
                title="sample_submission 约束",
                payload=summarize_submission_constraints(
                    sample_submission_path=submission_path,
                    test_path=test_path,
                ),
            )
        )

    # 运行环境
    env_info = collect_runtime_environment()
    sections.append(_render_section(title="运行环境", payload=env_info))

    # 训练建议（基于 train 数据摘要和环境信息）
    if train_path is not None:
        train_summary = summarize_table_file(
            csv_path=train_path,
            sample_rows=0,
            profile_rows=profile_rows,
        )
        recommendations = generate_training_recommendations(
            table_summary=train_summary,
            env_info=env_info,
        )
        sections.append(_render_section(title="训练建议", payload=recommendations))

    return "\n\n".join(sections).strip()


def _find_first_match(
    base_dir: Path,
    files: list[Path],
    exact_names: tuple[str, ...],
    keywords: tuple[str, ...],
    suffixes: tuple[str, ...],
) -> str:
    """按优先级搜索文件。"""

    exact_name_map = {name.lower(): name for name in exact_names}

    for file_path in sorted(files):
        lower_name = file_path.name.lower()
        if lower_name in exact_name_map:
            return str(file_path.relative_to(base_dir))

    for file_path in sorted(files):
        lower_name = file_path.name.lower()
        if not lower_name.endswith(suffixes):
            continue
        if all(keyword in lower_name for keyword in keywords):
            return str(file_path.relative_to(base_dir))

    return ""


def _resolve_relative_file(data_dir: Path, relative_path: str) -> Path | None:
    """将相对路径解析为绝对路径。"""

    if not relative_path:
        return None

    file_path = data_dir / relative_path
    if not file_path.exists():
        return None
    return file_path


def _count_csv_rows(file_path: Path) -> int | None:
    """统计 CSV 数据行数（不含表头）。"""

    with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
        line_count = sum(1 for _ in handle)
    return max(line_count - 1, 0)


def _build_dtype_counts(dataframe: pd.DataFrame) -> dict[str, int]:
    """统计 dtype 分布。"""

    counts: dict[str, int] = {}
    for dtype in dataframe.dtypes:
        dtype_name = str(dtype)
        counts[dtype_name] = counts.get(dtype_name, 0) + 1
    return counts


def _build_missing_columns(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    """构建缺失值摘要。"""

    missing_items: list[dict[str, Any]] = []
    total_rows = max(len(dataframe), 1)

    for column in dataframe.columns:
        missing_count = int(dataframe[column].isna().sum())
        if missing_count <= 0:
            continue
        missing_items.append(
            {
                "column": str(column),
                "missing_count": missing_count,
                "missing_ratio": round(missing_count / total_rows, 6),
            }
        )

    missing_items.sort(
        key=lambda item: (-int(item["missing_count"]), str(item["column"]))
    )
    return missing_items


def _to_serializable_records(
    dataframe: pd.DataFrame,
    sample_rows: int,
) -> list[dict[str, Any]]:
    """将样本记录转换为 JSON 可序列化对象。"""

    preview_frame = dataframe.head(sample_rows).copy()
    preview_frame = preview_frame.where(pd.notna(preview_frame), None)
    preview_json = preview_frame.to_json(orient="records", force_ascii=False)
    raw_records = json.loads(preview_json)
    return [dict(record) for record in raw_records]


def _build_numeric_stats(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    """构建数值特征统计摘要。

    Args:
        dataframe: 已加载的 DataFrame。

    Returns:
        每个数值列的 min/max/mean/std/q25/q75/skew/nunique。
    """

    numeric_df = dataframe.select_dtypes(include=("number",))
    if numeric_df.empty:
        return []

    desc = numeric_df.describe().T
    skew_values = numeric_df.skew()
    nunique_values = numeric_df.nunique()

    stats: list[dict[str, Any]] = []
    for col in numeric_df.columns:
        entry: dict[str, Any] = {"column": str(col)}
        if col in desc.index:
            entry["min"] = round(float(desc.loc[col, "min"]), 4)
            entry["max"] = round(float(desc.loc[col, "max"]), 4)
            entry["mean"] = round(float(desc.loc[col, "mean"]), 4)
            entry["std"] = round(float(desc.loc[col, "std"]), 4)
            entry["q25"] = round(float(desc.loc[col, "25%"]), 4)
            entry["q75"] = round(float(desc.loc[col, "75%"]), 4)
        if col in skew_values.index:
            entry["skew"] = round(float(skew_values[col]), 4)
        entry["nunique"] = int(nunique_values.get(col, 0))
        stats.append(entry)
    return stats


def _build_categorical_stats(
    dataframe: pd.DataFrame,
    cardinality_threshold: int = 50,
) -> list[dict[str, Any]]:
    """构建类别特征统计摘要。

    对非数值列以及 nunique < cardinality_threshold 的整数列进行统计。

    Args:
        dataframe: 已加载的 DataFrame。
        cardinality_threshold: 整数列被视为类别的基数阈值。

    Returns:
        每个类别列的 nunique、top_values、dtype。
    """

    stats: list[dict[str, Any]] = []

    # 非数值列
    non_numeric = dataframe.select_dtypes(exclude=("number",))
    for col in non_numeric.columns:
        nunique = int(dataframe[col].nunique())
        top_values = dataframe[col].value_counts().head(5).index.tolist()
        stats.append(
            {
                "column": str(col),
                "nunique": nunique,
                "top_values": [str(v) for v in top_values],
                "dtype": str(dataframe[col].dtype),
            }
        )

    # 低基数整数列
    int_cols = dataframe.select_dtypes(include=("integer",))
    for col in int_cols.columns:
        nunique = int(dataframe[col].nunique())
        if nunique < cardinality_threshold:
            top_values = dataframe[col].value_counts().head(5).index.tolist()
            stats.append(
                {
                    "column": str(col),
                    "nunique": nunique,
                    "top_values": [int(v) for v in top_values],
                    "dtype": str(dataframe[col].dtype),
                }
            )

    return stats


def _detect_string_patterns(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    """检测固定长度字符串特征模式。

    Args:
        dataframe: 已加载的 DataFrame。

    Returns:
        固定长度字符串列的 column/fixed_length/char_set/nunique。
    """

    object_cols = dataframe.select_dtypes(include=("object",))
    patterns: list[dict[str, Any]] = []

    for col in object_cols.columns:
        sample = dataframe[col].dropna().head(200)
        if sample.empty:
            continue

        lengths = sample.str.len()
        if lengths.nunique() == 1:
            fixed_len = int(lengths.iloc[0])
            all_chars = set("".join(sample.astype(str).tolist()))
            if all_chars.issubset(set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")):
                char_set = "A-Z"
            elif all_chars.issubset(set("abcdefghijklmnopqrstuvwxyz")):
                char_set = "a-z"
            elif all_chars.issubset(set("0123456789")):
                char_set = "0-9"
            else:
                char_set = "".join(sorted(all_chars)[:20])

            patterns.append(
                {
                    "column": str(col),
                    "fixed_length": fixed_len,
                    "char_set": char_set,
                    "nunique": int(dataframe[col].nunique()),
                }
            )

    return patterns


def _analyze_target(dataframe: pd.DataFrame) -> dict[str, Any] | None:
    """分析目标变量。

    Args:
        dataframe: 已加载的 DataFrame。

    Returns:
        目标变量的 column/task_type/class_distribution/is_balanced，
        若无 target 列返回 None。
    """

    if "target" not in dataframe.columns:
        return None

    target = dataframe["target"]
    nunique = int(target.nunique())

    if nunique == 2:
        task_type = "binary_classification"
    elif 2 < nunique <= 20:
        task_type = "multiclass_classification"
    else:
        task_type = "regression"

    result: dict[str, Any] = {
        "column": "target",
        "task_type": task_type,
        "nunique": nunique,
    }

    if task_type in ("binary_classification", "multiclass_classification"):
        dist = target.value_counts(normalize=True).to_dict()
        result["class_distribution"] = {
            str(k): round(float(v), 4) for k, v in dist.items()
        }
        min_ratio = min(dist.values())
        max_ratio = max(dist.values())
        result["is_balanced"] = (max_ratio / max(min_ratio, 1e-9)) < 3.0
    else:
        result["value_range"] = {
            "min": round(float(target.min()), 4),
            "max": round(float(target.max()), 4),
            "mean": round(float(target.mean()), 4),
            "std": round(float(target.std()), 4),
        }

    return result


def _detect_datetime_columns(dataframe: pd.DataFrame) -> list[str]:
    """检测可能的日期/时间列。

    Args:
        dataframe: 已加载的 DataFrame。

    Returns:
        被检测为日期/时间的列名列表。
    """

    datetime_cols: list[str] = []
    candidates = dataframe.select_dtypes(include=("object",)).columns.tolist()

    # 也包含已识别为 datetime 的列
    for col in dataframe.columns:
        if pd.api.types.is_datetime64_any_dtype(dataframe[col]):
            datetime_cols.append(str(col))

    for col in candidates:
        sample = dataframe[col].dropna().head(20)
        if sample.empty:
            continue
        try:
            pd.to_datetime(sample, infer_datetime_format=True)
            datetime_cols.append(str(col))
        except (ValueError, TypeError):
            continue

    return datetime_cols


def _detect_constant_columns(dataframe: pd.DataFrame) -> list[str]:
    """检测常量列（nunique == 1）。

    Args:
        dataframe: 已加载的 DataFrame。

    Returns:
        常量列名列表。
    """

    return [str(col) for col in dataframe.columns if dataframe[col].nunique() <= 1]


def collect_runtime_environment() -> dict[str, Any]:
    """探测本机运行环境。

    Returns:
        CPU 核数、内存、GPU 可用性等硬件信息。
    """

    import multiprocessing
    import platform

    cpu_count = multiprocessing.cpu_count()
    recommended_n_jobs = min(cpu_count, 16)

    env: dict[str, Any] = {
        "cpu_count": cpu_count,
        "recommended_n_jobs": recommended_n_jobs,
        "platform": platform.system(),
        "memory_gb": _get_memory_gb(),
        "gpu_available": False,
        "gpu_name": None,
        "gpu_memory_gb": None,
    }

    env.update(_detect_gpu_via_nvidia_smi())

    return env


def _detect_gpu_via_nvidia_smi() -> dict[str, Any]:
    """通过 nvidia-smi 检测 GPU（torch 未安装时的 fallback）。"""

    import subprocess

    result: dict[str, Any] = {
        "gpu_available": False,
        "gpu_name": None,
        "gpu_memory_gb": None,
    }
    try:
        output = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if output.returncode == 0 and output.stdout.strip():
            line = output.stdout.strip().split("\n")[0]
            name, mem_mb = line.split(",", 1)
            result["gpu_available"] = True
            result["gpu_name"] = name.strip()
            result["gpu_memory_gb"] = round(float(mem_mb.strip()) / 1024, 1)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return result


def _get_memory_gb() -> float | None:
    """获取系统内存大小（GB）。"""

    try:
        import psutil

        return round(psutil.virtual_memory().total / (1024**3), 1)
    except ImportError:
        pass

    # Linux fallback
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    return round(kb / (1024**2), 1)
    except (FileNotFoundError, ValueError):
        pass

    # macOS fallback
    import subprocess

    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return round(int(result.stdout.strip()) / (1024**3), 1)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass

    return None


def generate_training_recommendations(
    table_summary: dict[str, Any],
    env_info: dict[str, Any],
) -> dict[str, Any]:
    """根据数据规模和硬件生成表格竞赛训练建议。

    Args:
        table_summary: summarize_table_file() 返回的摘要。
        env_info: collect_runtime_environment() 返回的环境信息。

    Returns:
        模型资源建议和验证集划分建议。
    """

    total_rows = table_summary.get("total_rows") or 0
    cpu_count = env_info.get("cpu_count") or 4
    gpu_available = env_info.get("gpu_available", False)
    recommended_n_jobs = min(cpu_count, 16)

    # 模型资源建议
    model_recommendations: list[dict[str, Any]] = [
        {
            "model": "LightGBM",
            "use_gpu": False,
            "n_jobs": recommended_n_jobs,
            "note": f"线程数建议 {recommended_n_jobs}（服务器 {cpu_count} 核，超 16 线程同步开销增大）",
        },
        {
            "model": "XGBoost",
            "use_gpu": gpu_available and total_rows > 1_000_000,
            "n_jobs": recommended_n_jobs,
            "note": "GPU tree_method='gpu_hist' 在 >100 万行时有优势"
            if gpu_available
            else f"无 GPU，CPU 模式 n_jobs={recommended_n_jobs}",
        },
        {
            "model": "CatBoost",
            "use_gpu": gpu_available and total_rows > 1_000_000,
            "n_jobs": None,
            "note": "GPU 原生支持" if gpu_available else "CPU 模式",
        },
    ]

    if gpu_available:
        model_recommendations.append(
            {
                "model": "PyTorch/NN",
                "use_gpu": True,
                "n_jobs": None,
                "note": "深度学习强烈推荐使用 GPU",
            }
        )

    # 验证集划分建议
    target_analysis = table_summary.get("target_analysis")
    datetime_cols = table_summary.get("datetime_columns", [])

    if datetime_cols:
        split_strategy = "time_based_split"
        split_note = f"检测到时间列 {datetime_cols}，推荐按时间顺序划分"
        n_folds = None
    elif total_rows > 1_000_000:
        split_strategy = "holdout_or_3fold"
        split_note = (
            f"数据量 {total_rows:,} 行较大，推荐 3-fold 或单次 holdout（节省时间）"
        )
        n_folds = 3
    elif total_rows > 100_000:
        split_strategy = "stratified_kfold"
        split_note = "推荐 5-fold 或 3-fold CV"
        n_folds = 5
    else:
        split_strategy = "stratified_kfold"
        split_note = "数据量较小，推荐 5-fold 充分利用数据"
        n_folds = 5

    use_stratified = False
    if target_analysis and target_analysis.get("task_type") in (
        "binary_classification",
        "multiclass_classification",
    ):
        use_stratified = True
        if not target_analysis.get("is_balanced", True):
            split_note += "；目标不平衡，必须使用 StratifiedKFold"

    return {
        "model_recommendations": model_recommendations,
        "validation_split": {
            "strategy": split_strategy,
            "n_folds": n_folds,
            "use_stratified": use_stratified,
            "note": split_note,
        },
        "general_n_jobs": recommended_n_jobs,
    }


def _render_section(title: str, payload: dict[str, Any]) -> str:
    """渲染 Markdown 区块。"""

    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"## {title}\n```json\n{serialized}\n```"
