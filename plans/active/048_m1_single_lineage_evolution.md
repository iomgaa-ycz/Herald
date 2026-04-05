# M1: 单谱系进化 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已完成的多 Draft 差异化生成（M0.7）基础上，实现 Gene 级 MutatePES 闭环——选择 best Solution 作为 parent，由 Harness 推荐候选变异 slot，LLM 最终决定变异哪个 Gene 并生成新代码，通过 diff skill 做变异纯度检查。

**Architecture:** MutatePES 继承 BasePES 三阶段骨架，复用 DraftPES 的 execute 产物契约（代码落盘、语法校验、metrics 提取、submission 校验）。新增 gene 解析函数从 `GENE:XXX_START/END` 标记中拆分 slot 代码，DraftPES Summarize 阶段同步写入 genes 表。Scheduler 新增 mutate stage，parent 选择硬编码为 best fitness。

**Tech Stack:** Python 3.11+, SQLite, Jinja2, Claude Agent SDK, pytest

---

## 文件结构

| 文件 | 变更类型 | 职责 |
|------|----------|------|
| `core/pes/gene_utils.py` | NEW | gene 解析工具：`parse_genes_from_code()` + `rank_mutation_candidates()` |
| `core/pes/mutate.py` | NEW | MutatePES 实现 |
| `config/pes/mutate.yaml` | NEW | MutatePES 阶段配�� |
| `config/prompts/templates/mutate_plan.j2` | NEW | mutate plan 阶段 prompt 模板 |
| `config/prompts/templates/mutate_execute.j2` | NEW | mutate execute 阶段 prompt 模板 |
| `config/prompts/templates/mutate_summarize.j2` | NEW | mutate summarize ���段 prompt 模�� |
| `config/prompts/prompt_spec.yaml` | MODIFY | 新增 mutate_plan/execute/summarize 三个模板配置 |
| `core/prompts/skills/mutate-diff-check/SKILL.md` | NEW | 变异纯度检查 skill |
| `core/pes/draft.py` | MODIFY | Summarize 阶段新增 `_write_genes()` 调用 |
| `core/main.py` | MODIFY | 新增 `bootstrap_mutate_pes()` + Scheduler 增加 mutate stage |
| `core/scheduler/scheduler.py` | MODIFY | `_run_stage()` 支持 mutate 阶段的 parent 选择 |
| `docs/architecture.md` | MODIFY | §5/§9/§10 更新当前状态 |
| `tests/unit/test_gene_utils.py` | NEW | gene 解析与候选排序测试 |
| `tests/unit/test_mutate_pes.py` | NEW | MutatePES 单元测�� |
| `tests/unit/test_draft_pes_write_genes.py` | NEW | DraftPES genes 写入测试 |
| `tests/integration/test_mutate_pes_flow.py` | NEW | MutatePES 集成测试 |

---

### Task 1: gene 解析工具函数 — `parse_genes_from_code()`

**Files:**
- Create: `core/pes/gene_utils.py`
- Test: `tests/unit/test_gene_utils.py`

- [ ] **Step 1: 写失败测试 — 从标记代码中解析出各 slot**

```python
# tests/unit/test_gene_utils.py
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/iomgaa/Projects/Herald2 && python -m pytest tests/unit/test_gene_utils.py -v
```

预期：FAIL，`ModuleNotFoundError: No module named 'core.pes.gene_utils'`

- [ ] **Step 3: 实现 `parse_genes_from_code()`**

```python
# core/pes/gene_utils.py
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /home/iomgaa/Projects/Herald2 && python -m pytest tests/unit/test_gene_utils.py -v
```

预期：4 tests PASS

- [ ] **Step 5: 提交**

```bash
cd /home/iomgaa/Projects/Herald2 && git add core/pes/gene_utils.py tests/unit/test_gene_utils.py && git commit -m "feat: 新增 parse_genes_from_code 从 GENE 标记解析 slot ���码"
```

---

### Task 2: DraftPES Summarize 阶段写入 genes 表

**Files:**
- Modify: `core/pes/draft.py` (在 `_archive_completed_solution` 附近)
- Test: `tests/unit/test_draft_pes_write_genes.py`

- [ ] **Step 1: 写失败测试 — Summarize 完成后 genes 表有数据**

```python
# tests/unit/test_draft_pes_write_genes.py
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
    """_write_genes 应调用 db.insert_genes 写入��析出的 slot。"""
    mock_db = MagicMock()
    mock_db.get_full_code.return_value = SAMPLE_CODE_WITH_GENES

    # 直接测试 parse + insert 逻辑
    genes = parse_genes_from_code(SAMPLE_CODE_WITH_GENES)
    assert len(genes) == 2
    assert "DATA" in genes
    assert "MODEL" in genes

    # 模拟 insert_genes 的调用格式
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
```

- [ ] **Step 2: ���行测试确认通过（纯逻辑测试，不依赖 DraftPES 实例）**

```bash
cd /home/iomgaa/Projects/Herald2 && python -m pytest tests/unit/test_draft_pes_write_genes.py -v
```

预期：PASS（此测试验证 gene_utils 的输出格式与 DB 接口的对接逻辑）

- [ ] **Step 3: 修改 `core/pes/draft.py` — 在 Summarize 阶段写入 genes**

在 `draft.py` 顶部导入新增：

```python
from core.pes.gene_utils import parse_genes_from_code
```

在 `handle_phase_response` 的 `summarize` 分支中，在 `self._archive_completed_solution(solution)` 之后、`self._write_l2_knowledge(solution)` 之前新增调用：

```python
            self._archive_completed_solution(solution)
            self._write_genes(solution)  # 新增
            self._write_l2_knowledge(solution)
```

新增方法 `_write_genes`（放在 `_archive_completed_solution` 方法之后）：

```python
    def _write_genes(self, solution: PESSolution) -> None:
        """从 code_snapshots 解析 GENE 标记并写入 genes 表。"""

        if self.db is None or not hasattr(self.db, "insert_genes"):
            return

        code = self.db.get_full_code(solution.id)
        if code is None:
            logger.warning(
                "genes 写入跳过：无 code_snapshot [solution_id=%s]", solution.id
            )
            return

        genes = parse_genes_from_code(code)
        if not genes:
            logger.info(
                "genes 写入跳过：代码无 GENE 标记 [solution_id=%s]", solution.id
            )
            return

        gene_records = [
            {
                "slot": slot_name,
                "description": None,
                "code_anchor": slot_code[:200],
            }
            for slot_name, slot_code in genes.items()
        ]
        self.db.insert_genes(solution.id, gene_records)
        logger.info(
            "genes 已写入: solution_id=%s, slots=%s",
            solution.id,
            sorted(genes.keys()),
        )
```

- [ ] **Step 4: 运行已有 DraftPES 测试确认不破坏**

```bash
cd /home/iomgaa/Projects/Herald2 && python -m pytest tests/unit/test_draft_pes.py -v
```

