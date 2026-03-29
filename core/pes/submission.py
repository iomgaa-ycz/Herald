"""submission.csv 校验工具。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SubmissionSchema:
    """submission.csv 的最小 schema。"""

    columns: list[str]
    row_count: int


@dataclass(slots=True)
class SubmissionValidationResult:
    """submission 校验结果。"""

    is_valid: bool
    errors: list[str]
    submission_schema: SubmissionSchema
    sample_schema: SubmissionSchema


def load_submission_schema(csv_path: str | Path) -> SubmissionSchema:
    """读取 CSV 的列名与行数。"""

    resolved_path = Path(csv_path).expanduser().resolve()
    if not resolved_path.exists():
        raise ValueError(f"submission 文件不存在: {resolved_path}")

    with resolved_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        try:
            header = next(reader)
        except StopIteration as error:
            raise ValueError(f"submission 文件为空: {resolved_path}") from error

        columns = [column.strip() for column in header]
        if not any(columns):
            raise ValueError(f"submission 表头为空: {resolved_path}")

        row_count = sum(1 for _ in reader)

    return SubmissionSchema(columns=columns, row_count=row_count)


def validate_submission_against_sample(
    submission_path: str | Path,
    sample_submission_path: str | Path,
) -> SubmissionValidationResult:
    """使用 sample_submission.csv 校验 submission.csv。"""

    submission_schema = load_submission_schema(submission_path)
    sample_schema = load_submission_schema(sample_submission_path)

    errors: list[str] = []
    if submission_schema.columns != sample_schema.columns:
        errors.append(
            "列名或列顺序不匹配: "
            f"expected={sample_schema.columns}, actual={submission_schema.columns}"
        )
    if submission_schema.row_count != sample_schema.row_count:
        errors.append(
            "行数不匹配: "
            f"expected={sample_schema.row_count}, actual={submission_schema.row_count}"
        )

    return SubmissionValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        submission_schema=submission_schema,
        sample_schema=sample_schema,
    )
