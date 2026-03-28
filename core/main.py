"""Herald CLI 入口。"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path

from config.classconfig.herald import HeraldConfig
from core.database.herald_db import HeraldDB
from core.events import EventBus, setup_task_dispatcher
from core.load_config import ConfigManager
from core.pes import load_pes_config
from core.pes.draft import DraftPES
from core.scheduler import Scheduler
from core.workspace import Workspace

logger = logging.getLogger(__name__)


def bootstrap_draft_pes(
    config: HeraldConfig,
    workspace: Workspace,
    db: HeraldDB,
) -> DraftPES:
    """装配并注册生产级 DraftPES 实例。"""

    try:
        llm_module = importlib.import_module("core.llm")
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "缺少依赖 claude_agent_sdk，无法装配 LLMClient"
        ) from error

    pes_config_path = (
        Path(__file__).resolve().parents[1] / "config" / "pes" / "draft.yaml"
    )
    pes_config = load_pes_config(pes_config_path)
    llm_client = llm_module.LLMClient(
        llm_module.LLMConfig(
            model=config.llm.model,
            max_tokens=config.llm.max_tokens,
            max_turns=config.llm.max_turns,
            permission_mode=config.llm.permission_mode,
        )
    )
    draft_pes = DraftPES(
        config=pes_config,
        llm=llm_client,
        db=db,
        workspace=workspace,
        runtime_context={
            "competition_dir": config.run.competition_dir,
        },
    )
    logger.info("DraftPES 装配完成: instance_id=%s", draft_pes.instance_id)
    return draft_pes


def main() -> None:
    """Herald 主流程：加载配置 → 创建工作空间 → 初始化数据库 → 初始化事件流系统。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Phase 1: 获取配置（YAML + CLI）
    config = ConfigManager().parse()
    logger.info("配置加载完成: workspace_dir=%s", config.run.workspace_dir)

    # Phase 2: 创建工作空间
    if not config.run.competition_dir:
        logger.error("缺少必填参数 --run_competition_dir")
        sys.exit(1)

    workspace = Workspace(config.run.workspace_dir)
    workspace.create(config.run.competition_dir)
    logger.info("工作空间已创建: %s", workspace.root)

    # Phase 3: 初始化数据库
    db = HeraldDB(str(workspace.db_path))
    logger.info("数据库已初始化: %s", workspace.db_path)

    # Phase 4: 初始化事件流系统
    EventBus.get()
    setup_task_dispatcher()
    logger.info("事件流系统已初始化")

    # Phase 5: 装配 DraftPES
    draft_pes = bootstrap_draft_pes(
        config=config,
        workspace=workspace,
        db=db,
    )
    logger.info("DraftPES 已注册到调度链路: %s", draft_pes.instance_id)

    # Phase 6: 启动调度器
    scheduler = Scheduler(
        competition_dir=config.run.competition_dir,
        max_tasks=config.run.max_tasks,
    )
    logger.info("调度器已启动: max_tasks=%d", config.run.max_tasks)
    scheduler.run()
    logger.info("调度器执行完成")


if __name__ == "__main__":
    main()
