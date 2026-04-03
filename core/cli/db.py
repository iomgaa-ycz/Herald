"""Herald DB CLI 工具

供 Agent 通过 Bash 调用，查询/写入 HeraldDB。
所有命令输出 JSON 到 stdout。

用法示例：
    python core/cli/db.py query-lineage --slot MODEL --db-path /path/to/herald.db
    python core/cli/db.py get-population-summary --db-path /path/to/herald.db
    python core/cli/db.py read-gene-code --solution-id <uuid> --slot MODEL --db-path ...
    python core/cli/db.py write-l2-insight --slot MODEL --task-type tabular_ml \
        --pattern "XGBoost 在小数据集上比 LightGBM 稳定" --support --solution-id <uuid> --db-path ...
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

from core.database.herald_db import HeraldDB


def _get_db(db_path: str | None) -> HeraldDB:
    """从参数或环境变量初始化 HeraldDB。

    Args:
        db_path: 命令行传入的 --db-path，可为 None

    Returns:
        已初始化的 HeraldDB 实例

    Raises:
        SystemExit: db_path 未指定且环境变量也未设置时
    """
    path = db_path or os.environ.get("HERALD_DB_PATH")
    if not path:
        print(
            json.dumps(
                {"error": "必须通过 --db-path 或 HERALD_DB_PATH 环境变量指定数据库路径"}
            ),
            file=sys.stderr,
        )
        sys.exit(1)
    return HeraldDB(path)


def _extract_gene_region(code: str, slot: str) -> str | None:
    """从完整代码中提取指定 slot 的 GENE 区域。

    Args:
        code: 完整代码
        slot: 基因位点名

    Returns:
        GENE 区域代码，未找到返回 None
    """
    pattern = rf"#\s*GENE[:_]\s*{re.escape(slot)}\b(.*?)(?=#\s*GENE[:_]|\Z)"
    match = re.search(pattern, code, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


def cmd_query_lineage(args: argparse.Namespace) -> None:
    """查询某 slot 的历史变异记录（族谱）。"""
    db = _get_db(args.db_path)
    result: list[dict[str, Any]] = db.get_slot_history(args.slot)
    print(json.dumps(result, ensure_ascii=False))


def cmd_get_population_summary(args: argparse.Namespace) -> None:
    """获取当前种群概况。"""
    db = _get_db(args.db_path)
    result: dict[str, Any] = db.get_population_summary()
    print(json.dumps(result, ensure_ascii=False))


def cmd_read_gene_code(args: argparse.Namespace) -> None:
    """读取某 Solution 某 slot 的 GENE 区域源代码。"""
    db = _get_db(args.db_path)
    full_code = db.get_full_code(args.solution_id)
    if full_code is None:
        print(json.dumps({"code": None, "found": False}, ensure_ascii=False))
        return
    gene_code = _extract_gene_region(full_code, args.slot)
    print(
        json.dumps(
            {"code": gene_code, "found": gene_code is not None}, ensure_ascii=False
        )
    )


def cmd_write_l2_insight(args: argparse.Namespace) -> None:
    """写入或更新 L2 知识条目。"""
    db = _get_db(args.db_path)
    evidence_type = "support" if args.support else "contradict"
    insight_id: int = db.upsert_l2_insight(
        slot=args.slot,
        task_type=args.task_type,
        pattern=args.pattern,
        insight=args.pattern,
        solution_id=args.solution_id,
        evidence_type=evidence_type,
    )
    print(json.dumps({"insight_id": insight_id}, ensure_ascii=False))


def cmd_get_draft_detail(args: argparse.Namespace) -> None:
    """获取单个 draft 的完整 summarize_insight。"""
    db = _get_db(args.db_path)
    row = db.get_solution(args.solution_id)
    if row is None:
        print(json.dumps({"error": f"未找到 solution: {args.solution_id}"}))
        return
    print(
        json.dumps(
            {
                "solution_id": row["id"],
                "generation": row["generation"],
                "status": row["status"],
                "fitness": row.get("fitness"),
                "metric_name": row.get("metric_name"),
                "metric_value": row.get("metric_value"),
                "summarize_insight": row.get("summarize_insight"),
            },
            ensure_ascii=False,
        )
    )


def cmd_get_l2_insights(args: argparse.Namespace) -> None:
    """获取活跃的 L2 经验（含 solution 的 fitness/metric 信息）。"""
    db = _get_db(args.db_path)
    run_id = getattr(args, "run_id", None)
    rows = db.get_l2_insights_with_solution_info(
        slot="strategy",
        task_type=args.task_type,
        run_id=run_id,
        limit=args.limit,
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        insight_text = row.get("insight") or ""
        if len(insight_text) > 500:
            insight_text = insight_text[:500]
        result.append(
            {
                "id": row["id"],
                "slot": row["slot"],
                "pattern": row["pattern"],
                "insight": insight_text,
                "confidence": row["confidence"],
                "status": row["status"],
                "source_solution_id": row.get("source_solution_id"),
                "fitness": row.get("fitness"),
                "metric_name": row.get("metric_name"),
                "metric_value": row.get("metric_value"),
                "solution_status": row.get("solution_status"),
            }
        )
    print(json.dumps(result, ensure_ascii=False))


def _build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(
        description="Herald DB CLI — 供 Agent 通过 Bash 调用",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # query-lineage
    p_lineage = sub.add_parser("query-lineage", help="查询某 slot 的历史变异记录")
    p_lineage.add_argument("--slot", required=True, help="基因位点名（如 MODEL）")
    p_lineage.add_argument(
        "--db-path", default=None, help="数据库路径（也可用 HERALD_DB_PATH）"
    )

    # get-population-summary
    p_pop = sub.add_parser("get-population-summary", help="获取当前种群概况")
    p_pop.add_argument(
        "--db-path", default=None, help="数据库路径（也可用 HERALD_DB_PATH）"
    )

    # read-gene-code
    p_gene = sub.add_parser(
        "read-gene-code", help="读取某 Solution 某 slot 的 GENE 区域源代码"
    )
    p_gene.add_argument("--solution-id", required=True, help="Solution UUID")
    p_gene.add_argument("--slot", required=True, help="基因位点名")
    p_gene.add_argument(
        "--db-path", default=None, help="数据库路径（也可用 HERALD_DB_PATH）"
    )

    # write-l2-insight
    p_l2 = sub.add_parser("write-l2-insight", help="写入或更新 L2 知识条目")
    p_l2.add_argument("--slot", required=True, help="基因位点名")
    p_l2.add_argument("--task-type", required=True, help="任务类型（如 tabular_ml）")
    p_l2.add_argument("--pattern", required=True, help="知识内容")
    p_l2.add_argument(
        "--support",
        action="store_true",
        help="实验支撑此知识（不传则为反驳）",
    )
    p_l2.add_argument("--solution-id", required=True, help="产生此知识的 Solution UUID")
    p_l2.add_argument(
        "--db-path", default=None, help="数据库路径（也可用 HERALD_DB_PATH）"
    )

    # get-draft-detail
    p_draft_detail = sub.add_parser(
        "get-draft-detail", help="获取单个 draft 的完整 summarize_insight"
    )
    p_draft_detail.add_argument("--solution-id", required=True, help="Solution UUID")
    p_draft_detail.add_argument(
        "--db-path", default=None, help="数据库路径（也可用 HERALD_DB_PATH）"
    )

    # get-l2-insights
    p_l2_insights = sub.add_parser(
        "get-l2-insights", help="获取活跃的 L2 经验（含 solution fitness/metric 信息）"
    )
    p_l2_insights.add_argument(
        "--task-type", required=True, help="任务类型（如 tabular）"
    )
    p_l2_insights.add_argument("--run-id", default=None, help="按 run_id 过滤（可选）")
    p_l2_insights.add_argument(
        "--limit", type=int, default=20, help="最大返回条数（默认 20）"
    )
    p_l2_insights.add_argument(
        "--db-path", default=None, help="数据库路径（也可用 HERALD_DB_PATH）"
    )

    return parser


_COMMANDS = {
    "query-lineage": cmd_query_lineage,
    "get-population-summary": cmd_get_population_summary,
    "read-gene-code": cmd_read_gene_code,
    "write-l2-insight": cmd_write_l2_insight,
    "get-draft-detail": cmd_get_draft_detail,
    "get-l2-insights": cmd_get_l2_insights,
}


def main() -> None:
    """CLI 入口。"""
    parser = _build_parser()
    args = parser.parse_args()
    _COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
