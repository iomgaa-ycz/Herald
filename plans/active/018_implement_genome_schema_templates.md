# 018: 实现 GenomeSchema 模板体系

## 元信息
- 状态: draft
- 创建: 2026-03-28
- 对应 TD: Task 2（§6.2）

## 1. 摘要

为不同任务类型提供代码模板骨架。实现 `load_genome_template()` 函数根据 `task_type` 返回对应的 `GenomeSchema` 定义和 Python 代码模板内容，为 DraftPES 的 prompt 提供 `template_content`（代码骨架）和 `schema`（slot 结构）。

## 2. 审查点

1. **模板文件路径约定**: `config/genome_templates/` 作为模板目录，`tabular.py` / `generic.py` 作为模板文件
2. **GENE 标记解析策略**: 仅定义 `load_genome_template()` 返回原始模板字符串，**暂不实现** slot 解析逻辑（后续任务需要时再做）
3. **GenomeSchema 新字段**: `template_file: str | None` 存储模板文件绝对路径，`load_genome_template()` 额外返回 `template_content` 字符串

## 3. 流程图 / 伪代码

```
load_genome_template(task_type: str)
  │
  ├── 确定 task_type 对应的模板名:
  │     if task_type == "tabular":
  │         template_name = "tabular"
  │     else:
  │         template_name = "generic"  # 兜底
  │
  ├── 构建模板文件路径:
  │     template_dir = Path("config/genome_templates")
  │     template_path = template_dir / f"{template_name}.py"
  │
  ├── 读取模板内容:
  │     template_content = template_path.read_text(encoding="utf-8")
  │
  ├── 构建 GenomeSchema:
  │     schema = TABULAR_SCHEMA if template_name == "tabular" else GENERIC_SCHEMA
  │     schema.template_file = str(template_path.resolve())
  │
  └── return (schema, template_content)


预定义常量:

TABULAR_SCHEMA = GenomeSchema(
    task_type="tabular",
    slots={
        "DATA": SlotContract(
            function_name="load_data",
            params=[{"name": "config", "type": "dict"}],
            return_type='{"train": DataFrame, "val": DataFrame, "test": DataFrame, "target": ndarray}'
        ),
        "FEATURE_ENG": SlotContract(
            function_name="build_features",
            params=[{"name": "data", "type": "dict"}, {"name": "config", "type": "dict"}],
            return_type='{"train": DataFrame, "val": DataFrame, "test": DataFrame}'
        ),
        "MODEL": SlotContract(
            function_name="build_model",
            params=[{"name": "config", "type": "dict"}],
            return_type="(model_instance, model_type: str)"
        ),
        "POSTPROCESS": SlotContract(
            function_name="build_postprocess",
            params=[{"name": "config", "type": "dict"}],
            return_type='{"predict_fn": callable, "format_output": callable}'
        ),
    },
    template_file=None  # 运行时填充
)

GENERIC_SCHEMA = GenomeSchema(
    task_type="generic",
    slots={
        "DATA": SlotContract(
            function_name="load_data",
            params=[{"name": "config", "type": "dict"}],
            return_type="dict"
        ),
        "PROCESS": SlotContract(
            function_name="process",
            params=[{"name": "data", "type": "dict"}, {"name": "config", "type": "dict"}],
            return_type="dict"
        ),
        "MODEL": SlotContract(
            function_name="build_model",
            params=[{"name": "config", "type": "dict"}],
            return_type="Any"
        ),
        "POSTPROCESS": SlotContract(
            function_name="build_postprocess",
            params=[{"name": "config", "type": "dict"}],
            return_type='{"predict_fn": callable, "format_output": callable}'
        ),
    },
    template_file=None  # 运行时填充
)
```

**与现有代码嵌合**:
- `GenomeSchema` 已在 `core/pes/schema.py` 定义，只需新增 `template_file` 字段
- `FeatureExtractPES` 在 execute 阶段根据 `task_spec.task_type` 调用 `load_genome_template()`
- DraftPES 的 prompt context 通过 `schema` + `template_content` 注入代码骨架信息

## 4. 拟议变更

### 4.1 新建文件

| 文件 | 标识 | 说明 |
|------|------|------|
| `config/genome_templates/tabular.py` | [NEW] | Tabular 任务代码模板（基于 `Reference/tabular_ml.py`） |
| `config/genome_templates/generic.py` | [NEW] | 通用任务代码模板（兜底模板） |
| `tests/unit/test_genome_template.py` | [NEW] | 模板加载测试 |

### 4.2 修改文件

| 文件 | 标识 | 变更 |
|------|------|------|
| `core/pes/schema.py` | [MODIFY] | 添加 `template_file` 字段、`load_genome_template()` 函数、`TABULAR_SCHEMA` / `GENERIC_SCHEMA` 常量 |