预期：所有已有测试 PASS

- [ ] **Step 5: 提交**

```bash
cd /home/iomgaa/Projects/Herald2 && git add core/pes/draft.py tests/unit/test_draft_pes_write_genes.py && git commit -m "feat: DraftPES Summarize 阶段解析 GENE 标记写入 genes 表"
```

---

### Task 3: 变异候选排序函数 — `rank_mutation_candidates()`

**Files:**
- Modify: `core/pes/gene_utils.py`
- Modify: `tests/unit/test_gene_utils.py`

- [ ] **Step 1: 写失败测试 — 排序逻辑**

在 `tests/unit/test_gene_utils.py` 末尾追加：

```python
from core.pes.gene_utils import rank_mutation_candidates


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
    # FEATURE_ENG 被 summarize 提到，应排第一
    assert ranked[0]["slot"] == "FEATURE_ENG"
    assert ranked[0]["reason"] == "summarize_mentioned"


def test_rank_prioritizes_never_mutated():
    """从未变异过的 slot 应优先于已变异过的。"""
    parent_genes = ["DATA", "FEATURE_ENG", "MODEL"]
    summarize_insight = "无特别���议。"
    mutate_history = [
        {"slot": "MODEL", "fitness_delta": 0.05},
    ]

    ranked = rank_mutation_candidates(
        parent_genes=parent_genes,
        summarize_insight=summarize_insight,
        mutate_history=mutate_history,
    )
    slot_names = [r["slot"] for r in ranked]
    # DATA 和 FEATURE_ENG 从未变异，应排在 MODEL 前面
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/iomgaa/Projects/Herald2 && python -m pytest tests/unit/test_gene_utils.py::test_rank_prioritizes_summarize_mentioned_slots -v
```

预期：FAIL，`ImportError: cannot import name 'rank_mutation_candidates'`

- [ ] **Step 3: 实现 `rank_mutation_candidates()`**

在 `core/pes/gene_utils.py` 末尾追加：

```python
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
        # 规则 1：summarize 提及
        if slot.upper() in insight_upper:
            candidates.append({
                "slot": slot,
                "reason": "summarize_mentioned",
                "priority": 1,
            })
        # 规则 2：从未变异
        elif slot not in mutated_slots:
            candidates.append({
                "slot": slot,
                "reason": "never_mutated",
                "priority": 2,
            })
        # 规则 3：变异后 fitness 下降
        elif fitness_delta_map.get(slot, 0.0) < 0:
            candidates.append({
                "slot": slot,
                "reason": "fitness_declined",
                "priority": 3,
            })
        # 规则 4：其余
        else:
            candidates.append({
                "slot": slot,
                "reason": "default",
                "priority": 4,
            })

    candidates.sort(key=lambda c: c["priority"])
    return candidates
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /home/iomgaa/Projects/Herald2 && python -m pytest tests/unit/test_gene_utils.py -v
```

预期：全部 PASS（含 Task 1 的 4 个 + 本 Task 的 3 个）

- [ ] **Step 5: 提交**

```bash
cd /home/iomgaa/Projects/Herald2 && git add core/pes/gene_utils.py tests/unit/test_gene_utils.py && git commit -m "feat: 新增 rank_mutation_candidates 变异候选排序函数"
```

---

### Task 4: MutatePES YAML 配置 + prompt_spec 注册

**Files:**
- Create: `config/pes/mutate.yaml`
- Modify: `config/prompts/prompt_spec.yaml`

- [ ] **Step 1: 创建 `config/pes/mutate.yaml`**

```yaml
name: mutate
operation: mutate
solution_file_name: solution.py
submission_file_name: submission.csv

phases:
  plan:
    template_name: null
    tool_names: []
    max_retries: 1
    allowed_tools: ["Bash", "Read", "Glob", "Grep", "Skill"]
    max_turns: 3

  execute:
    template_name: null
    tool_names: ["db_cli"]
    max_retries: 1
    allowed_tools: ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "Skill"]
    max_turns: 12

  summarize:
    template_name: null
    tool_names: []
    max_retries: 1
    allowed_tools: ["Skill"]
    max_turns: 2
```

- [ ] **Step 2: 修改 `config/prompts/prompt_spec.yaml` — 新增 mutate 三阶段**

在文件末��追加：

```yaml

  # Mutate 操作 - Plan 阶段
  mutate_plan:
    required_context: ["solution", "parent_solution"]
    static_fragments: ["system_context"]
    artifacts: []

  # Mutate 操作 - Execute 阶段
  mutate_execute:
    required_context: ["solution", "parent_solution"]
    static_fragments: ["system_context"]
    artifacts: []

  # Mutate 操作 - Summarize 阶段
  mutate_summarize:
    required_context: ["solution", "execution_log", "parent_solution"]
    static_fragments: ["system_context"]
    artifacts: []
```

- [ ] **Step 3: 验证 YAML 语法正确**

```bash
cd /home/iomgaa/Projects/Herald2 && python -c "
import yaml
from pathlib import Path
for f in ['config/pes/mutate.yaml', 'config/prompts/prompt_spec.yaml']:
    data = yaml.safe_load(Path(f).read_text())
    print(f'{f}: OK, keys={list(data.keys())}')
"
```

预期：两个文件均输出 OK

- [ ] **Step 4: 验证 PESConfig 可正确加载**

```bash
cd /home/iomgaa/Projects/Herald2 && python -c "
from core.pes.config import load_pes_config
cfg = load_pes_config('config/pes/mutate.yaml')
print(f'name={cfg.name}, operation={cfg.operation}')
for phase_name, phase_cfg in cfg.phases.items():
    print(f'  {phase_name}: max_turns={phase_cfg.max_turns}, allowed_tools={phase_cfg.allowed_tools}')
"
```

预��：输出 mutate 配置的三个 phase

- [ ] **Step 5: 提交**

```bash
cd /home/iomgaa/Projects/Herald2 && git add config/pes/mutate.yaml config/prompts/prompt_spec.yaml && git commit -m "feat: 新增 MutatePES YAML 配置与 prompt_spec ���册"
```

---

### Task 5: mutate prompt 模板 — plan 阶���

**Files:**
- Create: `config/prompts/templates/mutate_plan.j2`

- [ ] **Step 1: 创建模板文件**

