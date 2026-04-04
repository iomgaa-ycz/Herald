"""Gene 解析与变异候选排序工具。"""

from __future__ import annotations

import re

# 匹配 # === GENE:XXX_START === ... # === GENE:XXX_END === 区域
_GENE_BLOCK_RE = re.compile(
    r"#\s*===\s*GENE:(\w+)_START\s*===\s*\n(.*?)#\s*===\s*GENE:\1_END\s*===",
    re.DOTALL,
)


def parse_genes_from_code(code: str) -> dict[str, str]:
    """从完整代码中按 GENE 标记解析出各 slot 的代码片段。

    Args:
        code: 完整 solution.py 代码

    Returns:
        ``{slot_name: code_content}`` 字典
    """

    genes: dict[str, str] = {}
    for match in _GENE_BLOCK_RE.finditer(code):
        slot_name = match.group(1)
        slot_code = match.group(2).rstrip("\n")
        genes[slot_name] = slot_code
    return genes