### 4.3 各文件详细设计

#### 4.3.1 `core/pes/schema.py` [MODIFY]

```python
"""GenomeSchema 与模板加载。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    template_file: str | None = None  # [NEW] 模板文件绝对路径


# [NEW] 预定义 slot 契约
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
    """返回 tabular 类型的 GenomeSchema（不含 template_file）。"""
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
    """返回 generic 类型的 GenomeSchema（不含 template_file）。"""
    return GenomeSchema(
        task_type="generic",
        slots={
            "DATA": _GENERIC_DATA_SLOT,
            "PROCESS": _GENERIC_PROCESS_SLOT,
            "MODEL": _GENERIC_MODEL_SLOT,
            "POSTPROCESS": _GENERIC_POSTPROCESS_SLOT,
        },
    )


# 模板目录相对路径
_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "config" / "genome_templates"


def load_genome_template(task_type: str) -> tuple[GenomeSchema, str]:
    """根据 task_type 加载 GenomeSchema 和代码模板内容。

    Args:
        task_type: 任务类型（"tabular" / 其他）

    Returns:
        (schema, template_content) 元组
        - schema: GenomeSchema 实例，含 slot 定义和 template_file 路径
        - template_content: Python 代码模板字符串
    """
    # 确定模板名
    if task_type == "tabular":
        template_name = "tabular"
        schema = get_tabular_schema()
    else:
        template_name = "generic"
        schema = get_generic_schema()

    # 读取模板文件
    template_path = _TEMPLATE_DIR / f"{template_name}.py"
    template_content = template_path.read_text(encoding="utf-8")

    # 填充 template_file
    schema.template_file = str(template_path.resolve())

    return schema, template_content
```

#### 4.3.2 `config/genome_templates/tabular.py` [NEW]

基于 `Reference/tabular_ml.py`，保持完全一致的 GENE/FIXED 标记格式：

```python
# templates/tabular.py
"""Tabular 任务代码模板。

包含四个可替换的 slot：DATA / FEATURE_ENG / MODEL / POSTPROCESS
固定区域：EVALUATE / TRAIN_LOOP / ENTRY
"""
import json
import os
import sys

DATA_DIR = os.environ["HERALD_DATA_DIR"]  # 由沙箱注入

# === GENE:DATA_START ===
def load_data(config):
    """从 DATA_DIR 读取数据。

    Args:
        config: 配置字典

    Returns:
        {"train": DataFrame, "val": DataFrame, "test": DataFrame, "target": ndarray}
    """
    pass  # LLM 填充
# === GENE:DATA_END ===

# === GENE:FEATURE_ENG_START ===
def build_features(data, config):
    """特征工程。

    Args:
        data: load_data 返回值
        config: 配置字典

    Returns:
        {"train": DataFrame, "val": DataFrame, "test": DataFrame}
    """
    pass  # LLM 填充
# === GENE:FEATURE_ENG_END ===

# === GENE:MODEL_START ===
def build_model(config):
    """模型构建。

    Args:
        config: 配置字典

    Returns:
        (model_instance, model_type: "xgboost" | "lightgbm" | "catboost" | "nn")
    """
    pass  # LLM 填充
# === GENE:MODEL_END ===

# === GENE:POSTPROCESS_START ===
def build_postprocess(config):
    """后处理。

    Args:
        config: 配置字典

    Returns:
        {"predict_fn": callable, "format_output": callable}
    """
    pass  # LLM 填充
# === GENE:POSTPROCESS_END ===

# === FIXED:EVALUATE ===
def evaluate(y_pred, y_true, config):
    """评估模型性能。

    Args:
        y_pred: 模型预测值
        y_true: 真实标签
        config: 配置字典，必须包含 metric_name

    Returns:
        float: 评估分数
    """
    raise NotImplementedError("必须按 metric_name 显式实现 evaluate()")
# === FIXED:EVALUATE_END ===

# === FIXED:TRAIN_LOOP ===
def main(config):
    """主训练循环。"""
    # 1. 数据加载
    data = load_data(config)

    # 2. 特征工程
    features = build_features(data, config)

    # 3. 模型构建与训练
    model, model_type = build_model(config)
    model.fit(features["train"], data["target"])

    # 4. 预测与后处理
    postprocess = build_postprocess(config)
    val_pred = postprocess["predict_fn"](model, features["val"])
    test_pred = postprocess["predict_fn"](model, features["test"])
    test_output = postprocess["format_output"](test_pred)

    # 5. 评估
    metric_name = config.get("metric_name")
    if not metric_name:
        raise ValueError("config.metric_name 不能为空")

    metric_value = evaluate(val_pred, data["val_target"], config)

    # 6. 保存 submission
    submission_path = os.path.join(os.getcwd(), "submission.csv")

    return {
        "metric_name": metric_name,
        "metric_value": float(metric_value),
        "model_type": model_type,
    }
# === FIXED:TRAIN_LOOP_END ===

# === FIXED:ENTRY ===
if __name__ == "__main__":
    config = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    metrics = main(config)
    print(json.dumps(metrics))
# === FIXED:ENTRY_END ===
```