```jinja2
{{ static_fragments_text | default('', true) }}

{% if time_budget or step_budget %}
# 资源预算

- 剩余时间: {{ time_budget | default("未知") }}
- 剩余步骤: {{ step_budget | default("未知") }}
{% endif %}

# 当前阶段

你当前处于 `mutate_plan` phase，需要选择一个 Gene Slot 进行变异，并为该 Slot 生成新的描述态方案。

{% if agent %}
# 当前执行 Agent

- `name`: `{{ agent.name }}`
- `display_name`: `{{ agent.display_name }}`

{% if agent.prompt_text %}
## Agent 执行偏好

{{ agent.prompt_text }}
{% endif %}
{% endif %}

# 角色边界

- `agent` 决定执行风格与问题拆解方式。
- `task_spec`、`schema`、`parent_solution` 决定任务目标、slot 边界与父方案状态。
- 若二者冲突，以 `task_spec` / `schema` 为准。

{% if task_spec %}
# 任务规格

- `task_type`: `{{ task_spec.task_type }}`
- `competition_name`: `{{ task_spec.competition_name }}`
- `objective`: `{{ task_spec.objective }}`
- `metric_name`: `{{ task_spec.metric_name }}`
- `metric_direction`: `{{ task_spec.metric_direction }}`
{% endif %}

{% if parent_solution %}
# 父方案信息

- `solution_id`: `{{ parent_solution.id }}`
- `generation`: `{{ parent_solution.generation }}`
- `fitness`: `{{ parent_solution.fitness }}`
- `status`: `{{ parent_solution.status }}`
{% if parent_solution.metrics %}
- `metric_name`: `{{ parent_solution.metrics.metric_name }}`
- `metric_value`: `{{ parent_solution.metrics.metric_value }}`
- `metric_direction`: `{{ parent_solution.metrics.metric_direction }}`
{% endif %}

{% if parent_solution.plan_summary %}
## 父方案 Plan 摘要

{{ parent_solution.plan_summary }}
{% endif %}

{% if parent_solution.summarize_insight %}
## 父��案 Summarize 总结

{{ parent_solution.summarize_insight }}
{% endif %}
{% endif %}

{% if mutation_candidates %}
# Harness 变异候选建议

以下是 Harness 根据规则排序的变异候选 Slot（优先级从高到低）。你可以接受建议，也可以给出理由选择其他 Slot。

{% for candidate in mutation_candidates %}
- **{{ candidate.slot }}** — 理由: {{ candidate.reason }}{% if candidate.priority %} (优先级: {{ candidate.priority }}){% endif %}

{% endfor %}
{% endif %}

{% if parent_genes %}
# 父方案 Gene 代码片段

以下是父方案各 Slot 的当前代码（来自 code_snapshots）：

{% for slot_name, slot_code in parent_genes.items() %}
## Slot `{{ slot_name }}`

```python
{{ slot_code }}
```

{% endfor %}
{% endif %}

{% if allowed_tools is defined %}
# 当前 phase 可见工具

{% if allowed_tools %}
- {{ allowed_tools | join(" / ") }}
{% else %}
- 当前 phase 无额外工具。
{% endif %}
{% endif %}

# 任务要求

1. **选择变异 Slot**：参考 Harness 候选建议和父方案 Summarize 总结，选择一个最值得改进的 Gene Slot
2. **生成新描述态方案**：为选中的 Slot 生成新的描述态方案，说明变异方向和预期效果
3. **保持其余 Slot 不变**：明确声明其余 Slot 将从父方案原样继承

## 变异约束

- 每次 mutate 只允许变异一个 Slot
- 变异方向应与父方案 Summarize 中的建议方向一致（如有）
- 规划前请先使用 `draft-history-review` skill 查询前序经验，确保变异方向与已有尝试不重复

# 输出格式

请严格按以下结构输出：

## 变异决策
- 选中 Slot: （Slot 名称）
- 选择理由: （为什么选这个 Slot）
- 变异方向: （打算怎么改）

## 新 Slot 方案
- 目标
- 核心思路
- 预期效果
- 与父方案的差异点

## 继承 Slot
- 列出所有不变的 Slot 及其继承理由
```

- [ ] **Step 2: 验证模板可渲染**

```bash
cd /home/iomgaa/Projects/Herald2 && python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('config/prompts/templates'), trim_blocks=True, lstrip_blocks=True)
tpl = env.get_template('mutate_plan.j2')
result = tpl.render(
    solution={'id': 'test', 'generation': 1},
    parent_solution={'id': 'parent', 'generation': 0, 'fitness': 0.85, 'status': 'completed',
                     'metrics': {'metric_name': 'rmse', 'metric_value': 0.85, 'metric_direction': 'min'},
                     'plan_summary': '使用 LightGBM', 'summarize_insight': '# 建议方向\n尝试改进 FEATURE_ENG'},
    mutation_candidates=[{'slot': 'FEATURE_ENG', 'reason': 'summarize_mentioned', 'priority': 1}],
    parent_genes={'DATA': 'def load_data(c): pass', 'FEATURE_ENG': 'def build_features(d,c): pass'},
    task_spec={'task_type': 'tabular', 'competition_name': 'test', 'objective': 'predict', 'metric_name': 'rmse', 'metric_direction': 'min'},
)
assert 'mutate_plan' in result
assert 'FEATURE_ENG' in result
print('mutate_plan.j2: OK')
"
```

预期：输出 OK

- [ ] **Step 3: 提交**

```bash
cd /home/iomgaa/Projects/Herald2 && git add config/prompts/templates/mutate_plan.j2 && git commit -m "feat: 新增 mutate_plan.j2 prompt 模板"
```

---

### Task 6: mutate prompt 模板 — execute 阶段

**Files:**
- Create: `config/prompts/templates/mutate_execute.j2`

- [ ] **Step 1: 创建模板文件**

```jinja2
{{ static_fragments_text | default('', true) }}

# 当前阶段

你当前处于 `mutate_execute` phase，需要在父方案代码基础上修改一个指定 Slot 的实现。

{% if agent %}
# 当前执行 Agent

- `name`: `{{ agent.name }}`
- `display_name`: `{{ agent.display_name }}`

{% if agent.prompt_text %}
## Agent 执行���好

{{ agent.prompt_text }}
{% endif %}
{% endif %}

# 角色边界

- `agent` 负责执行风格与调试策略。
- `task_spec`、`solution`、`workspace` 才是本轮实现的硬约束。
- 不要把 Agent 提示重写成新的任务目标；若与当前方案冲突，以当前任务上下文为准。

{% if task_spec %}
# 任务规格

- `task_type`: `{{ task_spec.task_type }}`
- `competition_name`: `{{ task_spec.competition_name }}`
- `objective`: `{{ task_spec.objective }}`
- `metric_name`: `{{ task_spec.metric_name }}`
- `metric_direction`: `{{ task_spec.metric_direction }}`
{% endif %}

{% if data_profile %}
# 数据概况

{{ data_profile }}
{% endif %}

{% if workspace %}
# 工作空间

- `workspace_root`: `{{ workspace.workspace_root }}`
- `data_dir`: `{{ workspace.data_dir }}`
- `working_dir`: `{{ workspace.working_dir }}`
- `logs_dir`: `{{ workspace.logs_dir }}`
- `db_path`: `{{ workspace.db_path }}`
- `run_log_path`: `{{ workspace.run_log_path }}`
{% endif %}

{% if target_slot %}
# 变异目标

- **目标 Slot**: `{{ target_slot }}`
- 你只需修改 `# === GENE:{{ target_slot }}_START ===` 和 `# === GENE:{{ target_slot }}_END ===` 之间的代码
- **其余所有代码必须保持与 `solution_parent.py` 完全一致**
{% endif %}

