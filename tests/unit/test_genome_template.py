"""GenomeSchema 模板加载测试。"""

from __future__ import annotations

import re
from pathlib import Path

from core.pes.schema import load_genome_template

_GENE_SLOT_PATTERN = re.compile(r"# === GENE:([A-Z_]+)_START ===")


def _extract_gene_slots(template_content: str) -> list[str]:
    """从模板文本中提取 GENE slot 名。"""

    return _GENE_SLOT_PATTERN.findall(template_content)


def test_load_tabular_genome_template() -> None:
    """tabular 模板返回预期 schema 与模板文本。"""

    schema, template_content = load_genome_template("tabular")

    assert schema.task_type == "tabular"
    assert schema.template_file is not None
    assert Path(schema.template_file).is_absolute()
    assert Path(schema.template_file).name == "tabular.py"
    assert set(schema.slots) == {"DATA", "FEATURE_ENG", "MODEL", "POSTPROCESS"}
    assert "def build_model(config: dict[str, object])" in template_content
    assert _extract_gene_slots(template_content) == [
        "DATA",
        "FEATURE_ENG",
        "MODEL",
        "POSTPROCESS",
    ]


def test_load_unknown_genome_template_falls_back_to_generic() -> None:
    """未知任务类型回退到 generic 模板。"""

    schema, template_content = load_genome_template("unknown_type")

    assert schema.task_type == "generic"
    assert schema.template_file is not None
    assert Path(schema.template_file).is_absolute()
    assert Path(schema.template_file).name == "generic.py"
    assert set(schema.slots) == {"DATA", "PROCESS", "MODEL", "POSTPROCESS"}
    assert "def process(" in template_content
    assert _extract_gene_slots(template_content) == [
        "DATA",
        "PROCESS",
        "MODEL",
        "POSTPROCESS",
    ]