#### 4.3.3 `config/genome_templates/generic.py` [NEW]

通用模板，兼容非 tabular 任务：

```python
# templates/generic.py
"""通用任务代码模板。

包含四个可替换的 slot：DATA / PROCESS / MODEL / POSTPROCESS
固定区域：EVALUATE / MAIN / ENTRY
"""
import json
import os
import sys

DATA_DIR = os.environ["HERALD_DATA_DIR"]  # 由沙箱注入

# === GENE:DATA_START ===
def load_data(config):
    """从 DATA_DIR 读取数据。

    Args:
        config: 配置字典

    Returns:
        dict: 数据字典
    """
    pass  # LLM 填充
# === GENE:DATA_END ===

# === GENE:PROCESS_START ===
def process(data, config):
    """数据处理。

    Args:
        data: load_data 返回值
        config: 配置字典

    Returns:
        dict: 处理后的数据
    """
    pass  # LLM 填充
# === GENE:PROCESS_END ===

# === GENE:MODEL_START ===
def build_model(config):
    """模型构建。

    Args:
        config: 配置字典

    Returns:
        Any: 模型实例
    """
    pass  # LLM 填充
# === GENE:MODEL_END ===

# === GENE:POSTPROCESS_START ===
def build_postprocess(config):
    """后处理。

    Args:
        config: 配置字典

    Returns:
        {"predict_fn": callable, "format_output": callable}
    """
    pass  # LLM 填充
# === GENE:POSTPROCESS_END ===

# === FIXED:EVALUATE ===
def evaluate(y_pred, y_true, config):
    """评估模型性能。

    Args:
        y_pred: 模型预测值
        y_true: 真实标签
        config: 配置字典，必须包含 metric_name

    Returns:
        float: 评估分数
    """
    raise NotImplementedError("必须按 metric_name 显式实现 evaluate()")
# === FIXED:EVALUATE_END ===

# === FIXED:MAIN ===
def main(config):
    """主流程。"""
    # 1. 数据加载
    data = load_data(config)

    # 2. 数据处理
    processed = process(data, config)

    # 3. 模型构建
    model = build_model(config)

    # 4. 预测与后处理
    postprocess = build_postprocess(config)
    # 注：通用模板的具体调用方式由 LLM 根据任务类型填充

    # 5. 评估
    metric_name = config.get("metric_name")
    if not metric_name:
        raise ValueError("config.metric_name 不能为空")

    # 6. 保存 submission
    submission_path = os.path.join(os.getcwd(), "submission.csv")

    return {
        "metric_name": metric_name,
        "metric_value": 0.0,  # 由 evaluate 填充
    }
# === FIXED:MAIN_END ===

# === FIXED:ENTRY ===
if __name__ == "__main__":
    config = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    metrics = main(config)
    print(json.dumps(metrics))
# === FIXED:ENTRY_END ===
```

#### 4.3.4 `tests/unit/test_genome_template.py` [NEW]

