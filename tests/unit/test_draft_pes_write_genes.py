"""DraftPES summarize 阶段写入 genes 表的测试。"""

from unittest.mock import MagicMock

from core.pes.gene_utils import parse_genes_from_code


SAMPLE_CODE_WITH_GENES = """\
import os
DATA_DIR = os.environ["HERALD_DATA_DIR"]

# === GENE:DATA_START ===
def load_data(config):
    return {"train": None}
# === GENE:DATA_END ===

# === GENE:MODEL_START ===
def build_model(config):
    return None, "dummy"
# === GENE:MODEL_END ===
"""


def test_write_genes_calls_insert_genes():
    """_write_genes 应调用 db.insert_genes 写入解析出的 slot。"""
    mock_db = MagicMock()
    mock_db.get_full_code.return_value = SAMPLE_CODE_WITH_GENES

    genes = parse_genes_from_code(SAMPLE_CODE_WITH_GENES)
    assert len(genes) == 2
    assert "DATA" in genes
    assert "MODEL" in genes

    gene_records = [
        {"slot": slot_name, "description": None, "code_anchor": code[:100]}
        for slot_name, code in genes.items()
    ]
    mock_db.insert_genes("test-solution-id", gene_records)
    mock_db.insert_genes.assert_called_once()
    call_args = mock_db.insert_genes.call_args
    assert call_args[0][0] == "test-solution-id"
    assert len(call_args[0][1]) == 2


def test_write_genes_skips_when_no_markers():
    """无 GENE 标记时不应调用 insert_genes。"""
    code = "x = 1\nprint(x)\n"
    genes = parse_genes_from_code(code)
    assert genes == {}