{% if solution.plan_summary %}
# 当前方案的 Plan 摘要（含变异决策）

{{ solution.plan_summary }}
{% endif %}

{% if recent_error %}
# 最���错误

{{ recent_error }}
{% endif %}

{% if allowed_tools is defined %}
# 当前 phase 可见工具

{% if allowed_tools %}
- {{ allowed_tools | join(" / ") }}
{% else %}
- 当前 phase 无额��工具。
{% endif %}
{% endif %}

# 可用工具

- 基础库: numpy, pandas, scipy
- 机器学习: scikit-learn, xgboost, lightgbm
- 深度学习: torch, torchvision, timm
- 优化: optuna
- 推荐优先使用 PyTorch 进行深度学习任务

# 执行步骤

你必须按以下编号顺序完成所有步骤，**不得跳过任何步骤**。

## Step 1: 阅读父方案代码

- 读取 `{{ workspace.working_dir if workspace else "." }}/solution_parent.py`
- 定位目标 Slot `{{ target_slot }}` 的 `GENE:{{ target_slot }}_START` / `GENE:{{ target_slot }}_END` 标记区域
- 理解该 Slot 与其余 Slot 的数据依赖��系

## Step 2: 编写 solution.py

- 复制 `solution_parent.py` 为 `solution.py`
- **只修改** `# === GENE:{{ target_slot }}_START ===` 和 `# === GENE:{{ target_slot }}_END ===` 之间的代码
- **严禁修改** 其余 GENE 区域和 FIXED 区域
- 确保修改后的代码与上下游 Slot 接口兼容
- **禁止修改 `solution_parent.py`**

## Step 3: 执行 solution.py（禁止跳过）

```bash
set -o pipefail; python -u solution.py 2>&1 | tee -a {{ workspace.run_log_path if workspace else "run.log" }}
```

等待运行完成，记录输出中的评估指标值。

## Step 4: 检查与修正

- 若 Step 3 运行失败，**必须修复 solution.py 中目标 Slot 区域的代码后重新执行 Step 3**
- 若运行成功但指标值异常，修复后重新执行
- 确认 submission.csv 存在且行数正确
- 确认验证集指标值合理

## Step 5: 变异纯度检查

- 使用 `mutate-diff-check` skill 对比 `solution_parent.py` 与 `solution.py` 的差异
- 确认只有目标 Slot 区域有变化

# 输出���式

请严格按以下结构输出：

## 执行报告
（1-3 段：实际修改内容、修改理由、与父方案的差异）

## 变异 Slot
- 目标 Slot: {{ target_slot }}
- 修改摘要: （简述改了什么）

## 验证结果（必须来自 Step 3 的实际运行输出，禁止估算）
- 指标名: {{ task_spec.metric_name if task_spec else "unknown" }}
- 指标值: （填写 Step 3 实际输出的数值）
- 提交路径: {{ workspace.working_dir if workspace else "." }}/submission.csv
```

- [ ] **Step 2: 验证模板可渲染**

```bash
cd /home/iomgaa/Projects/Herald2 && python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('config/prompts/templates'), trim_blocks=True, lstrip_blocks=True)
tpl = env.get_template('mutate_execute.j2')
result = tpl.render(
    solution={'plan_summary': '变异 FEATURE_ENG', 'genes': {}},
    parent_solution={'id': 'parent'},
    target_slot='FEATURE_ENG',
    task_spec={'task_type': 'tabular', 'competition_name': 'test', 'objective': 'predict', 'metric_name': 'rmse', 'metric_direction': 'min'},
    workspace={'workspace_root': '/tmp/ws', 'data_dir': '/tmp/ws/data', 'working_dir': '/tmp/ws/working', 'logs_dir': '/tmp/ws/logs', 'db_path': '/tmp/ws/db/herald.db', 'run_log_path': '/tmp/ws/working/run.log'},
)
assert 'FEATURE_ENG' in result
assert 'solution_parent.py' in result
assert 'mutate-diff-check' in result
print('mutate_execute.j2: OK')
"
```

预期：输出 OK

- [ ] **Step 3: 提交**

```bash
cd /home/iomgaa/Projects/Herald2 && git add config/prompts/templates/mutate_execute.j2 && git commit -m "feat: 新增 mutate_execute.j2 prompt 模板"
```

---

### Task 7: mutate prompt 模板 — summarize 阶段

**Files:**
- Create: `config/prompts/templates/mutate_summarize.j2`

- [ ] **Step 1: 创建���板文件**

```jinja2
{{ static_fragments_text | default('', true) }}

{% set metric_name = solution.metrics.metric_name if solution and solution.metrics and solution.metrics.metric_name is not none else (task_spec.metric_name if task_spec else "unknown") %}
{% set metric_value = solution.metrics.metric_value if solution and solution.metrics and solution.metrics.metric_value is not none else "unknown" %}
{% set metric_direction = solution.metrics.metric_direction if solution and solution.metrics and solution.metrics.metric_direction is not none else (task_spec.metric_direction if task_spec else "unknown") %}

# 当前阶段

你当前处于 `mutate_summarize` phase，需要总结本次变异实验并沉淀洞察。

{% if agent %}
# 当前���行 Agent

- `name`: `{{ agent.name }}`
- `display_name`: `{{ agent.display_name }}`
{% endif %}

# 角色边界

- `agent` 只影响表达与复盘风格。
- `solution`、`task_spec`、`execution_log`、指标结果才是总结结论的依据。
- 不要虚构未观察到的实验事实；推断必须明确标注为推断。

{% if task_spec %}
# 任务规格

- `task_type`: `{{ task_spec.task_type }}`
- `competition_name`: `{{ task_spec.competition_name }}`
- `objective`: `{{ task_spec.objective }}`
- `metric_name`: `{{ task_spec.metric_name }}`
- `metric_direction`: `{{ task_spec.metric_direction }}`
{% endif %}

{% if target_slot %}
# ���异信息

- 变异 Slot: `{{ target_slot }}`
{% endif %}

# 方案摘要

## Plan 阶段

{% if solution.plan_summary %}
{{ solution.plan_summary }}
{% else %}
暂无 plan 摘要。
{% endif %}

## Execute 阶段

{% if solution.execute_summary %}
{{ solution.execute_summary }}
{% else %}
暂无 execute 摘要。
{% endif %}

# 评估结果

- 指标：`{{ metric_name }}`
- 本轮指标值：{{ metric_value }}
- 指标方向：`{{ metric_direction }}`
- Fitness：{{ solution.fitness if solution and solution.fitness is not none else "unknown" }}
- 状态：{{ solution.status if solution and solution.status else "unknown" }}

{% if parent_solution and parent_solution.metrics and parent_solution.metrics.metric_value is not none %}
# 指标对比

