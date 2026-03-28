"""GenomeSchema 与模板加载定义。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# Phase 1: 基础类型
@dataclass(slots=True)
class TaskSpec:
    """任务规格。"""

    task_type: str
    competition_name: str
    objective: str
    metric_name: str
    metric_direction: str


@dataclass(slots=True)
class SlotContract:
    """单个 slot 的契约。"""

    function_name: str
    params: list[dict[str, str]]
    return_type: str


@dataclass(slots=True)
class GenomeSchema:
    """Genome 结构定义。"""

    task_type: str
    slots: dict[str, SlotContract | None]
    template_file: str | None = None


# Phase 2: 预定义 Slot 契约
_TABULAR_DATA_SLOT = SlotContract(
    function_name="load_data",
    params=[{"name": "config", "type": "dict"}],
    return_type='{"train": DataFrame, "val": DataFrame, "test": DataFrame, "target": ndarray}',
)

_TABULAR_FEATURE_ENG_SLOT = SlotContract(
    function_name="build_features",
    params=[{"name": "data", "type": "dict"}, {"name": "config", "type": "dict"}],
    return_type='{"train": DataFrame, "val": DataFrame, "test": DataFrame}',
)

_TABULAR_MODEL_SLOT = SlotContract(
    function_name="build_model",
    params=[{"name": "config", "type": "dict"}],
    return_type="(model_instance, model_type: str)",
)

_TABULAR_POSTPROCESS_SLOT = SlotContract(
    function_name="build_postprocess",
    params=[{"name": "config", "type": "dict"}],
    return_type='{"predict_fn": callable, "format_output": callable}',
)

_GENERIC_DATA_SLOT = SlotContract(
    function_name="load_data",
    params=[{"name": "config", "type": "dict"}],
    return_type="dict",
)

_GENERIC_PROCESS_SLOT = SlotContract(
    function_name="process",
    params=[{"name": "data", "type": "dict"}, {"name": "config", "type": "dict"}],
    return_type="dict",
)

_GENERIC_MODEL_SLOT = SlotContract(
    function_name="build_model",
    params=[{"name": "config", "type": "dict"}],
    return_type="Any",
)

_GENERIC_POSTPROCESS_SLOT = SlotContract(
    function_name="build_postprocess",
    params=[{"name": "config", "type": "dict"}],
    return_type='{"predict_fn": callable, "format_output": callable}',
)


def get_tabular_schema() -> GenomeSchema:
    """返回 tabular 类型的 GenomeSchema。"""

    return GenomeSchema(
        task_type="tabular",
        slots={
            "DATA": _TABULAR_DATA_SLOT,
            "FEATURE_ENG": _TABULAR_FEATURE_ENG_SLOT,
            "MODEL": _TABULAR_MODEL_SLOT,
            "POSTPROCESS": _TABULAR_POSTPROCESS_SLOT,
        },
    )


def get_generic_schema() -> GenomeSchema:
    """返回 generic 类型的 GenomeSchema。"""

    return GenomeSchema(
        task_type="generic",
        slots={
            "DATA": _GENERIC_DATA_SLOT,
            "PROCESS": _GENERIC_PROCESS_SLOT,
            "MODEL": _GENERIC_MODEL_SLOT,
            "POSTPROCESS": _GENERIC_POSTPROCESS_SLOT,
        },
    )


# Phase 3: 模板加载
_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "config" / "genome_templates"


def load_genome_template(task_type: str) -> tuple[GenomeSchema, str]:
    """根据任务类型加载 GenomeSchema 与模板内容。

    Args:
        task_type: 任务类型，当前支持 ``tabular``，其他值回退到 ``generic``。

    Returns:
        ``(schema, template_content)`` 元组。
    """

    if task_type == "tabular":
        template_name = "tabular"
        schema = get_tabular_schema()
    else:
        template_name = "generic"
        schema = get_generic_schema()

    template_path = (_TEMPLATE_DIR / f"{template_name}.py").resolve()
    template_content = template_path.read_text(encoding="utf-8")
    schema.template_file = str(template_path)
    return schema, template_content
