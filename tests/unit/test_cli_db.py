"""CLI db.py 命令单元测试：get-draft-detail / get-l2-insights。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.cli.db import cmd_get_draft_detail, cmd_get_l2_insights
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

    # 插入 L2 insight（关联 sol-000，run-001）
    db.upsert_l2_insight(
        slot="strategy",
        task_type="tabular",
        pattern="XGBoost 在小数据集上比 LightGBM 稳定",
        insight="详细的经验描述" * 50,
        solution_id="sol-000",
        evidence_type="support",
    )
    # 插入 L2 insight（关联 sol-002，run-001）
    db.upsert_l2_insight(
        slot="strategy",
        task_type="tabular",
        pattern="随机森林 baseline 更安全",
        insight="短经验",
        solution_id="sol-002",
        evidence_type="support",
    )

    return db


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
    """get-l2-insights 返回增强 L2 经验列表，含 solution 信息。"""
    db = _make_db(tmp_path)
    args = argparse.Namespace(
        task_type="tabular",
        run_id=None,
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
        # 原有字段
        assert "id" in item
        assert "slot" in item
        assert "pattern" in item
        assert "insight" in item
        assert "confidence" in item
        assert "status" in item
        # 新增字段
        assert "source_solution_id" in item
        assert "fitness" in item
        assert "metric_name" in item
        assert "metric_value" in item
        assert "solution_status" in item
        # insight 截断
        assert len(item["insight"]) <= 500

    # 验证关联到正确的 solution
    sol_ids = {item["source_solution_id"] for item in data}
    assert sol_ids == {"sol-000", "sol-002"}

    # 验证 fitness 值
    for item in data:
        if item["source_solution_id"] == "sol-000":
            assert item["fitness"] == 0.8
            assert item["metric_name"] == "auc"
            assert item["solution_status"] == "completed"


def test_get_l2_insights_with_run_id(tmp_path: Path, capsys: object) -> None:
    """--run-id 过滤生效。"""
    db = _make_db(tmp_path)

    # 用存在的 run-id 查询
    args = argparse.Namespace(
        task_type="tabular",
        run_id="run-001",
        limit=20,
        db_path=str(tmp_path / "herald.db"),
    )
    cmd_get_l2_insights(args)

    captured = capsys.readouterr()  # type: ignore[union-attr]
    data = json.loads(captured.out)
    assert len(data) == 2

    # 用不存在的 run-id 查询
    args2 = argparse.Namespace(
        task_type="tabular",
        run_id="run-999",
        limit=20,
        db_path=str(tmp_path / "herald.db"),
    )
    cmd_get_l2_insights(args2)
    db.close()

    captured2 = capsys.readouterr()  # type: ignore[union-attr]
    data2 = json.loads(captured2.out)
    assert len(data2) == 0


def test_get_l2_insights_limit(tmp_path: Path, capsys: object) -> None:
    """--limit 参数生效。"""
    db = _make_db(tmp_path)
    args = argparse.Namespace(
        task_type="tabular",
        run_id=None,
        limit=1,
        db_path=str(tmp_path / "herald.db"),
    )
    cmd_get_l2_insights(args)
    db.close()

    captured = capsys.readouterr()  # type: ignore[union-attr]
    data = json.loads(captured.out)
    assert len(data) == 1