- 本轮: {{ metric_value }}
- 父方案: {{ parent_solution.metrics.metric_value }}
- 变化: {{ "提升" if (metric_direction == "max" and metric_value > parent_solution.metrics.metric_value) or (metric_direction == "min" and metric_value < parent_solution.metrics.metric_value) else "下降或持平" }}
{% endif %}

{% if parent_solution %}
# 父方案参考

- `solution_id`: `{{ parent_solution.id }}`
- `generation`: `{{ parent_solution.generation }}`
{% if parent_solution.metrics %}
- `parent_metric_value`: {{ parent_solution.metrics.metric_value if parent_solution.metrics.metric_value is not none else "unknown" }}
{% endif %}
{% endif %}

{% if execution_log %}
# 执行日志

{{ execution_log }}
{% endif %}

{% if allowed_tools is defined %}
# 当前 phase 可见工具

{% if allowed_tools %}
- {{ allowed_tools | join(" / ") }}
{% else %}
- 当前 phase 无额外工具。
{% endif %}
{% endif %}

# 总结要求

请使用 `draft-summarize-format` skill 获取输出格式规范，严格按照五小节段落式结构输出实验总结。

在标准五小节基础上，本次 mutate summarize 需要额外强调：
- **变异 Slot 标识**：在"# 摘要"中明确指出"本次变异了 {{ target_slot }}"
- **指标变化方向**：与父方案的 fitness 对比结果
- **变异有效性判断**：本次变异是正向改进还是负向退化
- **下一步建议**：基于变异效果，建议下一次应该变异哪个 Slot、为什么
```

- [ ] **Step 2: 验证模板可渲染**

```bash
cd /home/iomgaa/Projects/Herald2 && python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('config/prompts/templates'), trim_blocks=True, lstrip_blocks=True)
tpl = env.get_template('mutate_summarize.j2')
result = tpl.render(
    solution={'plan_summary': '变异 FEATURE_ENG', 'execute_summary': '已执行', 'fitness': 0.88,
              'status': 'completed', 'metrics': {'metric_name': 'rmse', 'metric_value': 0.88, 'metric_direction': 'min'}},
    parent_solution={'id': 'parent', 'generation': 0, 'metrics': {'metric_name': 'rmse', 'metric_value': 0.85, 'metric_direction': 'min'}},
    target_slot='FEATURE_ENG',
    task_spec={'task_type': 'tabular', 'competition_name': 'test', 'objective': 'predict', 'metric_name': 'rmse', 'metric_direction': 'min'},
)
assert 'FEATURE_ENG' in result
assert 'mutate_summarize' in result
print('mutate_summarize.j2: OK')
"
```

预期：输出 OK

- [ ] **Step 3: 提交**

```bash
cd /home/iomgaa/Projects/Herald2 && git add config/prompts/templates/mutate_summarize.j2 && git commit -m "feat: 新增 mutate_summarize.j2 prompt 模板"
```

---

### Task 8: mutate-diff-check Skill

**Files:**
- Create: `core/prompts/skills/mutate-diff-check/SKILL.md`

- [ ] **Step 1: 创建 Skill 文件**

```markdown
---
name: mutate-diff-check
description: >-
  This skill should be used when the Mutate Agent needs to
  "verify mutation purity", "check code diff",
  "compare solution_parent.py with solution.py",
  "ensure only the target slot was modified", or
  "validate that non-target genes were not changed".
  Uses diff to verify that only the intended GENE region was modified.
---

# 变异纯度检查

在 `MutatePES.execute` 阶段完成代码修改后使用。

## 何时使用

- 完成 solution.py 编写后、提交最终输出前
- 需要确认只有目标 Slot 的 GENE 区域被修改

## 操作步骤

### Step 1: 执行 diff 对比

```bash
diff solution_parent.py solution.py || true
```

### Step 2: 分析 diff 输出

检查 diff 输出中的变更行：

1. **定位变更区域**：变更应全部在 `# === GENE:TARGET_SLOT_START ===` 和 `# === GENE:TARGET_SLOT_END ===` 标记之间
2. **检查非目标区域**：标记之外的代码不应有任何变化（import 调整除外）

### Step 3: 判断结果

- **纯净变异**：所有变更都在目标 Slot 标记区域内 → 直接继续
- **轻微溢出**：少量 import 语句变更（如新增模型依赖的 import） → 可接受，在执行报告中说明
- **严重溢出**：非目标 Slot 的 GENE 区域被修改 → 必须回退修改，只保留目标 Slot 的变更

## 注意事项

