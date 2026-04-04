"""MutatePES 集成测试：验证 plan → execute → summarize 三阶段流程。"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.database.herald_db import HeraldDB
from core.pes.config import load_pes_config
from core.pes.gene_utils import parse_genes_from_code
from core.pes.mutate import MutatePES
from core.pes.types import PESSolution
from core.workspace import Workspace


PARENT_CODE = """\
import os
DATA_DIR = os.environ.get("HERALD_DATA_DIR", ".")

# === GENE:DATA_START ===
def load_data(config):
    return {"train": [1, 2, 3]}
# === GENE:DATA_END ===

# === GENE:MODEL_START ===
def build_model(config):
    return "linear", "linear"
# === GENE:MODEL_END ===

if __name__ == "__main__":
    data = load_data({})
    model, name = build_model({})
    print(f"val_metric_value=0.85")
    print(f"val_metric_name=rmse")
"""


@pytest.fixture
def integration_workspace(tmp_path):
    """创建集成测试用 workspace。"""
    ws = Workspace(str(tmp_path / "workspace"))
    competition_dir = tmp_path / "competition"
    competition_dir.mkdir()
    (competition_dir / "description.md").write_text("test competition")
    ws.create(str(competition_dir))
    return ws


@pytest.fixture
def integration_db(integration_workspace):
    """创建集成测试用 DB。"""
    return HeraldDB(str(integration_workspace.db_path))


def test_parent_code_placed_in_workspace(integration_workspace, integration_db):
    """验证 _place_parent_code 能将父代码落盘。"""
    parent_id = "parent-test-id"
    integration_db.insert_solution({
        "id": parent_id,
        "generation": 0,
        "operation": "draft",
        "status": "completed",
        "created_at": "2026-04-01T00:00:00Z",
        "parent_ids": [],
        "fitness": 0.85,
    })
    integration_db.insert_code_snapshot(parent_id, PARENT_CODE)

    config = load_pes_config(
        Path(__file__).resolve().parents[2] / "config" / "pes" / "mutate.yaml"
    )
    from unittest.mock import MagicMock
    pes = MutatePES(
        config=config,
        llm=MagicMock(),
        db=integration_db,
        workspace=integration_workspace,
    )

    pes._place_parent_code(parent_id)
    parent_path = integration_workspace.working_dir / "solution_parent.py"
    assert parent_path.exists()
    assert "load_data" in parent_path.read_text()


def test_gene_parsing_from_parent_code(integration_db):
    """验证从 code_snapshot 解析出 genes。"""
    parent_id = "parse-test-id"
    integration_db.insert_solution({
        "id": parent_id,
        "generation": 0,
        "operation": "draft",
        "status": "completed",
        "created_at": "2026-04-01T00:00:00Z",
        "parent_ids": [],
    })
    integration_db.insert_code_snapshot(parent_id, PARENT_CODE)

    code = integration_db.get_full_code(parent_id)
    genes = parse_genes_from_code(code)
    assert "DATA" in genes
    assert "MODEL" in genes
    assert "load_data" in genes["DATA"]


def test_mutation_plan_context_building(integration_workspace, integration_db):
    """验证 plan 阶段的变异上下文构建。"""
    parent_id = "ctx-test-parent"
    integration_db.insert_solution({
        "id": parent_id,
        "generation": 0,
        "operation": "draft",
        "status": "completed",
        "created_at": "2026-04-01T00:00:00Z",
        "parent_ids": [],
        "fitness": 0.85,
        "summarize_insight": "# 建议方向\nDATA 的数据加载需要改进",
    })
    integration_db.insert_code_snapshot(parent_id, PARENT_CODE)

    config = load_pes_config(
        Path(__file__).resolve().parents[2] / "config" / "pes" / "mutate.yaml"
    )
    from unittest.mock import MagicMock
    pes = MutatePES(
        config=config,
        llm=MagicMock(),
        db=integration_db,
        workspace=integration_workspace,
        runtime_context={"run_id": "test-run"},
    )

    parent_solution = PESSolution(
        id=parent_id,
        operation="draft",
        generation=0,
        status="completed",
        created_at="2026-04-01T00:00:00Z",
        parent_ids=[],
        lineage=None,
        run_id="test-run",
        summarize_insight="# 建议方向\nDATA 的数据加载需要改进",
    )

    context = pes._build_mutation_plan_context(parent_solution)
    assert "parent_genes" in context
    assert "mutation_candidates" in context
    assert "DATA" in context["parent_genes"]
    assert "MODEL" in context["parent_genes"]
    # DATA should be prioritized (mentioned in summarize)
    candidates = context["mutation_candidates"]
    assert candidates[0]["slot"] == "DATA"
    assert candidates[0]["reason"] == "summarize_mentioned"
