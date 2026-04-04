"""gene_utils 单元测试。"""

from core.pes.gene_utils import parse_genes_from_code, rank_mutation_candidates


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


def test_rank_prioritizes_summarize_mentioned_slots():
    """父 summarize 中提到的 slot 应排在前面。"""
    parent_genes = ["DATA", "FEATURE_ENG", "MODEL", "POSTPROCESS"]
    summarize_insight = "# 建议方向\nFEATURE_ENG 的特征工程过于简单，建议尝试交叉特征。MODEL 部分可以保持。"
    mutate_history: list[dict] = []

    ranked = rank_mutation_candidates(
        parent_genes=parent_genes,
        summarize_insight=summarize_insight,
        mutate_history=mutate_history,
    )
    assert ranked[0]["slot"] == "FEATURE_ENG"
    assert ranked[0]["reason"] == "summarize_mentioned"


def test_rank_prioritizes_never_mutated():
    """从未变异过的 slot 应优先于已变异过的。"""
    parent_genes = ["DATA", "FEATURE_ENG", "MODEL"]
    summarize_insight = "无特别建议。"
    mutate_history = [
        {"slot": "MODEL", "fitness_delta": 0.05},
    ]

    ranked = rank_mutation_candidates(
        parent_genes=parent_genes,
        summarize_insight=summarize_insight,
        mutate_history=mutate_history,
    )
    slot_names = [r["slot"] for r in ranked]
    assert slot_names.index("DATA") < slot_names.index("MODEL")
    assert slot_names.index("FEATURE_ENG") < slot_names.index("MODEL")


def test_rank_returns_all_parent_genes():
    """排序结果应包含父方案的所有 gene。"""
    parent_genes = ["DATA", "FEATURE_ENG", "MODEL"]
    ranked = rank_mutation_candidates(
        parent_genes=parent_genes,
        summarize_insight="",
        mutate_history=[],
    )
    assert {r["slot"] for r in ranked} == {"DATA", "FEATURE_ENG", "MODEL"}
