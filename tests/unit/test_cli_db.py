"""CLI db.py 新命令单元测试：list-drafts / get-draft-detail / get-l2-insights。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.cli.db import cmd_get_draft_detail, cmd_get_l2_insights, cmd_list_drafts
from core.database.herald_db import HeraldDB
from core.pes.types import PESSolution
from core.utils.utils import utc_now_iso


def _make_db(tmp_path: Path) -> HeraldDB:
    """创建临时 HeraldDB 并插入测试数据。"""
    db = HeraldDB(str(tmp_path / "herald.db"))

    for i in range(5):
        sol = PESSolution(
            id=f"sol-{i:03d}",
            operation="draft",
            generation=i,
            status="completed" if i % 2 == 0 else "failed",
            created_at=utc_now_iso(),
            parent_ids=[],
            lineage="solution",
            run_id="run-001",
        )
        record = sol.to_record()
        record["fitness"] = 0.8 + i * 0.01 if i % 2 == 0 else None
        record["metric_name"] = "auc" if i % 2 == 0 else None
        record["metric_value"] = record["fitness"]
        record["summarize_insight"] = (
            f"# 摘要\n第 {i} 次 draft 采用了策略 {chr(65 + i)}。\n\n"
            f"# 策略选择\n详细描述。\n\n# 执行结果\n结果。\n\n"
            f"# 关键发现\n发现。\n\n# 建议方向\n建议。"
            if i % 2 == 0
            else None
        )
        db.insert_solution(record)

    # 插入 L2 insight
    db.upsert_l2_insight(
        slot="strategy",
        task_type="tabular",
        pattern="XGBoost 在小数据集上比 LightGBM 稳定",
        insight="详细的经验描述" * 50,
        solution_id="sol-000",
        evidence_type="support",
    )
    db.upsert_l2_insight(
        slot="strategy",
        task_type="tabular",
        pattern="随机森林 baseline 更安全",
        insight="短经验",
        solution_id="sol-002",
        evidence_type="support",
    )

    return db


def test_list_drafts_json_format(tmp_path: Path, capsys: object) -> None:
    """list-drafts 输出 JSON 格式正确，含 summary_excerpt。"""
    db = _make_db(tmp_path)
    args = argparse.Namespace(
        run_id="run-001",
        limit=20,
        status="all",
        db_path=str(tmp_path / "herald.db"),
    )
    cmd_list_drafts(args)
    db.close()

    captured = capsys.readouterr()  # type: ignore[union-attr]
    data = json.loads(captured.out)

    assert isinstance(data, list)
    assert len(data) == 5
    for item in data:
        assert "solution_id" in item
        assert "generation" in item
        assert "status" in item
        assert "summary_excerpt" in item

    # completed 的行应有非空 excerpt
    completed_items = [d for d in data if d["status"] == "completed"]
    assert all(d["summary_excerpt"] != "" for d in completed_items)


def test_list_drafts_limit(tmp_path: Path, capsys: object) -> None:
    """--limit 参数生效。"""
    db = _make_db(tmp_path)
    args = argparse.Namespace(
        run_id="run-001",
        limit=2,
        status="all",
        db_path=str(tmp_path / "herald.db"),
    )
    cmd_list_drafts(args)
    db.close()

    captured = capsys.readouterr()  # type: ignore[union-attr]
    data = json.loads(captured.out)
    assert len(data) == 2


def test_list_drafts_status_filter(tmp_path: Path, capsys: object) -> None:
    """--status 过滤生效。"""
    db = _make_db(tmp_path)
    args = argparse.Namespace(
        run_id="run-001",
        limit=20,
        status="completed",
        db_path=str(tmp_path / "herald.db"),
    )
    cmd_list_drafts(args)
    db.close()

    captured = capsys.readouterr()  # type: ignore[union-attr]
    data = json.loads(captured.out)
    assert all(d["status"] == "completed" for d in data)
    assert len(data) == 3  # generation 0, 2, 4


def test_get_draft_detail_returns_full_insight(tmp_path: Path, capsys: object) -> None:
    """get-draft-detail 返回完整 summarize_insight。"""
    db = _make_db(tmp_path)
    args = argparse.Namespace(
        solution_id="sol-000",
        db_path=str(tmp_path / "herald.db"),
    )
    cmd_get_draft_detail(args)
    db.close()

    captured = capsys.readouterr()  # type: ignore[union-attr]
    data = json.loads(captured.out)
    assert data["solution_id"] == "sol-000"
    assert "# 摘要" in data["summarize_insight"]
    assert "# 建议方向" in data["summarize_insight"]


def test_get_l2_insights_json_format(tmp_path: Path, capsys: object) -> None:
    """get-l2-insights 返回 L2 经验列表，insight 被截断。"""
    db = _make_db(tmp_path)
    args = argparse.Namespace(
        task_type="tabular",
        limit=20,
        db_path=str(tmp_path / "herald.db"),
    )
    cmd_get_l2_insights(args)
    db.close()

    captured = capsys.readouterr()  # type: ignore[union-attr]
    data = json.loads(captured.out)
    assert isinstance(data, list)
    assert len(data) == 2
    for item in data:
        assert "id" in item
        assert "slot" in item
        assert "pattern" in item
        assert "insight" in item
        assert "confidence" in item
        assert "status" in item
        assert len(item["insight"]) <= 500
