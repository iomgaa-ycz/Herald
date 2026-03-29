"""`core.main` 装配链路测试。"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from config.classconfig.herald import HeraldConfig
from config.classconfig.llm import LLMConfig
from config.classconfig.run import RunConfig
from core.database.herald_db import HeraldDB
from core.events import EventBus
from core.pes.draft import DraftPES
from core.pes.feature_extract import FeatureExtractPES
from core.pes.registry import PESRegistry
from core.workspace import Workspace

claude_agent_sdk_stub = types.ModuleType("claude_agent_sdk")
claude_agent_sdk_stub.AssistantMessage = object
claude_agent_sdk_stub.ClaudeAgentOptions = object
claude_agent_sdk_stub.ResultMessage = object
claude_agent_sdk_stub.TextBlock = object
claude_agent_sdk_stub.ToolResultBlock = object
claude_agent_sdk_stub.ToolUseBlock = object


async def _query_stub(*args: object, **kwargs: object) -> None:
    """提供最小异步查询桩。"""

    del args, kwargs
    if False:
        yield None


claude_agent_sdk_stub.query = _query_stub
sys.modules.setdefault("claude_agent_sdk", claude_agent_sdk_stub)


def setup_function() -> None:
    """每个测试前重置全局单例。"""

    EventBus.reset()
    PESRegistry.reset()


def test_bootstrap_draft_pes_registers_instance(tmp_path: Path) -> None:
    """`bootstrap_draft_pes()` 会创建并注册 `DraftPES`。"""

    from core.main import bootstrap_draft_pes

    competition_dir = tmp_path / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text("id,label\n1,0\n", encoding="utf-8")

    workspace_root = tmp_path / "workspace"
    workspace = Workspace(workspace_root)
    workspace.create(competition_dir)
    db = HeraldDB(str(workspace.db_path))
    config = HeraldConfig(
        llm=LLMConfig(
            model="dummy-model",
            max_tokens=2048,
            max_turns=3,
            permission_mode="bypassPermissions",
        ),
        run=RunConfig(
            workspace_dir=str(workspace_root),
            competition_dir=str(competition_dir),
            max_tasks=1,
        ),
    )

    draft_pes = bootstrap_draft_pes(
        config=config,
        workspace=workspace,
        db=db,
    )

    instances = PESRegistry.get_instance().get_by_base_name("draft")

    assert isinstance(draft_pes, DraftPES)
    assert instances == [draft_pes]
    assert draft_pes.workspace is workspace
    assert draft_pes.db is db
    assert draft_pes.runtime_context["competition_dir"] == str(competition_dir)
    assert draft_pes.runtime_context["competition_root_dir"] == str(
        competition_dir.resolve()
    )
    assert draft_pes.runtime_context["public_data_dir"] == str(workspace.data_dir)
    assert draft_pes.runtime_context["workspace_logs_dir"] == str(workspace.logs_dir)


def test_bootstrap_feature_extract_pes_registers_instance(tmp_path: Path) -> None:
    """`bootstrap_feature_extract_pes()` 会创建并注册 `FeatureExtractPES`。"""

    from core.main import bootstrap_feature_extract_pes

    competition_dir = tmp_path / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text("id,label\n1,0\n", encoding="utf-8")

    workspace_root = tmp_path / "workspace"
    workspace = Workspace(workspace_root)
    workspace.create(competition_dir)
    db = HeraldDB(str(workspace.db_path))
    config = HeraldConfig(
        llm=LLMConfig(
            model="dummy-model",
            max_tokens=2048,
            max_turns=3,
            permission_mode="bypassPermissions",
        ),
        run=RunConfig(
            workspace_dir=str(workspace_root),
            competition_dir=str(competition_dir),
            max_tasks=1,
        ),
    )

    feature_extract_pes = bootstrap_feature_extract_pes(
        config=config,
        workspace=workspace,
        db=db,
    )

    instances = PESRegistry.get_instance().get_by_base_name("feature_extract")

    assert isinstance(feature_extract_pes, FeatureExtractPES)
    assert instances == [feature_extract_pes]
    assert feature_extract_pes.workspace is workspace
    assert feature_extract_pes.db is db
    assert feature_extract_pes.runtime_context["competition_dir"] == str(
        competition_dir
    )


def test_run_metadata_file_can_be_written_and_updated(tmp_path: Path) -> None:
    """run 级 metadata.json 可写入并回写 finished_at。"""

    from core.main import build_run_metadata

    competition_dir = tmp_path / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text("id,label\n1,0\n", encoding="utf-8")

    workspace_root = tmp_path / "workspace"
    workspace = Workspace(workspace_root)
    workspace.create(competition_dir)
    config = HeraldConfig(
        llm=LLMConfig(
            model="dummy-model",
            max_tokens=2048,
            max_turns=3,
            permission_mode="bypassPermissions",
        ),
        run=RunConfig(
            workspace_dir=str(workspace_root),
            competition_dir=str(competition_dir),
            max_tasks=2,
        ),
    )

    metadata = build_run_metadata(
        config=config,
        workspace=workspace,
        run_id="run-001",
        started_at="2026-03-28T00:00:00+00:00",
    )
    metadata_path = workspace.write_run_metadata(metadata)

    assert metadata_path.exists()
    written_metadata = workspace.read_run_metadata()
    assert written_metadata is not None
    assert written_metadata["run_id"] == "run-001"
    assert written_metadata["finished_at"] is None

    workspace.update_run_finished_at("2026-03-28T00:10:00+00:00")

    updated_metadata = workspace.read_run_metadata()
    assert updated_metadata is not None
    assert updated_metadata["competition_id"] == "competition"
    assert updated_metadata["finished_at"] == "2026-03-28T00:10:00+00:00"


def test_build_run_metadata_contains_required_fields(tmp_path: Path) -> None:
    """run 元数据快照包含 TD 要求的最小字段集。"""

    from core.main import build_run_metadata

    competition_dir = tmp_path / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text("id,label\n1,0\n", encoding="utf-8")

    workspace_root = tmp_path / "workspace"
    workspace = Workspace(workspace_root)
    workspace.create(competition_dir)
    config = HeraldConfig(
        llm=LLMConfig(
            model="dummy-model",
            max_tokens=2048,
            max_turns=3,
            permission_mode="bypassPermissions",
        ),
        run=RunConfig(
            workspace_dir=str(workspace_root),
            competition_dir=str(competition_dir),
            max_tasks=2,
        ),
    )

    metadata = build_run_metadata(
        config=config,
        workspace=workspace,
        run_id="run-001",
        started_at="2026-03-28T00:00:00+00:00",
    )

    expected_keys = {
        "run_id",
        "competition_id",
        "competition_root_dir",
        "public_data_dir",
        "workspace_dir",
        "config_snapshot",
        "started_at",
        "finished_at",
    }

    assert expected_keys.issubset(metadata.keys())
    assert metadata["run_id"] == "run-001"
    assert metadata["competition_id"] == "competition"
    assert metadata["finished_at"] is None


@dataclass(slots=True)
class _StubPES:
    """测试 main 注入 run_id 的最小 PES 桩。"""

    instance_id: str
    runtime_context: dict[str, Any]


class _StubScheduler:
    """记录初始化参数的最小 Scheduler 桩。"""

    last_instance: _StubScheduler | None = None

    def __init__(
        self,
        competition_dir: str,
        max_tasks: int = 1,
        task_name: str = "draft",
        agent_name: str = "kaggle_master",
        context: dict[str, Any] | None = None,
        task_stages: list[tuple[str, int]] | None = None,
    ) -> None:
        self.competition_dir = competition_dir
        self.max_tasks = max_tasks
        self.task_name = task_name
        self.agent_name = agent_name
        self.context = context or {}
        self.task_stages = task_stages
        self.run_called = False
        _StubScheduler.last_instance = self

    def _resolve_task_stages(self) -> list[tuple[str, int]]:
        """返回 stage 配置，兼容 main 中的日志调用。"""

        if self.task_stages is not None:
            return list(self.task_stages)
        return [(self.task_name, self.max_tasks)]

    def run(self) -> None:
        """标记调度器已运行。"""

        self.run_called = True


def test_main_injects_shared_run_id_into_runtime_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`main()` 会把同一个 run_id 注入两个 PES 与调度器。"""

    import core.main as main_module

    competition_dir = tmp_path / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text("id,label\n1,0\n", encoding="utf-8")

    workspace_root = tmp_path / "workspace"
    config = HeraldConfig(
        llm=LLMConfig(
            model="dummy-model",
            max_tokens=2048,
            max_turns=3,
            permission_mode="bypassPermissions",
        ),
        run=RunConfig(
            workspace_dir=str(workspace_root),
            competition_dir=str(competition_dir),
            max_tasks=2,
        ),
    )

    captured_pes: dict[str, _StubPES] = {}

    class _StubConfigManager:
        def parse(self) -> HeraldConfig:
            return config

    def _stub_bootstrap_feature_extract_pes(
        config: HeraldConfig,
        workspace: Workspace,
        db: HeraldDB,
    ) -> _StubPES:
        del config, db
        pes = _StubPES(
            instance_id="feature_extract-pes",
            runtime_context={"competition_dir": str(workspace.data_dir.parent)},
        )
        captured_pes["feature_extract"] = pes
        return pes

    def _stub_bootstrap_draft_pes(
        config: HeraldConfig,
        workspace: Workspace,
        db: HeraldDB,
    ) -> _StubPES:
        del config, db
        pes = _StubPES(
            instance_id="draft-pes",
            runtime_context={"competition_dir": str(workspace.data_dir.parent)},
        )
        captured_pes["draft"] = pes
        return pes

    timestamps = iter(
        [
            "2026-03-28T00:00:00+00:00",
            "2026-03-28T00:10:00+00:00",
        ]
    )

    monkeypatch.setattr(main_module, "ConfigManager", _StubConfigManager)
    monkeypatch.setattr(
        main_module,
        "bootstrap_feature_extract_pes",
        _stub_bootstrap_feature_extract_pes,
    )
    monkeypatch.setattr(
        main_module,
        "bootstrap_draft_pes",
        _stub_bootstrap_draft_pes,
    )
    monkeypatch.setattr(main_module, "Scheduler", _StubScheduler)
    monkeypatch.setattr(main_module, "setup_task_dispatcher", lambda: None)
    monkeypatch.setattr(main_module, "create_run_id", lambda: "run-001")
    monkeypatch.setattr(main_module, "utc_now_iso", lambda: next(timestamps))

    main_module.main()

    assert captured_pes["feature_extract"].runtime_context["run_id"] == "run-001"
    assert captured_pes["draft"].runtime_context["run_id"] == "run-001"
    assert _StubScheduler.last_instance is not None
    assert _StubScheduler.last_instance.context["run_id"] == "run-001"
    assert _StubScheduler.last_instance.run_called is True

    workspace = Workspace(workspace_root)
    metadata = workspace.read_run_metadata()
    assert metadata is not None
    assert metadata["run_id"] == "run-001"
    assert metadata["started_at"] == "2026-03-28T00:00:00+00:00"
    assert metadata["finished_at"] == "2026-03-28T00:10:00+00:00"


