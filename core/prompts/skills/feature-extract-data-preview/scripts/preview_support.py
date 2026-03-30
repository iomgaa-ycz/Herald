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

    return {
        "file_name": normalized_path.name,
        "relative_parent": str(normalized_path.parent.name),
        "total_rows": total_rows,
        "sampled_rows": int(len(dataframe)),
        "column_count": int(len(dataframe.columns)),
        "columns": [str(column) for column in dataframe.columns.tolist()],
        "dtype_counts": _build_dtype_counts(dataframe),
        "missing_columns": missing_columns,
        "numeric_columns": [
            str(column)
            for column in dataframe.select_dtypes(include=("number",)).columns.tolist()
        ],
        "non_numeric_columns": [
            str(column)
            for column in dataframe.select_dtypes(exclude=("number",)).columns.tolist()
        ],
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
        "id_like_columns": [column for column in sample_columns if column in test_columns],
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

    description_path = _resolve_relative_file(normalized_dir, detected_files["description"])
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

    missing_items.sort(key=lambda item: (-int(item["missing_count"]), str(item["column"])))
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


def _render_section(title: str, payload: dict[str, Any]) -> str:
    """渲染 Markdown 区块。"""

    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"## {title}\n```json\n{serialized}\n```"
