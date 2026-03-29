"""submission.csv 校验单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.pes.submission import (
    load_submission_schema,
    validate_submission_against_sample,
)


def test_valid_submission_passes(tmp_path: Path) -> None:
    """格式正确的 submission 应通过校验。"""

    submission_path = tmp_path / "submission.csv"
    sample_path = tmp_path / "sample_submission.csv"
    content = "id,target\n1,0.9\n2,0.1\n"
    submission_path.write_text(content, encoding="utf-8")
    sample_path.write_text("id,target\n1,0\n2,0\n", encoding="utf-8")

    result = validate_submission_against_sample(submission_path, sample_path)

    assert result.is_valid is True
    assert result.errors == []
    assert result.submission_schema.columns == ["id", "target"]
    assert result.submission_schema.row_count == 2


def test_schema_mismatch_detected(tmp_path: Path) -> None:
    """列顺序或行数不匹配时应返回明确错误。"""

    submission_path = tmp_path / "submission.csv"
    sample_path = tmp_path / "sample_submission.csv"
    submission_path.write_text("target,id\n0.9,1\n", encoding="utf-8")
    sample_path.write_text("id,target\n1,0\n2,0\n", encoding="utf-8")

    result = validate_submission_against_sample(submission_path, sample_path)

    assert result.is_valid is False
    assert len(result.errors) == 2
    assert "列名或列顺序不匹配" in result.errors[0]
    assert "行数不匹配" in result.errors[1]


def test_missing_submission_detected(tmp_path: Path) -> None:
    """缺失 submission.csv 时应抛出明确错误。"""

    sample_path = tmp_path / "sample_submission.csv"
    sample_path.write_text("id,target\n1,0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="文件不存在"):
        load_submission_schema(tmp_path / "missing.csv")


def test_missing_sample_submission_raises(tmp_path: Path) -> None:
    """缺失 sample_submission.csv 时应抛出明确错误。"""

    submission_path = tmp_path / "submission.csv"
    submission_path.write_text("id,target\n1,0.9\n", encoding="utf-8")

    with pytest.raises(ValueError, match="文件不存在"):
        validate_submission_against_sample(
            submission_path,
            tmp_path / "missing_sample_submission.csv",
        )
