"""Herald CLI 入口。"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from config.classconfig.herald import HeraldConfig
from core.database.herald_db import HeraldDB
from core.events import EventBus, setup_task_dispatcher
from core.load_config import ConfigManager
from core.pes import load_pes_config
from core.pes.draft import DraftPES
from core.pes.feature_extract import FeatureExtractPES
from core.scheduler import Scheduler
from core.utils.utils import create_run_id, utc_now_iso
from core.workspace import Workspace

logger = logging.getLogger(__name__)


def _load_create_grading_hook() -> object:
    """延迟加载评分 hook 工厂。"""

    grading_path = Path(__file__).resolve().parents[1] / "tests" / "grading.py"
    spec = importlib.util.spec_from_file_location("herald_tests_grading", grading_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载评分模块: {grading_path}")

    grading_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = grading_module
    spec.loader.exec_module(grading_module)
    return grading_module.create_grading_hook


def _build_llm_client(config: HeraldConfig) -> object:
    """装配共享 LLMClient。"""

    try:
        llm_module = importlib.import_module("core.llm")
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "缺少依赖 claude_agent_sdk，无法装配 LLMClient"
        ) from error

    return llm_module.LLMClient(
        llm_module.LLMConfig(
            model=config.llm.model,
            max_tokens=config.llm.max_tokens,
            max_turns=config.llm.max_turns,
            permission_mode=config.llm.permission_mode,
            setting_sources=tuple(config.llm.setting_sources),
        )
    )


def bootstrap_feature_extract_pes(
    config: HeraldConfig,
    workspace: Workspace,
    db: HeraldDB,
) -> FeatureExtractPES:
    """装配并注册 FeatureExtractPES 实例。"""

    pes_config_path = (
        Path(__file__).resolve().parents[1] / "config" / "pes" / "feature_extract.yaml"
    )
    pes_config = load_pes_config(pes_config_path)
    feature_extract_pes = FeatureExtractPES(
        config=pes_config,
        llm=_build_llm_client(config),
        db=db,
        workspace=workspace,
        runtime_context={
            "competition_dir": config.run.competition_dir,
        },
    )
    logger.info(
        "FeatureExtractPES 装配完成: instance_id=%s",
        feature_extract_pes.instance_id,
    )
    return feature_extract_pes


def bootstrap_draft_pes(
    config: HeraldConfig,
    workspace: Workspace,
    db: HeraldDB,
) -> DraftPES:
    """装配并注册生产级 DraftPES 实例。"""

    pes_config_path = (
        Path(__file__).resolve().parents[1] / "config" / "pes" / "draft.yaml"
    )
    pes_config = load_pes_config(pes_config_path)
    competition_root_dir = str(Path(config.run.competition_dir).expanduser().resolve())
    draft_pes = DraftPES(
        config=pes_config,
        llm=_build_llm_client(config),
        db=db,
        workspace=workspace,
        runtime_context={
            "competition_dir": config.run.competition_dir,
            "competition_root_dir": competition_root_dir,
            "competition_id": Path(competition_root_dir).name,
            "public_data_dir": str(workspace.data_dir),
            "workspace_logs_dir": str(workspace.logs_dir),
        },
    )
    create_grading_hook = _load_create_grading_hook()
    draft_pes.hooks.register(
        create_grading_hook(
            competition_root_dir=competition_root_dir,
            public_data_dir=str(workspace.data_dir),
            workspace_logs_dir=str(workspace.logs_dir),
        ),
        name=f"{draft_pes.instance_id}_grading_hook",
    )
    logger.info("DraftPES 装配完成: instance_id=%s", draft_pes.instance_id)
    return draft_pes


def build_run_metadata(
    config: HeraldConfig,
    workspace: Workspace,
    run_id: str,
    started_at: str,
) -> dict[str, Any]:
    """构造 run 级元数据快照。"""

    competition_root_dir = str(Path(config.run.competition_dir).expanduser().resolve())
    return {
        "run_id": run_id,
        "competition_id": Path(competition_root_dir).name,
        "competition_root_dir": competition_root_dir,
        "public_data_dir": str(workspace.data_dir),
        "workspace_dir": str(workspace.root),
        "config_snapshot": asdict(config),
        "started_at": started_at,
        "finished_at": None,
    }


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
    run_id = create_run_id()
    started_at = utc_now_iso()

    workspace = Workspace(config.run.workspace_dir)
    workspace.create(config.run.competition_dir)
    project_root = Path(__file__).resolve().parents[1]
    skills_source = project_root / "core" / "prompts" / "skills"
    visible_skills_dir = workspace.expose_project_skills(skills_source)
    logger.info("工作空间已创建: %s", workspace.root)
    if visible_skills_dir is not None:
        logger.info("project skills 已暴露到 working 目录: %s", visible_skills_dir)
    else:
        logger.info("未发现 project skills 目录，跳过暴露")

    # Phase 3: 初始化数据库
    db = HeraldDB(str(workspace.db_path))
    logger.info("数据库已初始化: %s", workspace.db_path)

    # Phase 4: 初始化事件流系统
    EventBus.get()
    setup_task_dispatcher()
    logger.info("事件流系统已初始化")

    metadata = build_run_metadata(
        config=config,
        workspace=workspace,
        run_id=run_id,
        started_at=started_at,
    )
    metadata_path = workspace.write_run_metadata(metadata)
    logger.info("run 元数据已写入: %s", metadata_path)

    # Phase 5: 装配 FeatureExtractPES + DraftPES
    feature_extract_pes = bootstrap_feature_extract_pes(
        config=config,
        workspace=workspace,
        db=db,
    )
    draft_pes = bootstrap_draft_pes(
        config=config,
        workspace=workspace,
        db=db,
    )
    feature_extract_pes.runtime_context["run_id"] = run_id
    draft_pes.runtime_context["run_id"] = run_id
    logger.info(
        "PES 已注册到调度链路: feature_extract=%s, draft=%s",
        feature_extract_pes.instance_id,
        draft_pes.instance_id,
    )

    # Phase 6: 启动调度器
    scheduler = Scheduler(
        competition_dir=config.run.competition_dir,
        max_tasks=config.run.max_tasks,
        context={"run_id": run_id},
        task_stages=[
            ("feature_extract", 1),
            ("draft", config.run.max_tasks),
        ],
    )
    logger.info("调度器已启动: task_stages=%s", scheduler._resolve_task_stages())
    try:
        scheduler.run()
        logger.info("调度器执行完成")
    finally:
        workspace.update_run_finished_at(utc_now_iso())
        logger.info("run 元数据已回写 finished_at")


if __name__ == "__main__":
    main()
