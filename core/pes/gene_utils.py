"""Gene 解析与变异候选排序工具。"""

from __future__ import annotations

import re
from typing import Any

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


def rank_mutation_candidates(
    parent_genes: list[str],
    summarize_insight: str,
    mutate_history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """对候选变异 slot 排序，返回带理由的建议列表。

    排序优先级：
    1. 父 summarize_insight 中被提及需要改进的 slot
    2. 在本 run mutate 历史中从未被变异过的 slot
    3. 上次变异后 fitness 下降的 slot
    4. 其余 slot

    Args:
        parent_genes: 父方案拥有的 slot 名列表
        summarize_insight: 父方案的 summarize_insight 文本
        mutate_history: 本 run 内的 mutate 记录，每条含 ``slot`` 和 ``fitness_delta``

    Returns:
        ``[{"slot": str, "reason": str, "priority": int}, ...]``，按 priority 升序
    """

    mutated_slots = {record["slot"] for record in mutate_history}
    fitness_delta_map: dict[str, float] = {}
    for record in mutate_history:
        slot = record["slot"]
        delta = record.get("fitness_delta", 0.0)
        if delta is not None:
            fitness_delta_map[slot] = delta

    insight_upper = summarize_insight.upper()

    candidates: list[dict[str, Any]] = []
    for slot in parent_genes:
        if slot.upper() in insight_upper:
            candidates.append({
                "slot": slot,
                "reason": "summarize_mentioned",
                "priority": 1,
            })
        elif slot not in mutated_slots:
            candidates.append({
                "slot": slot,
                "reason": "never_mutated",
                "priority": 2,
            })
        elif fitness_delta_map.get(slot, 0.0) < 0:
            candidates.append({
                "slot": slot,
                "reason": "fitness_declined",
                "priority": 3,
            })
        else:
            candidates.append({
                "slot": slot,
                "reason": "default",
                "priority": 4,
            })

    candidates.sort(key=lambda c: c["priority"])
    return candidates