```python
"""GenomeSchema 模板加载测试。"""

from pathlib import Path

import pytest

from core.pes.schema import (
    GenomeSchema,
    SlotContract,
    load_genome_template,
    get_tabular_schema,
    get_generic_schema,
)


class TestSchemaDefinitions:
    """测试 Schema 定义。"""

    def test_tabular_schema_has_four_slots(self):
        """tabular schema 必须有四个 slot。"""
        schema = get_tabular_schema()
        assert schema.task_type == "tabular"
        assert set(schema.slots.keys()) == {"DATA", "FEATURE_ENG", "MODEL", "POSTPROCESS"}

    def test_generic_schema_has_four_slots(self):
        """generic schema 必须有四个 slot。"""
        schema = get_generic_schema()
        assert schema.task_type == "generic"
        assert set(schema.slots.keys()) == {"DATA", "PROCESS", "MODEL", "POSTPROCESS"}

    def test_slot_contract_fields(self):
        """SlotContract 字段正确。"""
        schema = get_tabular_schema()
        data_slot = schema.slots["DATA"]
        assert isinstance(data_slot, SlotContract)
        assert data_slot.function_name == "load_data"
        assert len(data_slot.params) == 1


class TestLoadGenomeTemplate:
    """测试 load_genome_template 函数。"""

    def test_load_tabular_returns_schema_with_template(self):
        """加载 tabular 模板返回 schema 和 template_content。"""
        schema, content = load_genome_template("tabular")

        assert schema.task_type == "tabular"
        assert schema.template_file is not None
        assert schema.template_file.endswith("tabular.py")
        assert len(content) > 0

    def test_load_unknown_returns_generic(self):
        """未知 task_type 返回 generic 模板。"""
        schema, content = load_genome_template("unknown_type")

        assert schema.task_type == "generic"
        assert schema.template_file is not None
        assert schema.template_file.endswith("generic.py")
        assert len(content) > 0

    def test_tabular_template_has_gene_markers(self):
        """tabular 模板包含 GENE 标记。"""
        schema, content = load_genome_template("tabular")

        # 检查四个 GENE 区域
        assert "# === GENE:DATA_START ===" in content
        assert "# === GENE:DATA_END ===" in content
        assert "# === GENE:FEATURE_ENG_START ===" in content
        assert "# === GENE:FEATURE_ENG_END ===" in content
        assert "# === GENE:MODEL_START ===" in content
        assert "# === GENE:MODEL_END ===" in content
        assert "# === GENE:POSTPROCESS_START ===" in content
        assert "# === GENE:POSTPROCESS_END ===" in content

    def test_tabular_template_has_fixed_markers(self):
        """tabular 模板包含 FIXED 标记。"""
        schema, content = load_genome_template("tabular")

        assert "# === FIXED:EVALUATE ===" in content
        assert "# === FIXED:EVALUATE_END ===" in content
        assert "# === FIXED:TRAIN_LOOP ===" in content
        assert "# === FIXED:TRAIN_LOOP_END ===" in content
        assert "# === FIXED:ENTRY ===" in content
        assert "# === FIXED:ENTRY_END ===" in content

    def test_generic_template_has_gene_markers(self):
        """generic 模板包含 GENE 标记。"""
        schema, content = load_genome_template("generic")

        assert "# === GENE:DATA_START ===" in content
        assert "# === GENE:DATA_END ===" in content
        assert "# === GENE:PROCESS_START ===" in content
        assert "# === GENE:PROCESS_END ===" in content
        assert "# === GENE:MODEL_START ===" in content
        assert "# === GENE:MODEL_END ===" in content
        assert "# === GENE:POSTPROCESS_START ===" in content
        assert "# === GENE:POSTPROCESS_END ===" in content

    def test_template_file_path_is_absolute(self):
        """template_file 是绝对路径。"""
        schema, content = load_genome_template("tabular")

        assert Path(schema.template_file).is_absolute()
        assert Path(schema.template_file).exists()


class TestTemplateContentValidity:
    """测试模板内容有效性。"""

    def test_tabular_template_is_valid_python(self):
        """tabular 模板是有效的 Python 语法。"""
        schema, content = load_genome_template("tabular")

        # 尝试编译检查语法
        compile(content, "<string>", "exec")

    def test_generic_template_is_valid_python(self):
        """generic 模板是有效的 Python 语法。"""
        schema, content = load_genome_template("generic")

        # 尝试编译检查语法
        compile(content, "<string>", "exec")

    def test_tabular_template_has_data_dir_env(self):
        """tabular 模板使用 HERALD_DATA_DIR 环境变量。"""
        schema, content = load_genome_template("tabular")

        assert 'DATA_DIR = os.environ["HERALD_DATA_DIR"]' in content
```

## 5. 验证计划

### 5.1 单元测试
```bash
conda activate herald && python -m pytest tests/unit/test_genome_template.py -v
```

### 5.2 回归验证
```bash
python -m pytest tests/unit/test_draft_pes.py tests/unit/test_prompt_manager.py -v
```

### 5.3 代码质量
```bash
ruff check core/pes/schema.py config/genome_templates/ tests/unit/test_genome_template.py --fix
ruff format core/pes/schema.py config/genome_templates/ tests/unit/test_genome_template.py
```

### 5.4 冒烟验证
```bash
python -c "from core.pes.schema import load_genome_template; schema, content = load_genome_template('tabular'); print(f'task_type={schema.task_type}, slots={list(schema.slots.keys())}, content_len={len(content)}')"
```

### 5.5 通过标准（TD §6.2）
- [ ] `load_genome_template("tabular")` 返回含 4 个 slot 的 GenomeSchema + 非空 template_content
- [ ] `load_genome_template("unknown")` 返回 generic 模板
- [ ] tabular 模板中 GENE 标记区域可被识别
