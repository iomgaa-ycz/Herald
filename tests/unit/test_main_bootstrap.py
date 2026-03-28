"""`core.main` 装配链路测试。"""

from __future__ import annotations

import sys
import types
from pathlib import Path

from config.classconfig.herald import HeraldConfig
from config.classconfig.llm import LLMConfig
from config.classconfig.run import RunConfig
from core.database.herald_db import HeraldDB
from core.events import EventBus
from core.pes.draft import DraftPES
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
