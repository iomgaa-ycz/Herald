"""从 L1 运行产物中截取 L2 回放资产。

用法：
    python scripts/extract_l2_replays.py [--workspace workspace/] [--output tests/cases/replays/]

从 workspace/database/herald.db 和 workspace/working/ 截取：
- draft_success_tabular_v1/   ← 成功的 Draft 运行
- feature_extract_tabular_success_v1/  ← 成功的 FeatureExtract 运行
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def _query_one(cur: sqlite3.Cursor, sql: str, params: tuple = ()) -> dict | None:
    """执行查询并返回单行字典。"""
    cur.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        return None
    cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row, strict=True))


def _query_all(cur: sqlite3.Cursor, sql: str, params: tuple = ()) -> list[dict]:
    """执行查询并返回所有行。"""
    cur.execute(sql, params)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in rows]


def _truncate_submission(full_csv: str, max_data_rows: int = 5) -> str:
    """截断 submission.csv 到 header + max_data_rows 行。"""
    lines = full_csv.strip().split("\n")
    kept = lines[: 1 + max_data_rows]
    return "\n".join(kept) + "\n"


def extract_draft_success(
    cur: sqlite3.Cursor,
    working_dir: Path,
    output_dir: Path,
) -> None:
    """截取成功的 Draft 运行回放资产。"""
    # 找到成功的 Draft solution
    sol = _query_one(
        cur,
        "SELECT * FROM solutions WHERE operation='draft' AND status='completed' "
        "AND metric_value IS NOT NULL ORDER BY created_at DESC LIMIT 1",
    )
    if sol is None:
        print("未找到成功的 Draft solution，跳过")
        return

    solution_id = sol["id"]
    print(
        f"Draft solution: {solution_id}, metric={sol['metric_name']}={sol['metric_value']}"
    )

    # 获取各 phase 的 llm_calls
    llm_calls = _query_all(
        cur,
        "SELECT phase, turns_json, output_text FROM llm_calls "
        "WHERE solution_id=? ORDER BY created_at",
        (solution_id,),
    )
    phase_map = {c["phase"]: c for c in llm_calls}

    # 获取 exec_logs
    exec_log = _query_one(
        cur,
        "SELECT * FROM exec_logs WHERE solution_id=? ORDER BY created_at DESC LIMIT 1",
        (solution_id,),
    )

    # 准备输出目录
    case_dir = output_dir / "draft_success_tabular_v1"
    case_dir.mkdir(parents=True, exist_ok=True)

    # 1. turns.json — execute phase 的完整 tool trace
    execute_call = phase_map.get("execute")
    if execute_call and execute_call["turns_json"]:
        turns = json.loads(execute_call["turns_json"])
        (case_dir / "turns.json").write_text(
            json.dumps(turns, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  turns.json: {len(turns)} turns")

    # 2. solution.py — 真实 Agent 生成的代码
    src_solution = working_dir / "solution.py"
    if src_solution.exists():
        (case_dir / "solution.py").write_text(
            src_solution.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        print(f"  solution.py: {src_solution.stat().st_size} bytes")

    # 3. stdout.log — 从 exec_logs 截取
    if exec_log and exec_log["stdout"]:
        (case_dir / "stdout.log").write_text(
            exec_log["stdout"] + "\n",
            encoding="utf-8",
        )
        print(f"  stdout.log: {len(exec_log['stdout'])} chars")

    # 4. metrics.json — 从 exec_logs.metrics_json 或 stdout 最后一行 JSON
    metrics_written = False
    if exec_log and exec_log.get("metrics_json"):
        metrics = json.loads(exec_log["metrics_json"])
        (case_dir / "metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        metrics_written = True
        print("  metrics.json: from exec_logs.metrics_json")

    if not metrics_written and exec_log and exec_log["stdout"]:
        # 从 stdout 最后几行找 JSON metrics
        for line in reversed(exec_log["stdout"].split("\n")):
            line = line.strip()
            if line.startswith("{") and "metric_" in line:
                try:
                    raw = json.loads(line)
                    # 转换为标准 L2 格式
                    metrics = {
                        "val_metric_name": raw.get("metric_name", sol["metric_name"]),
                        "val_metric_value": raw.get(
                            "metric_value", sol["metric_value"]
                        ),
                        "val_metric_direction": "max",
                    }
                    (case_dir / "metrics.json").write_text(
                        json.dumps(metrics, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    metrics_written = True
                    print("  metrics.json: from stdout JSON line")
                    break
                except json.JSONDecodeError:
                    continue

    if not metrics_written:
        # fallback: 从 solution 表构造
        metrics = {
            "val_metric_name": sol["metric_name"],
            "val_metric_value": sol["metric_value"],
            "val_metric_direction": "max",
        }
        (case_dir / "metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("  metrics.json: from solutions table")

    # 5. submission.csv — 截断版本
    src_submission = working_dir / "submission.csv"
    if src_submission.exists():
        full_csv = src_submission.read_text(encoding="utf-8")
        truncated = _truncate_submission(full_csv, max_data_rows=5)
        (case_dir / "submission.csv").write_text(truncated, encoding="utf-8")
        print("  submission.csv: truncated to 5 rows")

    # 6. input.json — 竞赛元数据
    input_data = {
        "competition_id": "tabular-playground-series-may-2022",
        "task_type": "tabular",
        "metric_name": sol["metric_name"] or "auc",
        "metric_direction": "maximize",
    }
    (case_dir / "input.json").write_text(
        json.dumps(input_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # 7. plan.txt / summarize.txt — 从 output_text 截取
    plan_call = phase_map.get("plan")
    if plan_call and plan_call["output_text"]:
        (case_dir / "plan.txt").write_text(
            plan_call["output_text"],
            encoding="utf-8",
        )
        print(f"  plan.txt: {len(plan_call['output_text'])} chars")
    else:
        # plan output_text 为空时，从 turns 中提取文本
        if plan_call and plan_call["turns_json"]:
            turns = json.loads(plan_call["turns_json"])
            texts = [t.get("text", "") for t in turns if t.get("text")]
            combined = "\n\n".join(texts)
            if combined.strip():
                (case_dir / "plan.txt").write_text(combined, encoding="utf-8")
                print(f"  plan.txt: from turns text ({len(combined)} chars)")
            else:
                (case_dir / "plan.txt").write_text(
                    "(plan phase 无文本输出)",
                    encoding="utf-8",
                )
                print("  plan.txt: empty (no text in turns)")
        else:
            (case_dir / "plan.txt").write_text(
                "(plan phase 无记录)",
                encoding="utf-8",
            )

    summarize_call = phase_map.get("summarize")
    if summarize_call and summarize_call["output_text"]:
        (case_dir / "summarize.txt").write_text(
            summarize_call["output_text"],
            encoding="utf-8",
        )
        print(f"  summarize.txt: {len(summarize_call['output_text'])} chars")

    # 8. expected.json — 断言基准值
    expected = {
        "status": "completed",
        "metric_name": sol["metric_name"],
        "metric_value": sol["metric_value"],
        "exec_command": exec_log["command"] if exec_log else None,
        "exit_code": exec_log["exit_code"] if exec_log else 0,
        "duration_ms": exec_log["duration_ms"] if exec_log else None,
    }
    (case_dir / "expected.json").write_text(
        json.dumps(expected, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("  expected.json: written")


def extract_feature_extract_success(
    cur: sqlite3.Cursor,
    output_dir: Path,
) -> None:
    """截取成功的 FeatureExtract 运行回放资产。"""
    sol = _query_one(
        cur,
        "SELECT * FROM solutions WHERE operation='feature_extract' AND status='completed' "
        "ORDER BY created_at DESC LIMIT 1",
    )
    if sol is None:
        print("未找到成功的 FeatureExtract solution，跳过")
        return

    solution_id = sol["id"]
    print(f"FeatureExtract solution: {solution_id}")

    llm_calls = _query_all(
        cur,
        "SELECT phase, turns_json, output_text FROM llm_calls "
        "WHERE solution_id=? ORDER BY created_at",
        (solution_id,),
    )
    phase_map = {c["phase"]: c for c in llm_calls}

    case_dir = output_dir / "feature_extract_tabular_success_v1"
    case_dir.mkdir(parents=True, exist_ok=True)

    # input.json
    input_data = {
        "competition_id": "tabular-playground-series-may-2022",
        "task_type": "tabular",
        "metric_name": "auc",
        "metric_direction": "maximize",
    }
    (case_dir / "input.json").write_text(
        json.dumps(input_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # plan.txt
    plan_call = phase_map.get("plan")
    if plan_call and plan_call["output_text"]:
        (case_dir / "plan.txt").write_text(
            plan_call["output_text"],
            encoding="utf-8",
        )
        print(f"  plan.txt: {len(plan_call['output_text'])} chars")
    else:
        if plan_call and plan_call["turns_json"]:
            turns = json.loads(plan_call["turns_json"])
            texts = [t.get("text", "") for t in turns if t.get("text")]
            combined = "\n\n".join(texts)
            (case_dir / "plan.txt").write_text(
                combined if combined.strip() else "(plan phase 无文本输出)",
                encoding="utf-8",
            )
            print("  plan.txt: from turns text")

    # execute_raw.txt
    execute_call = phase_map.get("execute")
    if execute_call and execute_call["output_text"]:
        (case_dir / "execute_raw.txt").write_text(
            execute_call["output_text"],
            encoding="utf-8",
        )
        print(f"  execute_raw.txt: {len(execute_call['output_text'])} chars")

    # summarize.txt
    summarize_call = phase_map.get("summarize")
    if summarize_call and summarize_call["output_text"]:
        (case_dir / "summarize.txt").write_text(
            summarize_call["output_text"],
            encoding="utf-8",
        )
        print(f"  summarize.txt: {len(summarize_call['output_text'])} chars")

    # expected.json — 从 execute_raw.txt 解析出预期值
    if execute_call and execute_call["output_text"]:
        text = execute_call["output_text"]
        # 提取最后一个 JSON code block
        import re

        blocks = re.findall(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
        if blocks:
            try:
                parsed = json.loads(blocks[-1])
                (case_dir / "expected.json").write_text(
                    json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print("  expected.json: from execute_raw JSON block")
            except json.JSONDecodeError:
                print("  expected.json: JSON 解析失败，跳过")


def main() -> None:
    """主入口。"""
    import argparse

    parser = argparse.ArgumentParser(description="从 L1 运行产物截取 L2 回放资产")
    parser.add_argument(
        "--workspace",
        default="workspace/",
        help="L1 运行的工作空间目录",
    )
    parser.add_argument(
        "--output",
        default="tests/cases/replays/",
        help="回放资产输出目录",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace)
    output_dir = Path(args.output)
    db_path = workspace / "database" / "herald.db"
    working_dir = workspace / "working"

    if not db_path.exists():
        print(f"数据库不存在: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    print("=" * 60)
    print("从 L1 运行截取 L2 回放资产")
    print(f"  数据库: {db_path}")
    print(f"  工作目录: {working_dir}")
    print(f"  输出目录: {output_dir}")
    print("=" * 60)

    print("\n--- Draft Success ---")
    extract_draft_success(cur, working_dir, output_dir)

    print("\n--- FeatureExtract Success ---")
    extract_feature_extract_success(cur, output_dir)

    conn.close()
    print("\n截取完成。")


if __name__ == "__main__":
    main()
