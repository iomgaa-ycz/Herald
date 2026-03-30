"""FeatureExtract project skill 链路集成测试。"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from core.agent.profile import AgentProfile
from core.events.bus import EventBus
from core.pes.config import load_pes_config
from core.pes.feature_extract import FeatureExtractPES
from core.pes.registry import PESRegistry
from core.workspace import Workspace


def setup_function() -> None:
    """每个测试前重置全局单例。"""

    EventBus.reset()
    PESRegistry.reset()


@dataclass(slots=True)
class DummyResponse:
    """测试用模型响应。"""

    result: str
    turns: list[dict[str, object]]
    model: str = "dummy-model"
    tokens_in: int = 1
    tokens_out: int = 1
    cost_usd: float | None = None
    duration_ms: int = 0
    session_id: str | None = None


class RecordingLLM:
    """记录调用参数并按顺序返回预设响应。"""

    def __init__(self, responses: list[str]) -> None:
        """初始化测试桩。"""

        self.responses = responses
        self.calls: list[dict[str, object]] = []
        self._index = 0

    async def execute_task(self, prompt: str, **kwargs: object) -> DummyResponse:
        """记录调用并返回当前响应。"""

        self.calls.append({"prompt": prompt, **kwargs})
        result = self.responses[self._index]
        self._index += 1
        return DummyResponse(result=result, turns=[])


class DummyPromptManager:
    """返回固定 prompt 的测试桩。"""

    def build_prompt(
        self,
        operation: str,
        phase: str,
        context: dict[str, object],
    ) -> str:
        """返回固定 prompt。"""

        del operation, context
        return f"prompt:{phase}"


MANIFEST_DIR = Path(__file__).resolve().parents[1] / "cases" / "competitions"
_TEST_DATA_ROOT = Path(
    os.environ.get("HERALD_TEST_DATA_ROOT", "~/.cache/mle-bench/data")
).expanduser()
REAL_COMPETITION_IDS: tuple[str, ...] = (
    "tabular-playground-series-may-2022",
    "spaceship-titanic",
)
_REPORT_SECTION_RE = re.compile(r"## (.+?)\n```json\n(.*?)\n```", re.DOTALL)


def _repo_root() -> Path:
    """返回仓库根目录。"""

    return Path(__file__).resolve().parents[2]


def _skills_source() -> Path:
    """返回 skills 源目录。"""

    return _repo_root() / "core" / "prompts" / "skills"


def _load_competition_manifest(competition_id: str) -> dict[str, object]:
    """读取真实竞赛 manifest。"""

    manifest_path = MANIFEST_DIR / f"{competition_id}.yaml"
    return dict(yaml.safe_load(manifest_path.read_text(encoding="utf-8")))


def _require_real_competition_dir(competition_id: str) -> Path:
    """获取真实竞赛 public 数据目录，不可用时跳过测试。"""

    if not _TEST_DATA_ROOT.exists():
        pytest.skip(f"真实数据根目录不存在: {_TEST_DATA_ROOT}")

    manifest = _load_competition_manifest(competition_id)
    relative_root = str(manifest["relative_root"])
    competition_dir = (_TEST_DATA_ROOT / relative_root).resolve()
    if not competition_dir.exists():
        pytest.skip(f"真实竞赛目录不存在: {competition_dir}")

    required_public_files = manifest.get("required_public_files", [])
    for file_name in required_public_files:
        if not (competition_dir / str(file_name)).exists():
            pytest.skip(f"竞赛目录缺少必需文件: {competition_dir / str(file_name)}")

    return competition_dir


def _count_csv_rows(csv_path: Path) -> int:
    """统计 CSV 数据行数（不含表头）。"""

    with csv_path.open("r", encoding="utf-8", errors="ignore") as handle:
        line_count = sum(1 for _ in handle)
    return max(line_count - 1, 0)


def _read_csv_columns(csv_path: Path) -> list[str]:
    """读取 CSV 表头。"""

    with csv_path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        return [str(column) for column in next(reader)]


def _parse_report_sections(report_text: str) -> dict[str, dict[str, object]]:
    """把 Markdown 预览报告解析为 section -> payload。"""

    sections: dict[str, dict[str, object]] = {}
    for title, payload in _REPORT_SECTION_RE.findall(report_text):
        sections[title] = dict(json.loads(payload))
    return sections


def _expected_target_columns(
    sample_submission_path: Path,
    test_path: Path,
) -> list[str]:
    """根据真实文件列名推导期望目标列。"""

    sample_columns = _read_csv_columns(sample_submission_path)
    test_columns = set(_read_csv_columns(test_path))
    target_columns = [column for column in sample_columns if column not in test_columns]
    if not target_columns and len(sample_columns) > 1:
        return sample_columns[1:]
    return target_columns


def _run_python_script(
    script_path: Path,
    *args: str,
    cwd: Path | None = None,
) -> str:
    """运行 skill 脚本并返回标准输出。"""

    completed = subprocess.run(
        [sys.executable, str(script_path), *args],
        check=True,
        capture_output=True,
        text=True,
        cwd=None if cwd is None else str(cwd),
    )
    return completed.stdout


def _make_execute_response(data_profile: str) -> str:
    """构造 execute 阶段结构化输出。"""

    payload = {
        "task_spec": {
            "task_type": "tabular",
            "competition_name": "demo-competition",
            "objective": "predict target",
            "metric_name": "auc",
            "metric_direction": "maximize",
        },
        "data_profile": data_profile,
        "genome_template": "tabular",
    }
    return f"分析完成。\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"


def _build_agent() -> AgentProfile:
    """构造最小 agent profile。"""

    return AgentProfile(
        name="kaggle_master",
        display_name="Kaggle Master",
        prompt_text="你是数据竞赛专家。",
    )


def test_feature_extract_execute_sees_visible_project_skills(tmp_path: Path) -> None:
    """execute 阶段在 working 目录下能看到 project skills。"""

    competition_dir = _require_real_competition_dir("tabular-playground-series-may-2022")
    skills_source = _skills_source()

    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)
    visible_skills_dir = workspace.expose_project_skills(skills_source)

    llm = RecordingLLM(
        responses=[
            "先看 description 与数据文件。",
            _make_execute_response("训练集 2 行，1 个数值特征，无缺失值。"),
            "总结：这是标准 tabular 任务。",
        ]
    )
    pes = FeatureExtractPES(
        config=load_pes_config("config/pes/feature_extract.yaml"),
        llm=llm,
        workspace=workspace,
        runtime_context={
            "competition_dir": str(competition_dir),
            "run_id": "run-001",
        },
        prompt_manager=DummyPromptManager(),
    )

    solution = asyncio.run(pes.run(agent_profile=_build_agent()))

    execute_call = llm.calls[1]

    assert solution.status == "completed"
    assert visible_skills_dir is not None
    assert visible_skills_dir.is_symlink()
    assert visible_skills_dir.resolve() == skills_source.resolve()
    assert execute_call["cwd"] == str(workspace.working_dir)
    assert "Skill" in execute_call["allowed_tools"]
    assert (
        workspace.working_dir
        / ".claude"
        / "skills"
        / "feature-extract-data-preview"
        / "SKILL.md"
    ).exists()
    assert workspace.summary()["project_skills_dir"] == str(visible_skills_dir)


def test_report_format_skill_visible_in_working(tmp_path: Path) -> None:
    """report-format skill 可通过 expose_project_skills() 暴露到 working。"""

    competition_dir = _require_real_competition_dir("tabular-playground-series-may-2022")
    skills_source = _skills_source()

    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)
    visible_skills_dir = workspace.expose_project_skills(skills_source)

    assert visible_skills_dir is not None

    report_format_skill = (
        workspace.working_dir
        / ".claude"
        / "skills"
        / "feature-extract-report-format"
        / "SKILL.md"
    )
    assert report_format_skill.exists(), (
        "report-format SKILL.md 应通过 expose_project_skills 可见"
    )

    skill_text = report_format_skill.read_text(encoding="utf-8")
    assert "# 数据概况报告" in skill_text
    assert "## 1. 数据集概览" in skill_text
    assert "## 6. 关键发现与建模建议" in skill_text


def test_feature_extract_execute_skips_missing_project_skills(tmp_path: Path) -> None:
    """缺少 project skills 时 execute 链路仍可继续。"""

    competition_dir = _require_real_competition_dir("tabular-playground-series-may-2022")

    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)
    visible_skills_dir = workspace.expose_project_skills(tmp_path / "nonexistent")

    llm = RecordingLLM(
        responses=[
            "先看 description 与数据文件。",
            _make_execute_response("训练集 2 行，1 个数值特征，无缺失值。"),
            "总结：这是标准 tabular 任务。",
        ]
    )
    pes = FeatureExtractPES(
        config=load_pes_config("config/pes/feature_extract.yaml"),
        llm=llm,
        workspace=workspace,
        runtime_context={
            "competition_dir": str(competition_dir),
            "run_id": "run-001",
        },
        prompt_manager=DummyPromptManager(),
    )

    solution = asyncio.run(pes.run(agent_profile=_build_agent()))

    execute_call = llm.calls[1]

    assert solution.status == "completed"
    assert visible_skills_dir is None
    assert execute_call["cwd"] == str(workspace.working_dir)
    assert "Skill" in execute_call["allowed_tools"]
    assert not (workspace.working_dir / ".claude" / "skills").exists()
    assert workspace.summary()["project_skills_dir"] == ""


@pytest.mark.parametrize("competition_id", REAL_COMPETITION_IDS)
def test_feature_extract_preview_skill_scripts_run_on_competition_dir(
    tmp_path: Path,
    competition_id: str,
) -> None:
    """真实 preview skill 脚本能在 working 目录中稳定运行。"""

    competition_dir = _require_real_competition_dir(competition_id)

    workspace = Workspace(tmp_path / competition_id / "workspace")
    workspace.create(competition_dir)
    visible_skills_dir = workspace.expose_project_skills(_skills_source())

    assert visible_skills_dir is not None

    script_path = (
        workspace.working_dir
        / ".claude"
        / "skills"
        / "feature-extract-data-preview"
        / "scripts"
        / "preview_competition.py"
    )
    output = _run_python_script(
        script_path,
        "--data-dir",
        str(workspace.data_dir),
        cwd=workspace.working_dir,
    )
    sections = _parse_report_sections(output)
    inventory_payload = sections["文件清单"]
    train_payload = sections["train 预览"]
    test_payload = sections["test 预览"]
    submission_payload = sections["sample_submission 约束"]

    assert script_path.exists()
    assert set(sections.keys()) == {
        "文件清单",
        "描述文件预览",
        "train 预览",
        "test 预览",
        "sample_submission 约束",
    }
    assert inventory_payload["detected_files"] == {
        "description": "description.md",
        "train": "train.csv",
        "test": "test.csv",
        "sample_submission": "sample_submission.csv",
    }
    assert set(inventory_payload["visible_files"]) >= {
        "description.md",
        "train.csv",
        "test.csv",
        "sample_submission.csv",
    }
    assert train_payload["file_name"] == "train.csv"
    assert test_payload["file_name"] == "test.csv"
    assert submission_payload["file_name"] == "sample_submission.csv"
    assert submission_payload["row_count_should_match_test"] == _count_csv_rows(
        workspace.data_dir / "test.csv"
    )


@pytest.mark.parametrize("competition_id", REAL_COMPETITION_IDS)
def test_feature_extract_preview_skill_output_covers_minimum_fields(
    tmp_path: Path,
    competition_id: str,
) -> None:
    """preview skill 输出覆盖 Task 14 规定的最小字段。"""

    competition_dir = _require_real_competition_dir(competition_id)
    manifest = _load_competition_manifest(competition_id)

    workspace = Workspace(tmp_path / competition_id / "workspace")
    workspace.create(competition_dir)
    visible_skills_dir = workspace.expose_project_skills(_skills_source())

    assert visible_skills_dir is not None

    scripts_dir = (
        workspace.working_dir
        / ".claude"
        / "skills"
        / "feature-extract-data-preview"
        / "scripts"
    )

    table_payload = json.loads(
        _run_python_script(
            scripts_dir / "preview_table.py",
            "--file",
            str(workspace.data_dir / "train.csv"),
            cwd=workspace.working_dir,
        )
    )
    submission_payload = json.loads(
        _run_python_script(
            scripts_dir / "preview_submission.py",
            "--file",
            str(workspace.data_dir / "sample_submission.csv"),
            "--test-file",
            str(workspace.data_dir / "test.csv"),
            cwd=workspace.working_dir,
        )
    )
    description_payload = json.loads(
        _run_python_script(
            scripts_dir / "preview_description.py",
            "--file",
            str(workspace.data_dir / "description.md"),
            cwd=workspace.working_dir,
        )
    )
    expected_train_rows = _count_csv_rows(workspace.data_dir / "train.csv")
    expected_train_columns = _read_csv_columns(workspace.data_dir / "train.csv")
    expected_submission_columns = _read_csv_columns(
        workspace.data_dir / "sample_submission.csv"
    )
    expected_test_columns = _read_csv_columns(workspace.data_dir / "test.csv")
    description_lines = (
        workspace.data_dir / "description.md"
    ).read_text(encoding="utf-8").splitlines()
    expected_description_preview = "\n".join(description_lines[:40]).strip()

    assert table_payload["file_name"] == "train.csv"
    assert table_payload["total_rows"] == expected_train_rows
    assert table_payload["sampled_rows"] == min(expected_train_rows, 2000)
    assert table_payload["columns"] == expected_train_columns
    assert table_payload["column_count"] == len(expected_train_columns)
    assert table_payload["column_count"] >= 2
    assert sum(table_payload["dtype_counts"].values()) == table_payload["column_count"]
    assert (
        len(table_payload["numeric_columns"]) + len(table_payload["non_numeric_columns"])
        == table_payload["column_count"]
    )
    assert "missing_columns" in table_payload
    assert len(table_payload["sample_records"]) == min(expected_train_rows, 5)

    assert submission_payload["file_name"] == "sample_submission.csv"
    assert submission_payload["column_order"] == expected_submission_columns
    assert submission_payload["id_like_columns"] == [
        column for column in expected_submission_columns if column in set(expected_test_columns)
    ]
    assert submission_payload["target_columns"] == _expected_target_columns(
        workspace.data_dir / "sample_submission.csv",
        workspace.data_dir / "test.csv",
    )
    assert submission_payload["row_count_should_match_test"] == _count_csv_rows(
        workspace.data_dir / "test.csv"
    )
    assert len(submission_payload["sample_records"]) == min(
        submission_payload["total_rows"],
        5,
    )

    assert description_payload["file_name"] == "description.md"
    assert description_payload["line_count"] == len(description_lines)
    assert description_payload["preview"] == expected_description_preview
    if str(manifest["metric_name"]).lower() in expected_description_preview.lower():
        assert str(manifest["metric_name"]).lower() in {
            metric.lower() for metric in description_payload["detected_metric_keywords"]
        }