- `solution_parent.py` 是只读参考文件，**禁止修改**
- diff 输出为空表示没有任何变更，这是错误情况——说明变异未生效
- 如果 diff 发现问题，优先通过 Edit 工具精确修复，避免重写整个文件
```

- [ ] **Step 2: 验证文件存在且 frontmatter ��确**

```bash
cd /home/iomgaa/Projects/Herald2 && python -c "
from pathlib import Path
skill_path = Path('core/prompts/skills/mutate-diff-check/SKILL.md')
assert skill_path.exists(), f'{skill_path} 不存在'
content = skill_path.read_text()
assert '---' in content
assert 'mutate-diff-check' in content
print('mutate-diff-check skill: OK')
"
```

- [ ] **Step 3: 提交**

```bash
cd /home/iomgaa/Projects/Herald2 && git add core/prompts/skills/mutate-diff-check/SKILL.md && git commit -m "feat: 新增 mutate-diff-check skill 变��纯度检查"
```

---

### Task 9: MutatePES 核心实��

**Files:**
- Create: `core/pes/mutate.py`
- Test: `tests/unit/test_mutate_pes.py`

- [ ] **Step 1: 写失败测试 — MutatePES 基础行为**

```python
# tests/unit/test_mutate_pes.py
"""MutatePES 单元测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.pes.config import load_pes_config
from core.pes.mutate import MutatePES
from core.pes.types import PESSolution


@pytest.fixture
def mutate_config():
    """加载 mutate YAML 配置。"""
    config_path = Path(__file__).resolve().parents[2] / "config" / "pes" / "mutate.yaml"
    return load_pes_config(config_path)


@pytest.fixture
def mock_db():
    """模拟数据库。"""
    db = MagicMock()
    db.get_full_code.return_value = "# === GENE:DATA_START ===\ndef load_data(c): pass\n# === GENE:DATA_END ===\n"
    db.get_best_fitness.return_value = 0.85
    db.insert_solution = MagicMock()
    db.update_solution_status = MagicMock()
    db.update_solution_artifacts = MagicMock()
    db.insert_code_snapshot = MagicMock()
    db.insert_genes = MagicMock()
    db.log_llm_call = MagicMock()
    db.log_exec = MagicMock()
    db.log_contract_check = MagicMock()
    db.upsert_l2_insight = MagicMock()
    db.get_slot_history.return_value = []
    db.genes = MagicMock()
    db.genes.get_by_solution.return_value = [
        {"slot": "DATA", "description": None, "code_anchor": "def load_data(c): pass"},
    ]
    return db


@pytest.fixture
def mock_workspace(tmp_path):
    """模拟工作空间。"""
    ws = MagicMock()
    working_dir = tmp_path / "working"
    working_dir.mkdir()
    ws.working_dir = working_dir
    ws.data_dir = tmp_path / "data"
    ws.logs_dir = tmp_path / "logs"
    ws.db_path = tmp_path / "database" / "herald.db"
    ws.run_log_path = working_dir / "run.log"
    ws.summary.return_value = {
        "workspace_root": str(tmp_path),
        "data_dir": str(ws.data_dir),
        "working_dir": str(working_dir),
        "logs_dir": str(ws.logs_dir),
        "db_path": str(ws.db_path),
        "run_log_path": str(ws.run_log_path),
    }
    ws.get_working_file_path = lambda name: working_dir / name
    ws.read_working_solution = lambda name="solution.py": (working_dir / name).read_text()
    ws.read_working_submission = lambda name="submission.csv": (working_dir / name).read_text()
    ws.read_runtime_artifact = lambda name: None
    ws.save_version = MagicMock(return_value=tmp_path / "history" / "gen1_test")
    ws.promote_best = MagicMock()
    ws.get_working_submission_path = lambda name: working_dir / name
    return ws


def test_mutate_pes_instantiates(mutate_config, mock_db, mock_workspace):
    """MutatePES 应能正常实例化。"""
    pes = MutatePES(
        config=mutate_config,
        llm=MagicMock(),
        db=mock_db,
        workspace=mock_workspace,
    )
    assert pes.config.operation == "mutate"


def test_mutate_pes_create_solution_has_parent(mutate_config, mock_db, mock_workspace):
    """MutatePES 创建的 solution 应有 parent_ids。"""
    pes = MutatePES(
        config=mutate_config,
        llm=MagicMock(),
        db=mock_db,
        workspace=mock_workspace,
    )
    parent = PESSolution(
        id="parent-id",
        operation="draft",
        generation=0,
        status="completed",
        created_at="2026-04-01T00:00:00Z",
        parent_ids=[],
        lineage="parent-id",
        run_id="test-run",
        fitness=0.85,
    )
    solution = pes.create_solution(generation=1, parent_solution=parent)
    assert solution.parent_ids == ["parent-id"]
    assert solution.operation == "mutate"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /home/iomgaa/Projects/Herald2 && python -m pytest tests/unit/test_mutate_pes.py -v
```

预期：FAIL，`ModuleNotFoundError: No module named 'core.pes.mutate'`

- [ ] **Step 3: 实�� MutatePES**

```python
# core/pes/mutate.py
"""MutatePES 单谱系变异实现。"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from core.pes.draft import DraftPES
from core.pes.gene_utils import parse_genes_from_code, rank_mutation_candidates
from core.pes.types import PESSolution
from core.utils.utils import utc_now_iso

logger = logging.getLogger(__name__)


