"""MutatePES 单元测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.pes.config import load_pes_config
from core.pes.mutate import MutatePES
from core.pes.types import PESSolution


@pytest.fixture
def mutate_config():
    """加载 mutate YAML 配置。"""
    config_path = Path(__file__).resolve().parents[2] / "config" / "pes" / "mutate.yaml"
    return load_pes_config(config_path)


@pytest.fixture
def mock_db():
    """模拟数据库。"""
    db = MagicMock()
    db.get_full_code.return_value = (
        "# === GENE:DATA_START ===\n"
        "def load_data(c): pass\n"
        "# === GENE:DATA_END ===\n"
    )
    db.get_best_fitness.return_value = 0.85
    db.insert_solution = MagicMock()
    db.update_solution_status = MagicMock()
    db.update_solution_artifacts = MagicMock()
    db.insert_code_snapshot = MagicMock()
    db.insert_genes = MagicMock()
    db.log_llm_call = MagicMock()
    db.log_exec = MagicMock()
    db.log_contract_check = MagicMock()
    db.upsert_l2_insight = MagicMock()
    db.get_slot_history.return_value = []
    db.list_solutions_by_run_and_operation.return_value = []
    db.get_solution.return_value = None
    return db


@pytest.fixture
def mock_workspace(tmp_path):
    """模拟工作空间。"""
    ws = MagicMock()
    working_dir = tmp_path / "working"
    working_dir.mkdir()
    ws.working_dir = working_dir
    ws.data_dir = tmp_path / "data"
    ws.logs_dir = tmp_path / "logs"
    ws.db_path = tmp_path / "database" / "herald.db"
    ws.run_log_path = working_dir / "run.log"
    ws.summary.return_value = {
        "workspace_root": str(tmp_path),
        "data_dir": str(ws.data_dir),
        "working_dir": str(working_dir),
        "logs_dir": str(ws.logs_dir),
        "db_path": str(ws.db_path),
        "run_log_path": str(ws.run_log_path),
    }
    ws.get_working_file_path = lambda name: working_dir / name
    ws.get_working_submission_path = lambda name: working_dir / name
    return ws


def test_mutate_pes_instantiates(mutate_config, mock_db, mock_workspace):
    """MutatePES 应能正常实例化。"""
    pes = MutatePES(
        config=mutate_config,
        llm=MagicMock(),
        db=mock_db,
        workspace=mock_workspace,
    )
    assert pes.config.operation == "mutate"


def test_mutate_pes_create_solution_has_parent(mutate_config, mock_db, mock_workspace):
    """MutatePES 创建的 solution 应有 parent_ids。"""
    pes = MutatePES(
        config=mutate_config,
        llm=MagicMock(),
        db=mock_db,
        workspace=mock_workspace,
    )
    parent = PESSolution(
        id="parent-id",
        operation="draft",
        generation=0,
        status="completed",
        created_at="2026-04-01T00:00:00Z",
        parent_ids=[],
        lineage="parent-id",
        run_id="test-run",
        fitness=0.85,
    )
    solution = pes.create_solution(generation=1, parent_solution=parent)
    assert solution.parent_ids == ["parent-id"]
    assert solution.operation == "mutate"


def test_parse_target_slot_from_plan(mutate_config, mock_db, mock_workspace):
    """应能从 plan 输出中解析 target_slot。"""
    pes = MutatePES(
        config=mutate_config,
        llm=MagicMock(),
        db=mock_db,
        workspace=mock_workspace,
    )
    plan_text = "## 变异决策\n- 选中 Slot: FEATURE_ENG\n- 选择理由: ..."
    assert pes._parse_target_slot(plan_text) == "FEATURE_ENG"


def test_parse_target_slot_with_backticks(mutate_config, mock_db, mock_workspace):
    """应能从带反引号的 plan 输出中解析 target_slot。"""
    pes = MutatePES(
        config=mutate_config,
        llm=MagicMock(),
        db=mock_db,
        workspace=mock_workspace,
    )
    plan_text = "## 变异决策\n- 选中 Slot: `MODEL`\n- 理由: ..."
    assert pes._parse_target_slot(plan_text) == "MODEL"


def test_parse_target_slot_fallback(mutate_config, mock_db, mock_workspace):
    """降级情况下应能从 GENE:XXX 格式中解析。"""
    pes = MutatePES(
        config=mutate_config,
        llm=MagicMock(),
        db=mock_db,
        workspace=mock_workspace,
    )
    plan_text = "我决定修改 GENE:DATA 区域的代码"
    assert pes._parse_target_slot(plan_text) == "DATA"


def test_place_parent_code(mutate_config, mock_db, mock_workspace):
    """应将父代码落盘到 solution_parent.py。"""
    pes = MutatePES(
        config=mutate_config,
        llm=MagicMock(),
        db=mock_db,
        workspace=mock_workspace,
    )
    pes._place_parent_code("parent-id")
    parent_path = mock_workspace.working_dir / "solution_parent.py"
    assert parent_path.exists()
    content = parent_path.read_text()
    assert "GENE:DATA_START" in content


def test_resolve_parent_solution_returns_none_when_no_id(mutate_config, mock_db, mock_workspace):
    """无 parent_solution_id 时返回 None。"""
    pes = MutatePES(
        config=mutate_config,
        llm=MagicMock(),
        db=mock_db,
        workspace=mock_workspace,
    )
    pes._execution_context = {}
    assert pes._resolve_parent_solution() is None


def test_get_mutate_history_empty(mutate_config, mock_db, mock_workspace):
    """无 mutate 历史时返回空列表。"""
    pes = MutatePES(
        config=mutate_config,
        llm=MagicMock(),
        db=mock_db,
        workspace=mock_workspace,
        runtime_context={"run_id": "test-run"},
    )
    history = pes._get_mutate_history()
    assert history == []