def test_main_exposes_project_skills_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`main()` 会调用工作空间的 project skill 暴露逻辑。"""

    import core.main as main_module

    competition_dir = tmp_path / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text("id,label\n1,0\n", encoding="utf-8")

    workspace_root = tmp_path / "workspace"
    config = HeraldConfig(
        llm=LLMConfig(
            model="dummy-model",
            max_tokens=2048,
            max_turns=3,
            permission_mode="bypassPermissions",
        ),
        run=RunConfig(
            workspace_dir=str(workspace_root),
            competition_dir=str(competition_dir),
            max_tasks=1,
        ),
    )

    captured: dict[str, Path] = {}

    class _StubConfigManager:
        def parse(self) -> HeraldConfig:
            return config

    def _stub_bootstrap_feature_extract_pes(
        config: HeraldConfig,
        workspace: Workspace,
        db: HeraldDB,
    ) -> _StubPES:
        del config, db
        return _StubPES(
            instance_id="feature_extract-pes",
            runtime_context={"competition_dir": str(workspace.data_dir.parent)},
        )

    def _stub_bootstrap_draft_pes(
        config: HeraldConfig,
        workspace: Workspace,
        db: HeraldDB,
    ) -> _StubPES:
        del config, db
        return _StubPES(
            instance_id="draft-pes",
            runtime_context={"competition_dir": str(workspace.data_dir.parent)},
        )

    def _stub_expose_project_skills(
        self: Workspace,
        project_root: str | Path,
    ) -> Path:
        captured["project_root"] = Path(project_root)
        target_dir = tmp_path / "project-skills"
        target_dir.mkdir(parents=True, exist_ok=True)
        skills_link = self.working_dir / ".claude" / "skills"
        skills_link.parent.mkdir(parents=True, exist_ok=True)
        if skills_link.exists() or skills_link.is_symlink():
            skills_link.unlink()
        skills_link.symlink_to(target_dir, target_is_directory=True)
        return skills_link

    timestamps = iter(
        [
            "2026-03-28T00:00:00+00:00",
            "2026-03-28T00:10:00+00:00",
        ]
    )

    monkeypatch.setattr(main_module, "ConfigManager", _StubConfigManager)
    monkeypatch.setattr(
        main_module,
        "bootstrap_feature_extract_pes",
        _stub_bootstrap_feature_extract_pes,
    )
    monkeypatch.setattr(
        main_module,
        "bootstrap_draft_pes",
        _stub_bootstrap_draft_pes,
    )
    monkeypatch.setattr(main_module, "Scheduler", _StubScheduler)
    monkeypatch.setattr(main_module, "setup_task_dispatcher", lambda: None)
    monkeypatch.setattr(main_module, "create_run_id", lambda: "run-001")
    monkeypatch.setattr(main_module, "utc_now_iso", lambda: next(timestamps))
    monkeypatch.setattr(
        Workspace,
        "expose_project_skills",
        _stub_expose_project_skills,
    )

    main_module.main()

    assert captured["project_root"] == Path(main_module.__file__).resolve().parents[1]
    assert (workspace_root / "working" / ".claude" / "skills").is_symlink()
