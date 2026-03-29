"""MLE-Bench 评分模块单元测试。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.database.herald_db import HeraldDB
from core.pes.types import PESSolution
from core.utils.utils import utc_now_iso
from tests.grading import (
    GradingConfig,
    GradingResult,
    MLEBenchGradingHook,
    grading_result_to_record,
    infer_competition_id,
    infer_data_dir,
)


@dataclass(slots=True)
class _DummyWorkspace:
    """最小 workspace 测试桩。"""

    logs_dir: Path


@dataclass(slots=True)
class _DummyContext:
    """最小 hook context 测试桩。"""

    solution: PESSolution
    workspace: _DummyWorkspace | None = None
    db: HeraldDB | None = None
    runtime_context: dict[str, object] | None = None


def test_grading_config_defaults() -> None:
    """GradingConfig 默认值符合 Task 11 约定。"""

    config = GradingConfig()

    assert config.enabled is True
    assert config.accepted_statuses == ("completed", "success")


def test_grading_result_fields_complete() -> None:
    """GradingResult 覆盖 Task 11 所需字段。"""

    result = GradingResult(
        competition_id="demo-comp",
        test_score=0.88,
        test_score_direction="max",
        test_valid_submission=True,
        test_medal_level="silver",
        test_above_median=True,
        gold_threshold=0.95,
        silver_threshold=0.9,
        bronze_threshold=0.8,
        median_threshold=0.5,
        graded_at=utc_now_iso(),
    )

    assert result.competition_id == "demo-comp"
    assert result.test_score == 0.88
    assert result.test_valid_submission is True
    assert result.test_medal_level == "silver"
    assert result.graded_at is not None


def test_fallback_from_competition_root(tmp_path: Path) -> None:
    """可从 competition root 推断 competition_id 与 data_dir。"""

    competition_dir = tmp_path / "demo-comp"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "prepared" / "public").mkdir(parents=True, exist_ok=True)

    assert infer_competition_id(competition_dir) == "demo-comp"
    assert infer_data_dir(competition_dir) == tmp_path


def test_fallback_from_prepared_public(tmp_path: Path) -> None:
    """prepared/public 路径也能正确回退。"""

    public_dir = tmp_path / "demo-comp" / "prepared" / "public"
    public_dir.mkdir(parents=True, exist_ok=True)

    assert infer_competition_id(public_dir) == "demo-comp"
    assert infer_data_dir(public_dir) == tmp_path


def test_missing_submission_skips_safely(tmp_path: Path) -> None:
    """缺 submission.csv 时安全跳过。"""

    solution = PESSolution(
        id="solution-001",
        operation="draft",
        generation=0,
        status="completed",
        created_at=utc_now_iso(),
        parent_ids=[],
        lineage="solution",
        run_id="run-001",
        submission_file_path=str(tmp_path / "missing.csv"),
    )
    context = _DummyContext(solution=solution, workspace=_DummyWorkspace(tmp_path))

    result = MLEBenchGradingHook()(context)

    assert result is None


def test_persist_grading_result_writes_log_file(tmp_path: Path, monkeypatch) -> None:
    """评分结果写入 workspace/logs/grading_result.json。"""

    logs_dir = tmp_path / "logs"
    submission_path = tmp_path / "submission.csv"
    submission_path.write_text("id,target\n1,0.9\n", encoding="utf-8")
    solution = PESSolution(
        id="solution-001",
        operation="draft",
        generation=0,
        status="completed",
        created_at=utc_now_iso(),
        parent_ids=[],
        lineage="solution",
        run_id="run-001",
        submission_file_path=str(submission_path),
    )
    solution.metadata["submission_validated"] = True
    context = _DummyContext(
        solution=solution,
        workspace=_DummyWorkspace(logs_dir=logs_dir),
        runtime_context={
            "competition_id": "demo-comp",
            "mlebench_data_dir": str(tmp_path),
        },
    )
    expected = GradingResult(
        competition_id="demo-comp",
        test_score=0.88,
        test_score_direction="max",
        test_valid_submission=True,
        test_medal_level="silver",
        test_above_median=True,
        gold_threshold=0.95,
        silver_threshold=0.9,
        bronze_threshold=0.8,
        median_threshold=0.5,
        graded_at=utc_now_iso(),
    )

    monkeypatch.setattr("tests.grading.grade_submission", lambda **_: expected)

    result = MLEBenchGradingHook()(context)

    assert result == expected
    output_path = logs_dir / "grading_result.json"
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert payload[-1]["solution_id"] == "solution-001"
    assert payload[-1]["test_score"] == 0.88
    assert payload[-1]["test_medal_level"] == "silver"


def test_prompt_payload_does_not_expose_test_score() -> None:
    """即使 metadata 含 grading 字段，prompt payload 也必须过滤。"""

    solution = PESSolution(
        id="solution-001",
        operation="draft",
        generation=0,
        status="completed",
        created_at=utc_now_iso(),
        parent_ids=[],
        lineage="solution",
        run_id="run-001",
    )
    solution.metadata["test_score"] = 0.88
    solution.metadata["test_medal_level"] = "silver"
    solution.metadata["keep_me"] = "visible"

    payload = solution.to_prompt_payload()

    assert payload["metadata"]["keep_me"] == "visible"
    assert "test_score" not in payload["metadata"]
    assert "test_medal_level" not in payload["metadata"]


def test_grading_result_written_to_db_without_touching_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """评分结果写入 DB 独立表，不写回 solution.metadata。"""

    logs_dir = tmp_path / "logs"
    submission_path = tmp_path / "submission.csv"
    submission_path.write_text("id,target\n1,0.9\n", encoding="utf-8")
    db = HeraldDB(str(tmp_path / "herald.db"))
    solution = PESSolution(
        id="solution-001",
        operation="draft",
        generation=0,
        status="completed",
        created_at=utc_now_iso(),
        parent_ids=[],
        lineage="solution",
        run_id="run-001",
        submission_file_path=str(submission_path),
    )
    db.insert_solution(solution.to_record())
    solution.metadata["submission_validated"] = True
    context = _DummyContext(
        solution=solution,
        workspace=_DummyWorkspace(logs_dir=logs_dir),
        db=db,
        runtime_context={
            "competition_id": "demo-comp",
            "mlebench_data_dir": str(tmp_path),
        },
    )
    expected = GradingResult(
        competition_id="demo-comp",
        test_score=0.91,
        test_score_direction="max",
        test_valid_submission=True,
        test_medal_level="gold",
        test_above_median=True,
        gold_threshold=0.95,
        silver_threshold=0.9,
        bronze_threshold=0.8,
        median_threshold=0.5,
        graded_at=utc_now_iso(),
    )

    monkeypatch.setattr("tests.grading.grade_submission", lambda **_: expected)

    MLEBenchGradingHook()(context)
    row = db.get_latest_grading_result(solution.id)

    assert row is not None
    assert row["test_score"] == 0.91
    assert solution.metadata == {"submission_validated": True}


def test_grading_result_to_record_fields_complete() -> None:
    """统一 record 字段集合完整。"""

    result = GradingResult(
        competition_id="demo-comp",
        test_score=0.77,
        test_score_direction="min",
        test_valid_submission=True,
        test_medal_level="bronze",
        test_above_median=False,
        gold_threshold=0.3,
        silver_threshold=0.5,
        bronze_threshold=0.7,
        median_threshold=0.9,
        graded_at=utc_now_iso(),
    )

    record = grading_result_to_record(solution_id="solution-001", result=result)

    assert record["solution_id"] == "solution-001"
    assert record["competition_id"] == "demo-comp"
    assert record["test_score_direction"] == "min"
    assert record["test_graded_at"] == result.graded_at
