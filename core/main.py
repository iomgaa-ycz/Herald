"""Herald CLI 入口。"""

from __future__ import annotations

import logging
import sys

from core.database.herald_db import HeraldDB
from core.events import EventBus, setup_task_dispatcher
from core.load_config import ConfigManager
from core.scheduler import Scheduler
from core.workspace import Workspace

logger = logging.getLogger(__name__)


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
    HeraldDB(str(workspace.db_path))
    logger.info("数据库已初始化: %s", workspace.db_path)

    # Phase 4: 初始化事件流系统
    EventBus.get()
    setup_task_dispatcher()
    logger.info("事件流系统已初始化")

    # Phase 5: 启动调度器
    scheduler = Scheduler(
        competition_dir=config.run.competition_dir,
        max_tasks=config.run.max_tasks,
    )
    logger.info("调度器已启动: max_tasks=%d", config.run.max_tasks)
    scheduler.run()
    logger.info("调度器执行完成")


if __name__ == "__main__":
    main()
