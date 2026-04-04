"""gene_utils 单元测试。"""

from core.pes.gene_utils import parse_genes_from_code


SAMPLE_CODE = """\
import os

DATA_DIR = os.environ["HERALD_DATA_DIR"]


# === GENE:DATA_START ===
def load_data(config):
    import pandas as pd
    return {"train": pd.read_csv(f"{DATA_DIR}/train.csv")}
# === GENE:DATA_END ===


# === GENE:FEATURE_ENG_START ===
def build_features(data, config):
    return data
# === GENE:FEATURE_ENG_END ===


# === GENE:MODEL_START ===
def build_model(config):
    from sklearn.linear_model import LinearRegression
    return LinearRegression(), "linear"
# === GENE:MODEL_END ===
"""


def test_parse_genes_extracts_all_slots():
    """应从标记代码中提取出所有 GENE 区域。"""
    genes = parse_genes_from_code(SAMPLE_CODE)
    assert set(genes.keys()) == {"DATA", "FEATURE_ENG", "MODEL"}
    assert "load_data" in genes["DATA"]
    assert "build_features" in genes["FEATURE_ENG"]
    assert "LinearRegression" in genes["MODEL"]


def test_parse_genes_empty_code():
    """空代码应返回空字典。"""
    genes = parse_genes_from_code("")
    assert genes == {}


def test_parse_genes_no_markers():
    """无标记的代码应返回空字典。"""
    genes = parse_genes_from_code("x = 1\ny = 2\n")
    assert genes == {}


def test_parse_genes_preserves_indentation():
    """解析结果应保留原始缩进。"""
    genes = parse_genes_from_code(SAMPLE_CODE)
    # load_data 函数体内有 4 空格缩进
    assert "    import pandas" in genes["DATA"]
