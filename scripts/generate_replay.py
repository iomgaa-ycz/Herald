"""从真实竞赛数据生成 FeatureExtractPES 回放资产。

用法:
    python scripts/generate_replay.py [--competition COMPETITION_ID] [--output-dir DIR]

默认竞赛: tabular-playground-series-may-2022
默认输出: tests/cases/replays/feature_extract_tabular_success_v1/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.agent.profile import AgentProfile  # noqa: E402
from core.events.bus import EventBus  # noqa: E402
from core.llm import LLMClient, LLMConfig  # noqa: E402
from core.pes.config import load_pes_config  # noqa: E402
from core.pes.feature_extract import FeatureExtractPES  # noqa: E402
from core.pes.registry import PESRegistry  # noqa: E402
from core.prompts.manager import PromptManager  # noqa: E402
from core.workspace import Workspace  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# MLE-Bench 数据根目录
DEFAULT_DATA_ROOT = Path("~/.cache/mle-bench/data").expanduser()


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="生成 FeatureExtractPES 回放资产")
    parser.add_argument(
        "--competition",
        default="tabular-playground-series-may-2022",
        help="竞赛 ID（对应 mle-bench 数据目录名）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="回放输出目录，默认 tests/cases/replays/feature_extract_tabular_success_v1/",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help="MLE-Bench 数据根目录",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5-20250929",
        help="LLM 模型 ID",
    )
    return parser.parse_args()


async def run_feature_extract(
    competition_id: str,
    competition_dir: Path,
    workspace_root: Path,
    model: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """运行 FeatureExtractPES 并返回 (solution 快照, metadata)。

    Args:
        competition_id: 竞赛 ID
        competition_dir: 竞赛数据目录
        workspace_root: 工作空间根目录
        model: LLM 模型 ID

    Returns:
        (快照字典, 元数据字典)
    """

    # Phase 1: 重置全局单例
    EventBus.reset()
    PESRegistry.reset()

    # Phase 2: 构造 workspace
    workspace = Workspace(workspace_root)
    workspace.create(competition_dir)

    # Phase 3: 构造组件
    llm = LLMClient(LLMConfig(model=model))
    config = load_pes_config("config/pes/feature_extract.yaml")
    prompt_base = PROJECT_ROOT / "config" / "prompts"
    prompt_manager = PromptManager(
        template_dir=prompt_base / "templates",
        fragments_dir=prompt_base / "fragments",
        spec_path=prompt_base / "prompt_spec.yaml",
    )

    # 覆盖 build_phase_model_options：Claude CLI 要求 cwd 在 git 仓库内，
    # 将 cwd 改为项目根目录（workspace 路径仍通过 prompt context 注入）
    class _ReplayFeatureExtractPES(FeatureExtractPES):
        def build_phase_model_options(
            self,
            phase: str,
            solution: object,
            parent_solution: object | None,
        ) -> dict[str, Any]:
            del solution, parent_solution
            if phase != "execute":
                return {}
            return {"cwd": str(PROJECT_ROOT)}

    pes = _ReplayFeatureExtractPES(
        config=config,
        llm=llm,
        workspace=workspace,
        runtime_context={"competition_dir": str(competition_dir)},
        prompt_manager=prompt_manager,
    )

    # Phase 4: 运行三阶段
    agent = AgentProfile(
        name="replay-generator",
        display_name="Replay Generator",
        prompt_text="",
    )
    solution = await pes.run(agent_profile=agent, generation=0)

    # Phase 5: 提取快照
    snapshots = {
        "plan": solution.plan_summary or "",
        "execute_raw": solution.phase_outputs.get("execute", ""),
        "summarize": solution.summarize_insight or "",
    }

    metadata = {
        "competition_id": competition_id,
        "competition_dir": str(competition_dir),
        "genome_template": solution.metadata.get("genome_template", ""),
        "schema_task_type": solution.metadata.get("schema_task_type", ""),
        "status": solution.status,
    }

    return snapshots, metadata


def build_expected_json(execute_raw: str, metadata: dict[str, str]) -> dict:
    """从 execute 原始输出中提取 expected.json 内容。

    Args:
        execute_raw: execute 阶段原始文本
        metadata: solution 元数据

    Returns:
        expected 字典
    """
    import re

    pattern = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
    matches = pattern.findall(execute_raw)
    if not matches:
        raise ValueError("execute 输出中未找到 JSON code block，无法构造 expected.json")

    parsed = json.loads(matches[-1].strip())
    return {
        "task_spec": parsed.get("task_spec", {}),
        "data_profile": parsed.get("data_profile", ""),
        "genome_template": metadata.get("genome_template", "generic"),
    }


def save_replay(
    output_dir: Path,
    snapshots: dict[str, str],
    metadata: dict[str, str],
) -> None:
    """保存回放资产到目录。

    Args:
        output_dir: 输出目录
        snapshots: 阶段快照
        metadata: 元数据
    """

    output_dir.mkdir(parents=True, exist_ok=True)

    # input.json
    input_data = {
        "competition_id": metadata["competition_id"],
        "competition_dir": metadata["competition_dir"],
    }
    (output_dir / "input.json").write_text(
        json.dumps(input_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # plan.txt
    (output_dir / "plan.txt").write_text(snapshots["plan"], encoding="utf-8")

    # execute_raw.txt
    (output_dir / "execute_raw.txt").write_text(
        snapshots["execute_raw"], encoding="utf-8"
    )

    # summarize.txt
    (output_dir / "summarize.txt").write_text(snapshots["summarize"], encoding="utf-8")

    # expected.json
    expected = build_expected_json(snapshots["execute_raw"], metadata)
    (output_dir / "expected.json").write_text(
        json.dumps(expected, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info("回放资产已保存到: %s", output_dir)
    logger.info("文件列表: %s", [f.name for f in sorted(output_dir.iterdir())])


async def main() -> None:
    """主函数。"""
    args = parse_args()

    competition_dir = args.data_root / args.competition
    if not competition_dir.exists():
        logger.error("竞赛数据目录不存在: %s", competition_dir)
        sys.exit(1)

    output_dir = args.output_dir
    if output_dir is None:
        output_dir = (
            PROJECT_ROOT
            / "tests"
            / "cases"
            / "replays"
            / "feature_extract_tabular_success_v1"
        )

    logger.info("竞赛: %s", args.competition)
    logger.info("数据目录: %s", competition_dir)
    logger.info("输出目录: %s", output_dir)
    logger.info("模型: %s", args.model)

    # 使用临时目录作为 workspace
    import tempfile

    with tempfile.TemporaryDirectory(prefix="herald_replay_") as tmp:
        workspace_root = Path(tmp) / "workspace"
        snapshots, metadata = await run_feature_extract(
            competition_id=args.competition,
            competition_dir=competition_dir,
            workspace_root=workspace_root,
            model=args.model,
        )

    # 保存回放
    save_replay(output_dir, snapshots, metadata)

    # 打印摘要供人工审核
    logger.info("--- 运行摘要 ---")
    logger.info("状态: %s", metadata["status"])
    logger.info("genome_template: %s", metadata["genome_template"])
    logger.info("schema_task_type: %s", metadata["schema_task_type"])
    logger.info("plan 长度: %d 字符", len(snapshots["plan"]))
    logger.info("execute_raw 长度: %d 字符", len(snapshots["execute_raw"]))
    logger.info("summarize 长度: %d 字符", len(snapshots["summarize"]))


if __name__ == "__main__":
    import anyio

    anyio.run(main)
