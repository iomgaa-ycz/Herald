"""Herald M1 Agent 工具集

5 个工具，按 PES 阶段分组：
- Plan: query_l2, query_lineage, get_population_summary
- Execute: read_gene_code
- Summarize: write_l2_insight
"""

from __future__ import annotations

from typing import Any

from core.database import HeraldDB


# ========================
# Tool 1: query_l2 (未实现)
# ========================


async def query_l2(slot: str, task_type: str) -> list[dict[str, Any]]:
    """查询某 slot 的历史实验经验（L2 知识层）

    Args:
        slot: 基因位点名（如 MODEL / DATA / FEATURE_ENG）
        task_type: 任务类型（如 tabular_ml）

    Returns:
        L2 insights 列表（当前未实现）
    """
    raise NotImplementedError(
        f"query_l2(slot={slot!r}, task_type={task_type!r}) 未实现。"
        "需要先实现 HeraldDB.get_l2_insights() 的完整逻辑。"
    )


# ========================
# Tool 2: query_lineage
# ========================


def create_query_lineage(db: HeraldDB):
    """创建 query_lineage 工具（闭包捕获 db）"""

    async def query_lineage(slot: str) -> list[dict[str, Any]]:
        """查询某 slot 的历史变异记录（族谱）

        Args:
            slot: 基因位点名

        Returns:
            按 generation 升序排列的历史变异记录
        """
        return db.get_slot_history(slot)

    return query_lineage


# ========================
# Tool 3: get_population_summary
# ========================


def create_get_population_summary(db: HeraldDB):
    """创建 get_population_summary 工具"""

    async def get_population_summary() -> dict[str, Any]:
        """获取当前种群概况

        Returns:
            包含 total, best_fitness, worst_fitness, avg_fitness, solutions 的字典
        """
        return db.get_population_summary()

    return get_population_summary


# ========================
# Tool 4: read_gene_code
# ========================


def create_read_gene_code(db: HeraldDB):
    """创建 read_gene_code 工具"""

    async def read_gene_code(solution_id: str, slot: str) -> str | None:
        """读取某 Solution 某 slot 的 GENE 区域源代码

        Args:
            solution_id: Solution UUID
            slot: 基因位点名

        Returns:
            GENE 区域代码字符串，不存在返回 None
        """
        full_code = db.get_full_code(solution_id)
        if full_code is None:
            return None
        return _extract_gene_region(full_code, slot)

    return read_gene_code


def _extract_gene_region(code: str, slot: str) -> str | None:
    """从完整代码中提取指定 slot 的 GENE 区域

    Args:
        code: 完整代码
        slot: 基因位点名

    Returns:
        GENE 区域代码，未找到返回 None
    """
    import re

    # 匹配 # GENE:MODEL 或 # GENE_MODEL 格式
    pattern = rf"#\s*GENE[:_]\s*{re.escape(slot)}\b(.*?)(?=#\s*GENE[:_]|\Z)"
    match = re.search(pattern, code, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


# ========================
# Tool 5: write_l2_insight
# ========================


def create_write_l2_insight(db: HeraldDB):
    """创建 write_l2_insight 工具"""

    async def write_l2_insight(
        slot: str,
        task_type: str,
        pattern: str,
        is_support: bool,
        solution_id: str,
    ) -> str:
        """写入或更新 L2 知识条目

        Args:
            slot: 基因位点名
            task_type: 任务类型
            pattern: 知识内容（如 'XGBoost 在小数据集上比 LightGBM 稳定'）
            is_support: True=实验支撑此知识，False=实验反驳此知识
            solution_id: 产生此知识的 Solution ID

        Returns:
            操作结果描述
        """
        evidence_type = "support" if is_support else "contradict"
        insight_id = db.upsert_l2_insight(
            slot=slot,
            task_type=task_type,
            pattern=pattern,
            insight=pattern,  # pattern 同时作为 insight 内容
            solution_id=solution_id,
            evidence_type=evidence_type,
        )
        return f"upserted insight_id={insight_id}"

    return write_l2_insight


# ========================
# 工厂函数
# ========================


def create_tools(db: HeraldDB) -> list:
    """创建所有工具函数列表，供 LLMClient.call_with_tools() 使用

    Args:
        db: HeraldDB 实例

    Returns:
        工具函数列表（可直接传给 tool_runner）
    """
    return [
        query_l2,  # 未实现，会报错
        create_query_lineage(db),
        create_get_population_summary(db),
        create_read_gene_code(db),
        create_write_l2_insight(db),
    ]