class MutatePES(DraftPES):
    """Gene 级变异 PES，继承 DraftPES 的 execute 产物契约。

    新增能力：
    - plan 阶段注入父代码、mutation_candidates、parent_genes
    - execute 阶段前将父代码落盘为 solution_parent.py
    - summarize 阶段记录 target_slot 和 fitness 变化
    """

    def build_prompt_context(
        self,
        phase: str,
        solution: PESSolution,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        """扩展 prompt 上下文，注入变异专用信息。"""

        context = super().build_prompt_context(phase, solution, parent_solution)

        if phase == "plan" and parent_solution is not None:
            context.update(
                self._build_mutation_plan_context(parent_solution)
            )

        if phase in ("execute", "summarize"):
            context["target_slot"] = solution.target_slot

        return context

    def _build_mutation_plan_context(
        self,
        parent_solution: PESSolution,
    ) -> dict[str, Any]:
        """构造 plan 阶段的变异上下文。"""

        extra: dict[str, Any] = {}

        # 从 code_snapshots 获取父代码并解析 genes
        parent_code = self._get_parent_code(parent_solution.id)
        if parent_code is not None:
            parent_genes = parse_genes_from_code(parent_code)
            extra["parent_genes"] = parent_genes

            # 获取变异历史
            mutate_history = self._get_mutate_history()

            # 排序候选
            candidates = rank_mutation_candidates(
                parent_genes=list(parent_genes.keys()),
                summarize_insight=parent_solution.summarize_insight or "",
                mutate_history=mutate_history,
            )
            extra["mutation_candidates"] = candidates

        return extra

    def _get_parent_code(self, parent_id: str) -> str | None:
        """从 DB 获取父方案的完整代码。"""

        if self.db is None or not hasattr(self.db, "get_full_code"):
            return None
        return self.db.get_full_code(parent_id)

    def _get_mutate_history(self) -> list[dict[str, Any]]:
        """获取本 run 内的 mutate 历史记录。"""

        if self.db is None or not hasattr(self.db, "list_solutions_by_run_and_operation"):
            return []

        run_id = self.runtime_context.get("run_id")
        if run_id is None:
            return []

        solutions = self.db.list_solutions_by_run_and_operation(
            run_id=run_id,
            operation="mutate",
            status="completed",
        )

        history: list[dict[str, Any]] = []
        for sol in solutions:
            mutated_slot = sol.get("mutated_slot")
            if mutated_slot is None:
                continue
            # fitness_delta 需要查父方案，暂简化为 0
            history.append({
                "slot": mutated_slot,
                "fitness_delta": 0.0,
            })
        return history

    async def handle_phase_response(
        self,
        phase: str,
        solution: PESSolution,
        response: object,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        """消费 phase 响应，扩展 plan 阶段的 target_slot 解析。"""

        response_text = self._extract_response_text(response)

        if phase == "plan":
            solution.plan_summary = response_text
            target_slot = self._parse_target_slot(response_text)
            solution.target_slot = target_slot
            if parent_solution is not None:
                self._place_parent_code(parent_solution.id)
            return {"phase": phase, "response_text": response_text, "target_slot": target_slot}

        if phase == "execute":
            return self._handle_execute_response(
                solution=solution,
                response=response,
                response_text=response_text,
            )

        if phase == "summarize":
            solution.summarize_insight = response_text
            solution.status = "completed"
            solution.finished_at = utc_now_iso()
            self._archive_completed_solution(solution)
            self._write_genes(solution)
            self._write_l2_knowledge(solution)
            self._emit_task_complete_event(solution=solution, status="completed")
            return {"phase": phase, "response_text": response_text}

        raise ValueError(f"不支持的 MutatePES phase: {phase}")

    def _parse_target_slot(self, plan_text: str) -> str | None:
        """从 plan 输出中解析选中的变异 Slot。

        查找 "选中 Slot:" 后面的内容。
        """

        import re

        match = re.search(
            r"选中\s*Slot\s*[:：]\s*[`]?(\w+)[`]?",
            plan_text,
            re.IGNORECASE,
        )
        if match is not None:
            return match.group(1).upper()

        # 降级：查找 GENE:XXX 格���
        match = re.search(r"GENE[:\s_]*(\w+)", plan_text, re.IGNORECASE)
        if match is not None:
            slot = match.group(1).upper()
            # 过滤掉 START/END
            if slot not in ("START", "END"):
                return slot

        logger.warning("未能从 plan 输出中解析 target_slot")
        return None

    def _place_parent_code(self, parent_id: str) -> None:
        """将父代码落盘到 workspace/working/solution_parent.py。"""

        parent_code = self._get_parent_code(parent_id)
        if parent_code is None:
            logger.warning("无法获取父代码，跳过 solution_parent.py 落盘")
            return

        if self.workspace is None:
            return

        working_dir = getattr(self.workspace, "working_dir", None)
        if working_dir is None:
            return

        parent_path = Path(working_dir) / "solution_parent.py"
        parent_path.write_text(parent_code, encoding="utf-8")
        logger.info("父代码已落盘: %s", parent_path)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /home/iomgaa/Projects/Herald2 && python -m pytest tests/unit/test_mutate_pes.py -v
```

预期：2 tests PASS

- [ ] **Step 5: 运行全量单元测试确认不破坏**

```bash
cd /home/iomgaa/Projects/Herald2 && python -m pytest tests/unit/ -v --timeout=30
```

预期：全部 PASS

- [ ] **Step 6: 提交**

```bash
cd /home/iomgaa/Projects/Herald2 && git add core/pes/mutate.py tests/unit/test_mutate_pes.py && git commit -m "feat: 实现 MutatePES 核心类，继承 DraftPES 产物契约"
```

---

### Task 10: Scheduler 支持 mutate 阶段 + parent 选择

**Files:**
- Modify: `core/scheduler/scheduler.py`
- Modify: `core/main.py`

- [ ] **Step 1: 修改 Scheduler — 新增 `select_best_parent()` 方法**

在 `core/scheduler/scheduler.py` 的 `__init__` 中新增：

```python
        self._db: object | None = None
```

新增方法（放在 `_merge_stage_outputs` 之后）：

```python
    def set_db(self, db: object) -> None:
        """注入数据库引用，用于 parent 选择。"""
        self._db = db

    def _select_best_parent_id(self) -> str | None:
        """选择 fitness 最高的 completed solution 作为 parent。"""

        if self._db is None or not hasattr(self._db, "solutions"):
            return None

        run_id = self.context.get("run_id")
        best_fitness = getattr(self._db, "get_best_fitness", None)
        if not callable(best_fitness):
            return None

        best = best_fitness(run_id=run_id)
        if best is None:
            return None

        # 查找 fitness == best 的 solution
        solutions_repo = getattr(self._db, "solutions", None)
        if solutions_repo is None or not hasattr(solutions_repo, "list_active"):
            return None

        active_solutions = solutions_repo.list_active()
        for sol in active_solutions:
            if sol.get("fitness") == best and sol.get("run_id") == run_id:
                return sol["id"]
        return None
```

在 `_dispatch_task` 方法中，当 stage 是 mutate 时注入 `parent_solution_id`：

```python
    def _dispatch_task(self, index: int, task_name: str) -> None:
        """发出一个任务分发事件。"""
        self._current_task_event = asyncio.Event()

        context = {
            "competition_dir": self.competition_dir,
            **self.context,
            **self.shared_context,
        }

        # mutate 阶段需要注入 parent
        if task_name == "mutate":
            parent_id = self._select_best_parent_id()
            if parent_id is not None:
                context["parent_solution_id"] = parent_id
                logger.info("mutate 阶段选择 parent: %s", parent_id)
            else:
                logger.warning("mutate 阶段未找到可用 parent，将以无 parent 模式运行")

        EventBus.get().emit(
            TaskDispatchEvent(
                task_name=task_name,
                agent_name=self.agent_name,
                generation=index,
                context=context,
            )
        )

        logger.info(
            "任务已分发: task=%s, agent=%s, generation=%d, context_keys=%s",
            task_name,
            self.agent_name,
            index,
            sorted(context.keys()),
        )
```

- [ ] **Step 2: 修改 MutatePES — 从 execution_context 获取 parent_solution**

在 `core/pes/mutate.py` 的 `BasePES.run` 被调用前，需要在 `on_execute` 中设置 parent_solution。

在 `MutatePES` 中覆写 `on_execute` 方法（在 `build_prompt_context` 之前添加）：

```python
    def on_execute(self, event: object) -> None:
        """接收执行事件，额外解析 parent_solution。"""

        super().on_execute(event)

    async def _run_from_event(
        self,
        agent_profile: object,
        generation: int,
    ) -> None:
        """覆写事件驱动运行，注�� parent_solution。"""

        parent_solution = self._resolve_parent_solution()
        try:
            await self.run(
                agent_profile=agent_profile,
                generation=generation,
                parent_solution=parent_solution,
            )
        except Exception:
            logger.exception(
                "事件驱动 MutatePES ��行失败 [generation=%s]",
                generation,
            )

    def _resolve_parent_solution(self) -> PESSolution | None:
        """从 execution_context 中解析 parent_solution。"""

        parent_id = self._execution_context.get("parent_solution_id")
        if parent_id is None or self.db is None:
            return None

        row = self.db.get_solution(parent_id)
        if row is None:
            logger.warning("parent_solution_id=%s 对应的 solution 不存在", parent_id)
            return None

        import json
        parent_ids_raw = row.get("parent_ids", "[]")
        if isinstance(parent_ids_raw, str):
            try:
                parent_ids = json.loads(parent_ids_raw)
            except json.JSONDecodeError:
                parent_ids = []
        else:
            parent_ids = parent_ids_raw or []

        return PESSolution(
            id=row["id"],
            operation=row.get("operation", "draft"),
            generation=row.get("generation", 0),
            status=row.get("status", "completed"),
            created_at=row.get("created_at", ""),
            parent_ids=parent_ids,
            lineage=row.get("lineage"),
            run_id=row.get("run_id"),
            finished_at=row.get("finished_at"),
            fitness=row.get("fitness"),
            metrics={
                "metric_name": row.get("metric_name"),
                "metric_value": row.get("metric_value"),
                "metric_direction": row.get("metric_direction"),
            },
            plan_summary=row.get("plan_summary", ""),
            execute_summary=row.get("execute_summary", ""),
            summarize_insight=row.get("summarize_insight", ""),
        )
```

- [ ] **Step 3: 修改 `core/main.py` — 新增 bootstrap_mutate_pes + scheduler 配置**

在顶部导入新增：

```python
from core.pes.mutate import MutatePES
```

新增 bootstrap 函数（放在 `bootstrap_draft_pes` 之后）：

```python
def bootstrap_mutate_pes(
    config: HeraldConfig,
    workspace: Workspace,
    db: HeraldDB,
) -> MutatePES:
    """装配并注册 MutatePES 实例。"""

    pes_config_path = (
        Path(__file__).resolve().parents[1] / "config" / "pes" / "mutate.yaml"
    )
    pes_config = load_pes_config(pes_config_path)
    competition_root_dir = str(Path(config.run.competition_dir).expanduser().resolve())
    mutate_pes = MutatePES(
        config=pes_config,
        llm=_build_llm_client(config),
        db=db,
        workspace=workspace,
        runtime_context={
            "competition_dir": config.run.competition_dir,
            "competition_root_dir": competition_root_dir,
            "competition_id": Path(competition_root_dir).name,
            "public_data_dir": str(workspace.data_dir),
            "workspace_logs_dir": str(workspace.logs_dir),
        },
    )
    create_grading_hook = _load_create_grading_hook()
    mutate_pes.hooks.register(
        create_grading_hook(
            competition_root_dir=competition_root_dir,
            public_data_dir=str(workspace.data_dir),
            workspace_logs_dir=str(workspace.logs_dir),
        ),
        name=f"{mutate_pes.instance_id}_grading_hook",
    )
    logger.info("MutatePES 装配完成: instance_id=%s", mutate_pes.instance_id)
    return mutate_pes
```

在 `main()` 函数中，Phase 5 补充 MutatePES：

```python
    # Phase 5: 装配 FeatureExtractPES + DraftPES + MutatePES
    ...
    mutate_pes = bootstrap_mutate_pes(
        config=config,
        workspace=workspace,
        db=db,
    )
    ...
    mutate_pes.runtime_context["run_id"] = run_id
    logger.info(
        "PES 已注册到调度链路: feature_extract=%s, draft=%s, mutate=%s",
        feature_extract_pes.instance_id,
        draft_pes.instance_id,
        mutate_pes.instance_id,
    )
```

Scheduler 配置中新增 mutate stage 并注入 db：

```python
    scheduler = Scheduler(
        competition_dir=config.run.competition_dir,
        max_tasks=config.run.max_tasks,
        context={"run_id": run_id},
        task_stages=[
            ("feature_extract", 1),
            ("draft", config.run.max_tasks),
            ("mutate", config.run.max_tasks),
        ],
        stage_max_retries={"feature_extract": 2},
    )
    scheduler.set_db(db)
```

- [ ] **Step 4: 运行已有 Scheduler 测试确认不破���**

```bash
cd /home/iomgaa/Projects/Herald2 && python -m pytest tests/unit/test_scheduler_stages.py -v
```

预期：PASS

- [ ] **Step 5: 提交**

```bash
cd /home/iomgaa/Projects/Herald2 && git add core/scheduler/scheduler.py core/pes/mutate.py core/main.py && git commit -m "feat: Scheduler 支持 mutate 阶段 parent 选择，main.py 装配 MutatePES"
```

---

### Task 11: 集成测试 — MutatePES 完整流程

**Files:**
- Create: `tests/integration/test_mutate_pes_flow.py`

- [ ] **Step 1: 编写集成测试**

```python
# tests/integration/test_mutate_pes_flow.py
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
    # 先写入父方案
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
```

- [ ] **Step 2: 运行集成测试**

```bash
cd /home/iomgaa/Projects/Herald2 && python -m pytest tests/integration/test_mutate_pes_flow.py -v
```

预期：PASS

- [ ] **Step 3: 提交**

```bash
cd /home/iomgaa/Projects/Herald2 && git add tests/integration/test_mutate_pes_flow.py && git commit -m "test: MutatePES 集成测试——父代码落盘与 gene 解析"
```

---

### Task 12: 更新架构文档

**Files:**
- Modify: `docs/architecture.md`

- [ ] **Step 1: 更新 §5 当前代码真实架构**

在 §5.1 已实现主链路的 Stage 2 之后新增 Stage 3:

```text
          └── ✅ Stage 3: emit(TaskDispatchEvent(task_name="mutate", context=上游产出+parent_id))
                ▼
              TaskDispatcher → MutatePES.run()
                ├── plan:     消费 parent 的 genes + summarize + Harness 排序候选
                │             → LLM 选择 target_slot + 生成新描述态方案
                ├── execute:  落盘 solution_parent.py → 修改 target_slot 区域
                │             → 运行、metrics 提取、submission 校验、纯度检查
                └── summarize: 五小节格式 + L2 写入 + genes 写入
```

- [ ] **Step 2: 更新 §9.3 — 明确标记选择压力推迟**

将 §9.3 修改为：

```text
### 9.3 P1：单谱系进化（当前阶段）

**已完成：**
1. genes / code_snapshots 真正接入主链路
2. MutatePES 闭环（gene 级变异 + 规则驱动候选排序 + LLM 最终选择）
3. parent 选择硬编码为 best fitness

**明确推迟到 M1.5+：**
- Boltzmann / 锦标赛选择
- population summary
- 选择压力可调控
```

- [ ] **Step 3: 更新 §10 推荐演进路线表**

将 M1 行更新为"已完成"，新增 M1.5 行：

```text
| M1 | 单谱系进化 | MutatePES、parent/child、genes/snapshots 真接入 | ✅ 完成 |
| M1.5 | 选择压力 | Boltzmann 选择、population summary、选择压力可调 | 待开始 |
```

- [ ] **Step 4: 提交**

```bash
cd /home/iomgaa/Projects/Herald2 && git add docs/architecture.md && git commit -m "docs: 更新架构文档至 M1 完成状态，标记选择压力推迟到 M1.5"
```

---

## 计划自检

### Spec 覆盖

| 设计要点 | 对应 Task |
|----------|----------|
| `parse_genes_from_code()` | Task 1 |
| DraftPES Summarize 写入 genes | Task 2 |
| `rank_mutation_candidates()` | Task 3 |
| MutatePES YAML + prompt_spec | Task 4 |
| mutate_plan.j2 模板 | Task 5 |
| mutate_execute.j2 模板 | Task 6 |
| mutate_summarize.j2 模板 | Task 7 |
| mutate-diff-check Skill | Task 8 |
| MutatePES 核心实��� | Task 9 |
| Scheduler mutate 阶段 + parent 选择 | Task 10 |
| 集成测试 | Task 11 |
| 架构文档更新 | Task 12 |

### Placeholder 扫描

已检查全部 Task，无 TBD / TODO / "implement later" / "similar to Task N" 占位符。

### 类型一致性

- `parse_genes_from_code` 返回 `dict[str, str]`：Task 1 定义，Task 2/3/9 使用，签名一致
- `rank_mutation_candidates` 返回 `list[dict[str, Any]]`：Task 3 定义，Task 9 使用，签名一致
- `PESSolution.target_slot`：已存在于 `types.py:86`，Task 9 使用
- `MutatePES` 继��� `DraftPES`：Task 9 实现
