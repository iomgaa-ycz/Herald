# 技术方案（TD）— Herald2

> **状态**: v0.1
> **更新**: 2026-03-28
> **目标阶段**: 实现“单进程、单任务类型、串行驱动的 `DraftPES` MVP 闭环”

---

## 1. 摘要

当前阶段的技术目标，不是实现完整进化系统，而是把以下最小闭环真正做实：

```text
main.py
  -> Scheduler(task_stages)
  -> TaskDispatcher
  -> FeatureExtractPES(plan/execute/summarize)  # 前置：数据分析 + TaskSpec 生成
  -> DraftPES(plan/execute/summarize)            # 主链路：方案生成
  -> solution.py / submission.csv
  -> val_metric_value / fitness
  -> test_score
  -> DB / 日志 / 工作空间工件
```

本 TD 文档回答三个问题：

1. 当前阶段需要哪些模块
2. 每个模块的接口应该长什么样
3. 如何验证这条 MVP 闭环确实成立

本文中的”单任务类型”在技术层拆成以下维度：

- **操作类型**：`feature_extract`（前置）+ `draft`（主链路）
- **唯一竞赛 schema 类型**：`tabular`（另有 `generic` 作为兜底）

---

## 2. 技术决策

| 决策项 | 结论 | 理由 |
|---|---|---|
| 运行拓扑 | 单进程、串行调度 | 先把最小闭环打实，避免过早并行化 |
| 核心执行模型 | 固定 `Plan / Execute / Summarize` | 保持所有 PES 的统一骨架 |
| 当前 PES | `FeatureExtractPES` + `DraftPES` | `FeatureExtractPES` 前置运行一次做数据分析和 TaskSpec 生成；`DraftPES` 消费其产出 |
| 当前操作类型 | `feature_extract` + `draft` | Scheduler 通过 `task_stages` 按序调度 |
| 当前竞赛 schema 类型 | `tabular`（主）+ `generic`（兜底） | 当前 CI 阻塞集属于 tabular；generic 模板兼容非 tabular 任务 |
| TaskSpec 来源 | `FeatureExtractPES` 动态生成 | 不再 bootstrap 阶段静态构造，由 LLM Agent 分析竞赛数据后生成 |
| GenomeSchema 模板 | Python 代码模板文件 | `config/genome_templates/tabular.py` + `generic.py`，含 GENE 标记的 slot 骨架 |
| 当前唯一 Agent | `kaggle_master` | 先稳定 prompt persona 与接口边界 |
| 系统核心对象 | `PESSolution` | 所有运行状态、工件路径、分数都挂在 solution 上 |
| 记录体系 | 日志 + SQLite + 工作空间工件 | 满足实时观测、结构化查询、可回放 |
| Prompt 装配 | `prompt_spec + fragments + jinja templates` | 保证上下文结构化、模板可测试 |
| 运行时主分数 | `val_metric_value -> fitness` | 用于系统自我调度与进化 |
| 外部真实性分数 | `test_score` | 用于离线分析与真实性验证，不参与在线调度 |
| 测试策略 | 真实竞赛数据 + 真实运行回放优先 | 避免失真 mock |
| LLM 质量评测 | `pytest + assert` 为主，`deepeval` 评审文本质量 | 结构正确性与语义质量分层判定 |

---

## 3. 范围与非范围

### 3.1 本阶段必须完成

- `main.py` 能装配并启动 `FeatureExtractPES` 和 `DraftPES`
- `Scheduler` 支持 `task_stages`，能按序调度 `feature_extract(1次) -> draft(N次)`
- `FeatureExtractPES` 能完整执行 `plan -> execute -> summarize`，产出 TaskSpec + data_profile + GenomeSchema 选择
- `DraftPES` 能完整执行 `plan -> execute -> summarize`，消费 FeatureExtractPES 的产出
- `execute` 阶段输出能落盘为真实 `working/solution.py`
- `execute` 阶段生成真实 `working/submission.csv`
- 系统能记录 `llm_calls`、`exec_logs`、代码快照、工件路径
- 系统能产出 run 级 `metadata.json` 与配置快照
- 系统能拿到 `val_metric_value` 与 `fitness`
- 系统能补采 `test_score`
- 测试体系基于真实数据与真实回放可验证这条闭环

### 3.2 本阶段明确不做

- `MutatePES` / `MergePES`
- 多任务并行与多岛
- 分布式消息系统
- 用 `test_score` 驱动在线选择
- L2/L3 真正回流到 Plan

---

## 4. 模块设计

## 4.1 启动与装配层

**状态**: ✅ 已有骨架，🔄 需补运行时上下文
**层级**: CLI 入口 / Bootstrap
**前置依赖**: `ConfigManager`、`Workspace`、`HeraldDB`、`EventBus`、`DraftPES`
**测试文件**: `tests/unit/test_main_bootstrap.py`

**文件**: `core/main.py`
**职责**:

- 读取配置
- 创建工作空间
- 初始化数据库
- 初始化事件系统
- 写入 run 级元数据与配置快照
- 显式装配 `FeatureExtractPES` 和 `DraftPES`
- 启动 `Scheduler`（使用 `task_stages`）

### 关键函数签名

```python
def bootstrap_feature_extract_pes(
    config: HeraldConfig,
    workspace: Workspace,
    db: HeraldDB,
) -> FeatureExtractPES

def bootstrap_draft_pes(
    config: HeraldConfig,
    workspace: Workspace,
    db: HeraldDB,
) -> DraftPES

def main() -> None
```

### 当前阶段要求

- `bootstrap_feature_extract_pes()` 装配前置数据分析 PES
- `bootstrap_draft_pes()` 装配主链路 DraftPES
- `FeatureExtractPES` 的 `runtime_context` 至少包含：
  - `competition_dir`
  - `run_id`
- `DraftPES` 的 `runtime_context` 初始只包含基础信息，`task_spec` / `data_profile` / `schema` 由 Scheduler 从 FeatureExtractPES 产出动态注入
- `Scheduler` 使用 `task_stages=[("feature_extract", 1), ("draft", max_tasks)]`
- bootstrap 阶段必须产出 run 级 `metadata.json`，至少包含：
  - `run_id`
  - `competition_id`
  - `competition_root_dir`
  - `public_data_dir`
  - `workspace_dir`
  - `config_snapshot`
  - `started_at`
- run 完成后必须回写 `finished_at`

### 验证 Checkpoint

- `bootstrap_draft_pes()` 返回的实例被正确注册到 `PESRegistry`
- `main()` 启动后能触发 `Scheduler.run()`
- 工作空间中存在可读的 run 级 `metadata.json`

---

## 4.2 调度与事件层

**状态**: ✅ 已实现
**层级**: Orchestrator MVP
**前置依赖**: `EventBus`、`AgentRegistry`、`PESRegistry`
**测试文件**:

- `tests/integration/test_dispatch_flow.py`
- `tests/integration/test_scheduler_flow.py`

**文件**:

- `core/scheduler/scheduler.py`
- `core/events/types.py`
- `core/events/dispatcher.py`

**职责**:

- 串行发出任务
- 将 `TaskDispatchEvent` 转换为 `TaskExecuteEvent`
- 接收 `TaskCompleteEvent`

### 关键接口签名

```python
class Scheduler:
    def __init__(
        self,
        competition_dir: str,
        max_tasks: int = 1,
        task_name: str = "draft",
        agent_name: str = "kaggle_master",
        context: dict[str, Any] | None = None,
        task_stages: list[tuple[str, int]] | None = None,  # [NEW]
    ) -> None
    def run(self) -> None

class TaskDispatchEvent(Event): ...
class TaskExecuteEvent(Event): ...
class TaskCompleteEvent(Event):
    output_context: dict[str, Any]  # [NEW] 阶段产出上下文

class TaskDispatcher:
    def handle_dispatch(self, event: TaskDispatchEvent) -> None

def setup_task_dispatcher() -> TaskDispatcher
```

### task_stages 调度机制

`task_stages` 是 `list[tuple[str, int]]`，每个元素为 `(task_name, count)`。

```python
# 当前阶段的标准配置
task_stages = [
    ("feature_extract", 1),  # 前置：运行 1 次
    ("draft", max_tasks),    # 主链路：运行 N 次
]
```

调度流程：
1. 按 `task_stages` 顺序逐 stage 执行
2. 每个 stage 串行发出 `count` 个任务
3. stage 完成后，从 `TaskCompleteEvent.output_context` 收集产出
4. 产出合并到 `shared_context`，注入下一 stage 的 dispatch context

向后兼容：不传 `task_stages` 时，退化为 `[(task_name, max_tasks)]`。

### 当前阶段约束

- task_stages 固定为 `[("feature_extract", 1), ("draft", N)]`
- agent 名固定为 `kaggle_master`
- 一次只允许一个在执行中的 task
- `TaskCompleteEvent.status` 当前接受 `completed` / `failed`

### 验证 Checkpoint

- `Scheduler(task_stages=[("feature_extract", 1), ("draft", 2)])` 能按序执行 3 个任务
- `feature_extract` stage 的 `output_context` 能注入 `draft` stage 的 dispatch context
- `TaskCompleteEvent` 能解除调度等待

---

## 4.3 运行期数据模型层

**状态**: ✅ 已实现骨架，🔄 需补字段使用
**层级**: 核心数据模型
**前置依赖**: 无
**测试文件**:

- `tests/unit/test_draft_pes.py`
- 后续新增：`tests/unit/test_solution_model.py`

**文件**:

- `core/pes/types.py`
- `core/pes/schema.py`

**职责**:

- 定义运行中的 `Solution`
- 定义任务规格与 schema
- 为 Prompt、DB、调度提供统一数据边界

### 关键接口签名

```python
@dataclass(slots=True)
class PESSolution:
    id: str
    operation: str
    generation: int
    status: str
    created_at: str
    parent_ids: list[str]
    lineage: str | None
    run_id: str | None
    finished_at: str | None = None
    target_slot: str | None = None
    workspace_dir: str | None = None
    solution_file_path: str | None = None
    submission_file_path: str | None = None
    plan_summary: str = ""
    execute_summary: str = ""
    summarize_insight: str = ""
    genes: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[str, Any] | None = None
    fitness: float | None = None
    phase_outputs: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]
    def to_prompt_payload(self) -> dict[str, Any]

@dataclass(slots=True)
class TaskSpec:
    task_type: str
    competition_name: str
    objective: str
    metric_name: str
    metric_direction: str

@dataclass(slots=True)
class SlotContract:
    function_name: str
    params: list[dict[str, str]]
    return_type: str

@dataclass(slots=True)
class GenomeSchema:
    task_type: str
    slots: dict[str, SlotContract | None]
    template_file: str | None = None  # [NEW] 对应代码模板文件路径
```

### TaskSpec 动态生成

`TaskSpec` 不再由 bootstrap 静态构造。其生成链路为：

1. `FeatureExtractPES.execute()` 让 LLM Agent 分析竞赛数据和描述
2. LLM 输出结构化 JSON，包含 `task_type`、`competition_name`、`objective`、`metric_name`、`metric_direction`
3. `FeatureExtractPES.handle_phase_response()` 解析 JSON 并持久化到 `workspace/working/task_spec.json`
4. Scheduler 收集产出后注入 DraftPES 的 dispatch context

### GenomeSchema 模板加载

```python
def load_genome_template(task_type: str) -> tuple[GenomeSchema, str]:
    """根据 task_type 加载对应的 GenomeSchema 和代码模板内容。

    Args:
        task_type: 任务类型（"tabular" / 其他）

    Returns:
        (GenomeSchema, template_content) 元组
    """
```

模板映射规则：
- `task_type == "tabular"` → `config/genome_templates/tabular.py`
- 其他 → `config/genome_templates/generic.py`

### 当前阶段要求

- `PESSolution.metrics` 至少要能承载：
  - `val_metric_name`
  - `val_metric_value`
  - `val_metric_direction`
- `PESSolution.metadata` 至少要能承载：
  - `schema_task_type`
  - `test_score`
  - `test_score_direction`
  - `test_valid_submission`
  - `test_medal_level`
  - `test_competition_id`
  - `test_gold_threshold`
  - `test_silver_threshold`
  - `test_bronze_threshold`
  - `test_median_threshold`
  - `test_graded_at`

### 验证 Checkpoint

- `to_record()` 生成的字典可直接写入 `solutions`
- `to_prompt_payload()` 可直接喂给模板系统
- `TaskSpec` / `GenomeSchema` 可由真实竞赛 case 构造

---

## 4.4 PES Runtime 抽象层

**状态**: ✅ 已实现
**层级**: 系统内核
**前置依赖**: `EventBus`、`PromptManager`、`PESRegistry`、`HeraldDB`
**测试文件**: `tests/unit/test_draft_pes.py`

**文件**: `core/pes/base.py`
**职责**:

- 固定 `plan / execute / summarize` 三阶段
- 统一 Prompt 上下文构造
- 统一模型调用
- 统一 trace 记录
- 统一失败处理

### 关键接口签名

```python
class BasePES(ABC):
    def __init__(
        self,
        config: PESConfig,
        llm: object,
        db: object | None = None,
        workspace: object | None = None,
        tools: dict[str, Any] | list[Any] | None = None,
        hooks: HookManager | None = None,
        runtime_context: dict[str, Any] | None = None,
        prompt_manager: PromptManager | None = None,
    ) -> None

    def on_execute(self, event: TaskExecuteEvent) -> None

    async def run(
        self,
        agent_profile: AgentProfile,
        generation: int = 0,
        parent_solution: PESSolution | None = None,
    ) -> PESSolution

    async def plan(
        self,
        solution: PESSolution,
        parent_solution: PESSolution | None = None,
    ) -> PESSolution

    async def execute_phase(
        self,
        solution: PESSolution,
        parent_solution: PESSolution | None = None,
    ) -> PESSolution

    async def summarize(
        self,
        solution: PESSolution,
        parent_solution: PESSolution | None = None,
    ) -> PESSolution

    def create_solution(
        self,
        generation: int,
        parent_solution: PESSolution | None = None,
    ) -> PESSolution

    def build_prompt_context(
        self,
        phase: str,
        solution: PESSolution,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]

    def render_prompt(self, phase: str, context: dict[str, Any]) -> str

    async def call_phase_model(
        self,
        phase: str,
        prompt: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> object

    @abstractmethod
    async def handle_phase_response(
        self,
        phase: str,
        solution: PESSolution,
        response: object,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]
```

### 当前阶段要求

- `BasePES.run()` 必须保证：
  - solution 创建后立即落库
  - 每个 phase 调用都记录 `llm_calls`
  - 失败状态能正确写回 `solutions`
- `after_run` hook 是 test_score 获取的推荐挂点

### 验证 Checkpoint

- `run()` 顺序固定为 `plan -> execute -> summarize`
- `handle_phase_failure()` 能把状态置为 `failed`
- `call_phase_model()` 能透传 `cwd/env`

---

## 4.5 FeatureExtractPES 具体实现层

**状态**: ✅ MVP 已实现
**层级**: 前置数据分析 PES
**前置依赖**: `BasePES`、`Workspace`、`HeraldDB`
**测试文件**: `tests/unit/test_feature_extract_pes.py`

**文件**: `core/pes/feature_extract.py`
**职责**:

- 每竞赛运行一次，分析竞赛数据并生成 TaskSpec
- plan 阶段：分析竞赛 description.md，规划数据探索策略
- execute 阶段：LLM Agent 用 Bash 工具读取数据文件，生成 TaskSpec + data_profile + 选择 GenomeSchema 模板
- summarize 阶段：总结数据特征、关键发现、建模建议

### 关键接口签名

```python
class FeatureExtractPES(BasePES):
    def build_phase_model_options(
        self,
        phase: str,
        solution: PESSolution,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]

    async def handle_phase_response(
        self,
        phase: str,
        solution: PESSolution,
        response: object,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]
```

### execute 阶段 LLM Agent 行为

LLM Agent 在 execute 阶段使用 Bash 工具执行以下数据探索操作：

1. 读取竞赛 `description.md`，提取任务目标、评估指标
2. `ls` 数据目录，了解文件结构
3. `head -20 train.csv` 查看数据样本
4. `python -c "import pandas as pd; df = pd.read_csv('train.csv'); print(df.shape, df.dtypes, df.isnull().sum())"` 获取数据概况
5. 分析 `sample_submission.csv` 了解输出格式

LLM Agent 最终输出必须包含：

```json
{
  "task_spec": {
    "task_type": "tabular",
    "competition_name": "...",
    "objective": "...",
    "metric_name": "auc",
    "metric_direction": "maximize"
  },
  "data_profile": "... 数据概况报告文本 ...",
  "genome_template": "tabular"
}
```

### 产出与持久化

| 产出 | 持久化位置 | 传递方式 |
|---|---|---|
| TaskSpec JSON | `workspace/working/task_spec.json` | `TaskCompleteEvent.output_context["task_spec"]` |
| 数据概况报告 | `workspace/working/data_profile.md` | `TaskCompleteEvent.output_context["data_profile"]` |
| GenomeSchema 模板类型 | `solution.metadata["genome_template"]` | `TaskCompleteEvent.output_context["genome_template"]` |

### PES 配置

```yaml
# config/pes/feature_extract.yaml
name: feature_extract
operation: feature_extract
solution_file_name: data_profile.md
submission_file_name: null

phases:
  plan:
    max_retries: 1
    allowed_tools: []
    max_turns: 1
  execute:
    max_retries: 1
    allowed_tools: ["Bash", "Read", "Glob", "Grep"]
    max_turns: 12
  summarize:
    max_retries: 1
    allowed_tools: []
    max_turns: 1
```

### 验证 Checkpoint

- `FeatureExtractPES.run()` 能完整执行三阶段
- execute 阶段产出的 TaskSpec JSON 可解析为 `TaskSpec` dataclass
- `data_profile.md` 非空且包含字段信息和数据统计
- `genome_template` 值为 `"tabular"` 或 `"generic"`
- 竞赛 `tabular-playground-series-may-2022` 能被正确识别为 `tabular` 类型

---

## 4.6 DraftPES 具体实现层

**状态**: 🔄 部分完成
**层级**: 主链路 PES，消费 FeatureExtractPES 产出
**前置依赖**: `BasePES`、`Workspace`、`HeraldDB`、`FeatureExtractPES` 产出
**测试文件**: `tests/unit/test_draft_pes.py`

**文件**: `core/pes/draft.py`
**职责**:

- 执行从零起草方案的 MVP 流程
- 在三阶段响应中更新 `PESSolution`
- 生成最小工件路径
- 发出 `TaskCompleteEvent`

### 关键接口签名

```python
class DraftPES(BasePES):
    def build_phase_model_options(
        self,
        phase: str,
        solution: PESSolution,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]

    async def handle_phase_response(
        self,
        phase: str,
        solution: PESSolution,
        response: object,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]
```

### 当前已完成

- execute 阶段能把 `cwd` 指向 `workspace.working_dir`
- execute 阶段能注入 `HERALD_DB_PATH`
- 三阶段文本摘要能写回 `solution`
- summarize 阶段会发出 `TaskCompleteEvent`

### 当前待补

- 消费 FeatureExtractPES 产出的 `task_spec` / `data_profile` / `schema`（通过 Scheduler 注入的 dispatch context）
- 建立 execute 阶段的 `tool-write` 契约：Agent 必须在工作空间用 tools 写出真实 `working/solution.py`
- 运行 `solution.py`
- 提取 `val_metric_value`
- 生成真实 `submission.csv`
- 写入 `code_snapshots`
- 记录 `exec_logs`
- 触发 `test_score` 评分

### 验证 Checkpoint

- 当前最小版本：`solution_file_path` / `submission_file_path` 已挂载
- 阶段目标版本：`working/solution.py` 不再是空文件，且有真实内容

---

## 4.7 Prompt 装配层

**状态**: ✅ 已实现
**层级**: 上下文控制层
**前置依赖**: `config/prompts/*`
**测试文件**:

- `tests/unit/test_prompt_manager.py`
- `tests/unit/test_agent_registry.py`

**文件**:

- `core/prompts/manager.py`
- `config/prompts/prompt_spec.yaml`
- `config/prompts/templates/draft_*.j2`

**职责**:

- 验证 prompt spec
- 拼接 fragments
- 渲染 phase 模板

### 关键接口签名

```python
class PromptManager:
    def __init__(
        self,
        template_dir: Path,
        fragments_dir: Path,
        spec_path: Path,
    ) -> None

    def get_template_spec(self, operation: str, phase: str) -> dict[str, Any]
    def load_fragment(self, fragment_name: str) -> str
    def build_static_fragments_text(self, template_spec: dict[str, Any]) -> str
    def validate_context(
        self,
        template_key: str,
        template_spec: dict[str, Any],
        context: dict[str, Any],
    ) -> None
    def build_prompt(
        self,
        operation: str,
        phase: str,
        context: dict[str, Any],
    ) -> str
```

### 当前阶段要求

- `feature_extract_plan` 必须消费 `solution`，引导 LLM 规划数据探索策略
- `feature_extract_execute` 必须消费 `solution` / `workspace`，引导 LLM 用工具分析数据并输出 TaskSpec + data_profile
- `feature_extract_summarize` 必须消费 `solution` / `execution_log`
- `draft_plan` 必须消费 `task_spec` / `schema` / `data_profile`
- `draft_execute` 必须消费 `workspace` / `solution.plan_summary` / `data_profile`
- `draft_summarize` 必须消费 `execution_log` / `metrics`

### 验证 Checkpoint

- 三个 `draft_*` 模板可正常渲染
- 缺必填字段时快速失败

---

## 4.8 GenomeSchema 模板加载层

**状态**: ✅ MVP 已实现
**层级**: 任务规格层
**前置依赖**: `config/genome_templates/`
**测试文件**: `tests/unit/test_genome_template.py`

**文件**:

- `core/pes/schema.py`（扩展）
- `config/genome_templates/tabular.py`（新建）
- `config/genome_templates/generic.py`（新建）

**职责**:

- 根据 `task_type` 加载对应的 GenomeSchema 定义和 Python 代码模板
- 为 DraftPES 的 prompt 提供 `template_content`（代码骨架）和 `schema`（slot 结构）

### 关键接口签名

```python
def load_genome_template(task_type: str) -> tuple[GenomeSchema, str]:
    """根据 task_type 加载 GenomeSchema 和代码模板内容。

    Args:
        task_type: 任务类型 ("tabular" / 其他)

    Returns:
        (schema, template_content) 元组
        - schema: GenomeSchema 实例，含 slot 定义
        - template_content: Python 代码模板字符串
    """
```

### 模板文件规范

模板文件遵循 `Reference/tabular_ml.py` 的标记约定：

```python
# === GENE:SLOT_NAME_START ===
def slot_function(params):
    """docstring"""
    pass  # LLM 填充
# === GENE:SLOT_NAME_END ===

# === FIXED:SECTION_NAME ===
def fixed_function():
    """不可修改的固定逻辑"""
    ...
# === FIXED:SECTION_NAME_END ===
```

### tabular.py 模板 slots

| Slot 名 | 函数 | 职责 |
|---|---|---|
| `DATA` | `load_data(config)` | 从 DATA_DIR 读取数据，返回 train/val/test/target |
| `FEATURE_ENG` | `build_features(data, config)` | 特征工程 |
| `MODEL` | `build_model(config)` | 模型构建 |
| `POSTPROCESS` | `build_postprocess(config)` | 预测后处理与输出格式化 |

固定区域：`EVALUATE`、`TRAIN_LOOP`、`ENTRY`

### generic.py 模板 slots

| Slot 名 | 函数 | 职责 |
|---|---|---|
| `DATA` | `load_data(config)` | 数据加载 |
| `PROCESS` | `process(data, config)` | 通用数据处理 |
| `MODEL` | `build_model(config)` | 模型构建 |
| `POSTPROCESS` | `build_postprocess(config)` | 后处理 |

固定区域：`EVALUATE`、`MAIN`、`ENTRY`

### 验证 Checkpoint

- `load_genome_template("tabular")` 返回含 4 个 slot 的 GenomeSchema + 非空 template_content
- `load_genome_template("unknown_type")` 返回 generic 模板
- 模板代码中的 GENE 标记可被稳定识别

---

## 4.9 LLM 接口层

**状态**: ✅ 已实现
**层级**: 模型访问层
**前置依赖**: `claude_agent_sdk`
**测试文件**: 当前以集成桩测试为主，后续补真实回放测试

**文件**: `core/llm.py`
**职责**:

- 封装 Claude Agent SDK
- 统一返回 `LLMResponse`
- 暴露 `cwd/env/allowed_tools` 等控制参数

### 关键接口签名

```python
@dataclass(slots=True)
class LLMConfig:
    model: str = "glm-5"
    max_tokens: int = 32 * 1024
    max_turns: int = 16
    permission_mode: str = "bypassPermissions"

@dataclass(slots=True)
class LLMResponse:
    result: str
    turns: list[dict[str, Any]]
    model: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    duration_ms: int
    session_id: str | None

class LLMClient:
    async def execute_task(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        allowed_tools: list[str] | None = None,
        mcp_servers: dict[str, Any] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> LLMResponse
```

### 当前阶段要求

- `result` 仅作为文本摘要与人工审阅材料，不作为代码真相来源
- `turns` 必须完整保留 tool 调用痕迹，用于回放、契约检查与 deepeval 审阅
- `cwd/env` 透传必须可靠

### 验证 Checkpoint

- SDK 不可用时 bootstrap 明确失败
- `execute_task()` 能返回统一结构

---

## 4.10 Workspace 与工件层

**状态**: ✅ 已实现基础能力，🔄 待接线
**层级**: Harness 文件层
**前置依赖**: 文件系统
**测试文件**: 后续新增 `tests/unit/test_workspace.py`

**文件**: `core/workspace.py`
**职责**:

- 创建工作空间目录
- 软链接竞赛数据
- 保存历史版本
- 维护 `best/`

### 关键接口签名

```python
class Workspace:
    def __init__(self, root: str | Path) -> None
    def create(self, competition_dir: str | Path) -> Workspace
    def save_version(
        self,
        code: str,
        submission: str,
        generation: int,
        solution_id: str,
    ) -> Path
    def promote_best(
        self,
        version_dir: Path,
        metadata: dict[str, Any] | None = None,
    ) -> None
    def get_working_solution_path(self) -> Path
    def get_log_path(self, name: str) -> Path
    def summary(self) -> dict[str, str]
```

### 当前阶段要求

- `create()` 必须优先链接 `prepared/public`
- `working/` 用于当前 solution 输出
- 工作空间根目录必须承载 run 级 `metadata.json`
- 阶段目标版本必须把真实 `solution.py` / `submission.csv` 落到 `working/`
- 成功 run 后应调用 `save_version()`
- 最优 `fitness` 时应调用 `promote_best()`

### 验证 Checkpoint

- `data/` 目录能正确映射竞赛数据
- 版本目录能正确保存 solution 与 submission

---

## 4.11 数据库与追踪层

**状态**: ✅ schema 与 facade 已实现，🔄 主流程仍未完全接通
**层级**: Harness 结构化事实层
**前置依赖**: SQLite
**测试文件**: 后续新增 `tests/unit/test_database_roundtrip.py`

**文件**:

- `core/database/herald_db.py`
- `core/database/schema.py`
- `core/database/repositories/*`

**职责**:

- 持久化 `solutions`
- 持久化 trace 与代码快照
- 提供 lineage / population / l2 查询

### 关键接口签名

```python
class HeraldDB:
    def insert_solution(self, solution) -> None
    def update_solution_artifacts(
        self,
        solution_id: str,
        workspace_dir: str | None = None,
        solution_file_path: str | None = None,
        submission_file_path: str | None = None,
    ) -> None
    def update_solution_status(
        self,
        solution_id: str,
        status: str,
        fitness: float | None = None,
        metric_name: str | None = None,
        metric_value: float | None = None,
        metric_direction: str | None = None,
        execute_summary: str | None = None,
        summarize_insight: str | None = None,
        finished_at: str | None = None,
    ) -> None
    def insert_genes(self, solution_id: str, genes: dict) -> None
    def insert_code_snapshot(self, solution_id: str, full_code: str) -> None
    def log_llm_call(self, **kwargs) -> str
    def log_exec(self, **kwargs) -> str
    def log_contract_check(self, **kwargs) -> str
```

### 当前阶段要求

- 至少打通：
  - `solutions`
  - `llm_calls`
  - `exec_logs`
  - `code_snapshots`
- `metric_value` 在当前阶段表示 `val_metric_value`
- `test_score` 当前写入 `workspace/logs/grading_result.json`，并可同步写入 DB 独立表
- `test_score` 不得通过 `solution.metadata` / `to_prompt_payload()` 暴露给 agent

### 验证 Checkpoint

- `PESSolution.to_record()` 能正确落入 `solutions`
- `log_llm_call()` / `log_exec()` 可查询回放

---

## 4.12 test_score 评分层

**状态**: ✅ 已接入运行时 hook
**层级**: 外部评测层
**前置依赖**: `mlebench`
**测试文件**: 后续新增 `tests/unit/test_grading.py`

**文件**: `tests/grading.py`
**职责**:

- 优先从显式上下文读取 `competition_id` 与 `mlebench_data_dir`
- 在缺显式字段时，从竞赛路径 fallback 推断 `competition_id` 与 `data_dir`
- 调用 MLE-Bench 评分接口
- 归一化 `CompetitionReport`
- 将 `test_score` 写入 `workspace/logs/grading_result.json`
- 可同步写入 DB 独立评分记录
- 不得通过 `to_prompt_payload()` 暴露给 agent

### 关键接口签名

```python
@dataclass(frozen=True, slots=True)
class GradingConfig:
    enabled: bool = True
    competition_id: str | None = None
    competition_root_dir: str | Path | None = None
    public_data_dir: str | Path | None = None
    mlebench_data_dir: str | Path | None = None
    competition_dir: str | Path | None = None
    workspace_logs_dir: str | Path | None = None
    accepted_statuses: tuple[str, ...] = ("completed", "success")

@dataclass(frozen=True, slots=True)
class GradingResult:
    competition_id: str
    test_score: float
    test_score_direction: str
    test_valid_submission: bool
    test_medal_level: str
    test_above_median: bool
    gold_threshold: float | None
    silver_threshold: float | None
    bronze_threshold: float | None
    median_threshold: float | None
    graded_at: str

def grade_submission(
    submission_path: str | Path,
    competition_id: str,
    data_dir: str | Path,
) -> GradingResult | None

def grade_solution_submission(
    submission_path: str | Path,
    competition_dir: str | Path,
) -> GradingResult | None

class MLEBenchGradingHook:
    def __call__(self, context: object) -> GradingResult | None

def create_grading_hook(
    enabled: bool = True,
    competition_dir: str | Path | None = None,
    *,
    competition_id: str | None = None,
    competition_root_dir: str | Path | None = None,
    public_data_dir: str | Path | None = None,
    mlebench_data_dir: str | Path | None = None,
) -> MLEBenchGradingHook
```

### 当前阶段要求

- 接受 `completed` / `success`
- 推荐挂在 `after_run`
- 优先消费显式上下文字段：
  - `competition_id`
  - `competition_root_dir`
  - `public_data_dir`
  - `mlebench_data_dir`
- `competition_dir` 路径推断只能作为 fallback
- `test_score` 只用于外部真实性评估，不覆盖 `fitness`

### 验证 Checkpoint

- 显式上下文字段存在时，评分链路不依赖路径猜测
- 缺显式字段时，仍能从 `competition_root`、`prepared`、`prepared/public` 三种路径形态推断竞赛信息
- `submission.csv` 缺失时能安全跳过

---

## 5. 模块依赖关系

### 5.1 运行链依赖

```text
ConfigManager
  -> main.py
  -> Workspace
  -> HeraldDB
  -> EventBus + TaskDispatcher
  -> FeatureExtractPES + DraftPES
  -> Scheduler(task_stages)
  -> Stage 1: TaskDispatchEvent("feature_extract")
  -> FeatureExtractPES.run() -> TaskSpec + data_profile + genome_template
  -> Stage 2: TaskDispatchEvent("draft", context=上游产出)
  -> DraftPES.run() -> PromptManager + LLMClient
  -> Workspace artifacts + HeraldDB traces
  -> MLEBenchGradingHook
```

### 5.2 数据依赖

```text
竞赛目录 (description.md + data files)
  -> FeatureExtractPES (plan / execute / summarize)
  -> TaskSpec + data_profile + genome_template
  -> Scheduler shared_context
  -> DraftPES runtime_context
  -> PromptManager context (task_spec + schema + data_profile + template_content)
  -> DraftPES plan / execute
  -> PESSolution.metrics / fitness
  -> HeraldDB.solutions
  -> grading.py(test_score)
```

---

## 6. 下一步任务清单

下面的任务清单就是当前阶段的直接开发顺序。
每个任务都必须在对应测试通过后，才能进入下一项。

### 6.1 Task 1：实现 FeatureExtractPES

**状态**: ✅ MVP 已实现
**目标**: 实现前置数据分析 PES，能分析竞赛数据并动态生成 TaskSpec + data_profile + GenomeSchema 选择。

**任务是什么**

- 创建 `FeatureExtractPES`，继承 `BasePES`
- 实现三阶段（plan/execute/summarize）的 `handle_phase_response`
- execute 阶段 LLM Agent 用 Bash 工具读取数据文件，输出结构化 TaskSpec + data_profile
- 创建对应的 PES 配置和 Prompt 模板

**要干什么**

- 新建 `core/pes/feature_extract.py`
- 新建 `config/pes/feature_extract.yaml`
- 新建 `config/prompts/templates/feature_extract_plan.j2`
- 新建 `config/prompts/templates/feature_extract_execute.j2`
- 新建 `config/prompts/templates/feature_extract_summarize.j2`
- 更新 `config/prompts/prompt_spec.yaml` 添加三个模板规格
- `handle_phase_response` 在 execute 阶段解析 LLM 输出中的 TaskSpec JSON 和 data_profile
- 持久化到 `workspace/working/task_spec.json` 和 `workspace/working/data_profile.md`
- summarize 阶段发出 `TaskCompleteEvent`（携带 `output_context`）

**涉及文件**

- `core/pes/feature_extract.py` [NEW]
- `config/pes/feature_extract.yaml` [NEW]
- `config/prompts/templates/feature_extract_*.j2` [NEW]
- `config/prompts/prompt_spec.yaml` [MODIFY]

**必过测试**

- `tests/unit/test_feature_extract_pes.py`

**测试通过标准**

- `FeatureExtractPES.run()` 能完整执行三阶段
- execute 阶段产出的 TaskSpec JSON 可解析为 `TaskSpec` dataclass
- `data_profile.md` 非空
- `genome_template` 值合法（`"tabular"` 或 `"generic"`）

### 6.2 Task 2：实现 GenomeSchema 模板体系

**状态**: ✅ MVP 已实现
**目标**: 为不同任务类型提供代码模板骨架，DraftPES 在生成代码时以此为基础。

**任务是什么**

- 创建 tabular.py 和 generic.py 代码模板
- 实现 `load_genome_template()` 加载函数
- 扩展 `GenomeSchema` dataclass 支持 `template_file`

**要干什么**

- 新建 `config/genome_templates/tabular.py`（基于 `Reference/tabular_ml.py`）
- 新建 `config/genome_templates/generic.py`
- 修改 `core/pes/schema.py`：添加 `template_file` 字段和 `load_genome_template()` 函数

**涉及文件**

- `config/genome_templates/tabular.py` [NEW]
- `config/genome_templates/generic.py` [NEW]
- `core/pes/schema.py` [MODIFY]

**必过测试**

- `tests/unit/test_genome_template.py`

**测试通过标准**

- `load_genome_template("tabular")` 返回含 4 个 slot 的 GenomeSchema + 非空 template_content
- `load_genome_template("unknown")` 返回 generic 模板
- tabular 模板中 GENE 标记区域可被稳定识别

### 6.3 Task 3：Scheduler 支持 task_stages + 数据传递

**状态**: ⬜ 待实现
**目标**: 让 Scheduler 能按序调度多个 PES stage，并在 stage 间传递产出数据。

**任务是什么**

- Scheduler 新增 `task_stages` 参数
- 实现 stage 间的 `output_context` 收集与传递
- `TaskCompleteEvent` 新增 `output_context` 字段

**要干什么**

- 修改 `core/scheduler/scheduler.py`：支持 `task_stages` 调度
- 修改 `core/events/types.py`：`TaskCompleteEvent` 添加 `output_context`
- stage 完成后收集 `output_context` 合并到下一 stage 的 dispatch context

**涉及文件**

- `core/scheduler/scheduler.py` [MODIFY]
- `core/events/types.py` [MODIFY]

**必过测试**

- `tests/unit/test_scheduler_stages.py`

**测试通过标准**

- `Scheduler(task_stages=[("a", 1), ("b", 2)])` 按序发出 3 个任务
- stage a 的 `output_context` 在 stage b 的 dispatch context 中可见
- 不传 `task_stages` 时向后兼容

### 6.4 Task 4：Bootstrap 整合 + DraftPES 消费 data_profile

**状态**: ⬜ 待实现
**目标**: 让 main.py 装配两个 PES，DraftPES 能消费 FeatureExtractPES 的产出。

**任务是什么**

- main.py 装配 `FeatureExtractPES` 和 `DraftPES`
- 使用 `task_stages=[("feature_extract", 1), ("draft", max_tasks)]` 启动 Scheduler
- DraftPES prompt 模板新增 `data_profile` 区块

**要干什么**

- 修改 `core/main.py`：新增 `bootstrap_feature_extract_pes()`，使用 `task_stages`
- 修改 `config/prompts/templates/draft_plan.j2`：新增 `data_profile` 区块
- 修改 `config/prompts/templates/draft_execute.j2`：新增 `data_profile` 区块
- 写入 run 级 `metadata.json`

**涉及文件**

- `core/main.py` [MODIFY]
- `config/prompts/templates/draft_plan.j2` [MODIFY]
- `config/prompts/templates/draft_execute.j2` [MODIFY]

**必过测试**

- `tests/unit/test_main_bootstrap.py`
- `tests/integration/test_feature_extract_draft_pipeline.py`

**测试通过标准**

- `bootstrap_feature_extract_pes()` 返回有效的 PES 实例
- DraftPES 的 dispatch context 中存在 `task_spec`、`data_profile`、`schema`
- `draft_plan` 模板能正确渲染 `data_profile` 区块
- 工作空间存在 `metadata.json`

### 6.5 Task 5：注入 `run_id` 与 run 级元数据

**状态**: ⬜ 待实现
**目标**: 让每次运行有唯一标识，并在工作空间留下可审阅的 run 级元数据。

**任务是什么**

- 在 bootstrap 阶段生成 `run_id`
- 写入 run 级 `metadata.json`（含 `run_id`、竞赛路径、`config_snapshot`、`started_at`）
- run 结束后回写 `finished_at`

**要干什么**

- 修改 `core/main.py`：生成 `run_id`，注入两个 PES 的 `runtime_context`
- 在工作空间根目录写入 `metadata.json`
- run 结束后更新 `finished_at`

**涉及文件**

- `core/main.py` [MODIFY]
- `core/workspace.py` [MODIFY]

**必过测试**

- `tests/unit/test_main_bootstrap.py`

**测试通过标准**

- `runtime_context` 中存在 `run_id`
- 工作空间根目录存在 `metadata.json`，含 `run_id`、`started_at`
- run 结束后 `metadata.json` 含 `finished_at`

### 6.6 Task 6：建立 Tool-Write 契约并落盘真实 `solution.py`

**状态**: ⬜ 待实现
**目标**: 把 execute 阶段从“工具能力可选”推进到“`tool-write` 成功写出代码才算 execute 成功”。

**任务是什么**

- 要求 Agent 在 execute 阶段通过 tools 写出真实 `working/solution.py`
- 在 phase 结束后严格校验 `working/solution.py` 是否存在且非空
- 将该文件内容写入 `code_snapshots`

**要干什么**

- 在 `DraftPES.handle_phase_response()` 中增加 `tool-write` 契约检查
- execute 结束后从工作空间读取 `working/solution.py`，并做最小语法校验
- `solution.py` 缺失、为空或语法不合法时，明确把 solution 置为失败并记录原因
- 同步保存完整代码快照到数据库
- 明确禁止使用最终输出文本做代码恢复或兜底

**涉及文件**

- `core/pes/draft.py`
- `core/pes/base.py`
- `core/workspace.py`
- `core/database/herald_db.py`

**必过测试**

- `tests/unit/test_tool_write_contract.py`
- `tests/unit/test_database_roundtrip.py`
- `tests/integration/test_draft_pes_tool_write_flow.py`

**测试用例**

- `tests/cases/replays/draft_success_tabular_v1/turns.json`
- `tests/cases/replays/draft_missing_solution_file_v1/turns.json`
- `tests/cases/replays/draft_empty_solution_file_v1/turns.json`
- `tests/cases/replays/draft_syntax_error_v1/solution.py`

**测试通过标准**

- success case 能生成非空的 `working/solution.py`
- missing/empty `solution.py` case 会被明确标记失败，并留下可读错误原因
- `code_snapshots` 中存在与 `solution.py` 一致的完整代码内容

### 6.7 Task 7：执行 `solution.py` 并记录 `exec_logs`

**状态**: ⬜ 待实现
**目标**: 让系统拿到并持久化生成代码的首次真实执行事实，而不是停在代码落盘，也不是依赖模型自然语言自评。

**任务是什么**

- 由 Agent 在 `execute` phase 中真实运行 `working/solution.py`
- 记录首次真实运行的执行命令、stdout、stderr、exit_code、duration

**要干什么**

- 在 `DraftPES` 中接入 execute 阶段运行事实的采集与持久化
- 将 `prepared/public` 作为只读数据来源暴露给运行代码
- 统一记录执行日志到 `exec_logs`
- 明确以工件与机器输出作为事实来源，不以模型自然语言“我成功了/我更好了”作为通过依据
- 运行失败时更新 `solution.status = "failed"` 并保留执行痕迹

**约束**

- Task 7 的主目标是记录 execute 阶段的首次真实运行事实
- 不要求 Harness 仅为了验证而对同一高成本脚本强制二次完整重跑
- 若后续确实需要系统侧复跑，只能作为显式调试 / 回放能力，不能设为默认主链路

**涉及文件**

- `core/pes/draft.py`
- `core/workspace.py`
- `core/database/herald_db.py`

**必过测试**

- `tests/unit/test_execute_fact_capture.py`
- `tests/unit/test_database_roundtrip.py`
- `tests/integration/test_draft_pes_execute_fact_flow.py`

**测试用例**

- `tests/cases/replays/draft_success_tabular_v1/solution.py`
- `tests/cases/replays/draft_runtime_error_v1/solution.py`
- 真实竞赛数据：`tabular-playground-series-may-2022`

**测试通过标准**

- 成功 case 会生成至少一条 `exec_logs`
- `stdout`、`stderr`、`exit_code`、`duration_s` 都可查询
- runtime-error case 不会静默吞错，solution 状态会被明确置为 `failed`

### 6.8 Task 8：提取 `val_metric_value` 并回写 `fitness`

**状态**: ⬜ 待实现
**目标**: 建立 Herald2 当前阶段唯一的运行时主分数闭环。

**任务是什么**

- 从执行结果中提取 `val_metric_name`、`val_metric_value`、`val_metric_direction`
- 按当前约定写回 `solution.metrics` 与 `solution.fitness`

**要干什么**

- 约定 execute 成功脚本的最小输出协议
- 为 tabular case 实现 `val_metric_value` 提取
- 优先从脚本 stdout / JSON / 落盘文件中提取分数事实，而不是读取模型自然语言总结
- 按 `docs/evolve.md` 的契约，保证 `fitness` 来自 `val_metric_value`
- 将分数字段同步更新到 `solutions`

**涉及文件**

- `core/pes/draft.py`
- `core/pes/types.py`
- `core/database/herald_db.py`

**必过测试**

- `tests/unit/test_metric_extraction.py`
- `tests/unit/test_solution_model.py`
- `tests/integration/test_draft_pes_runtime_flow.py`

**测试用例**

- `tests/cases/replays/draft_success_tabular_v1/stdout.log`
- `tests/cases/replays/draft_metric_missing_v1/stdout.log`
- 真实竞赛数据：`tabular-playground-series-may-2022`
- 真实竞赛数据：`spaceship-titanic`

**测试通过标准**

- 成功 case 的 `solution.metrics` 中必须有 `val_metric_name`、`val_metric_value`、`val_metric_direction`
- `solution.fitness` 与文档约定一致，且不被 `test_score` 覆盖
- 缺失 `val_metric_value` 的 case 不能被判定为成功闭环

### 6.9 Task 9：生成并校验真实 `submission.csv`

**状态**: ⬜ 待实现
**目标**: 让 execute 阶段产出的 submission 成为可评分工件，而不是占位文件。

**任务是什么**

- 确保运行代码真实产出 `working/submission.csv`
- 基于真实 `sample_submission.csv` 做 schema 校验

**要干什么**

- 约定脚本输出 `submission.csv` 的工作目录
- 实现 submission 基本校验：文件存在、列名、列顺序、行数
- 失败时将错误写入 `exec_logs` 或 `execute_summary`

**涉及文件**

- `core/pes/draft.py`
- `core/workspace.py`
- 可能新增：`core/pes/submission.py`

**必过测试**

- `tests/unit/test_submission_validator.py`
- `tests/integration/test_draft_pes_runtime_flow.py`
- `tests/integration/test_draft_pes_real_cases.py`

**测试用例**

- `tests/cases/replays/draft_success_tabular_v1/submission.csv`
- `tests/cases/replays/draft_submission_schema_error_v1/submission.csv`
- 真实 `sample_submission.csv`：
  - `tabular-playground-series-may-2022`
  - `spaceship-titanic`

**测试通过标准**

- success case 的 `working/submission.csv` 与对应 `sample_submission.csv` schema 一致
- schema-error case 会被稳定识别并标记失败
- 通过校验的 submission 才允许进入 `test_score` 评分流程

### 6.10 Task 10：版本归档与最佳结果提升

**状态**: ⬜ 待实现
**目标**: 让成功 solution 不只存在于当下，而能被版本化保存和提升为 best。

**任务是什么**

- 调用 `Workspace.save_version()` 保存代码与 submission
- 根据 `fitness` 调用 `Workspace.promote_best()`

**要干什么**

- 在 run 成功后保存 `solution.py` 与 `submission.csv`
- 将版本目录与 `solution_id` 对齐
- 当当前 solution 的 `fitness` 高于历史 best 时，更新 `best/`
- run 结束后回写 `metadata.json` 的 `finished_at`

**涉及文件**

- `core/workspace.py`
- `core/pes/draft.py`
- `core/database/herald_db.py`

**必过测试**

- `tests/unit/test_workspace.py`
- `tests/unit/test_database_roundtrip.py`
- `tests/integration/test_draft_pes_runtime_flow.py`

**测试用例**

- `tests/cases/replays/draft_success_tabular_v1/`
- 双 run 场景：先低 `fitness`，后高 `fitness`

**测试通过标准**

- 成功 run 后会创建版本目录，并包含真实 `solution.py` 与 `submission.csv`
- `best/` 指向或复制当前最优版本
- run 结束后 `metadata.json` 中存在 `finished_at`
- 数据库中的工件路径与工作空间中的真实文件一致

### 6.11 Task 11：接入 `MLEBenchGradingHook` 获取 `test_score`

**状态**: ✅ 已实现
**目标**: 为每个有效 submission 补采外部真实性分数。

**任务是什么**

- 在 `after_run` 挂接 `MLEBenchGradingHook`
- 将 `test_score` 及相关元数据写入 `workspace/logs/grading_result.json`
- 可同步写入 DB 独立评分记录
- 不通过 `solution.metadata` / `to_prompt_payload()` 暴露给 agent

**要干什么**

- 在 bootstrap 或 hook 装配阶段注册评分 hook
- 优先从运行时上下文读取 `competition_id`、`competition_root_dir`、`public_data_dir`、`mlebench_data_dir`
- 只对 `completed` / `success` 且存在有效 `submission.csv` 的 solution 触发评分
- 评分失败时安全跳过，不影响主链路完成

**涉及文件**

- `core/main.py`
- `core/pes/base.py`
- `tests/grading.py`

**必过测试**

- `tests/unit/test_grading.py`
- `tests/integration/test_draft_pes_grading_flow.py`

**测试用例**

- 真实 submission：
  - `tabular-playground-series-may-2022`
  - `spaceship-titanic`
- 缺失 `submission.csv` case
- 无效 submission case

**测试通过标准**

- 有效 submission 能拿到 `test_score`
- `workspace/logs/grading_result.json` 中存在 `test_score`、`test_score_direction`、`test_valid_submission`、`test_medal_level`
- 同时存在 `test_competition_id`、四个阈值字段与 `test_graded_at`
- `to_prompt_payload()` 不暴露任何 `test_*` grading 字段
- `fitness` 与 `val_metric_value` 不会被评分 hook 改写

### 6.12 Task 12：补齐真实竞赛 case、真实回放 case 与 deepeval 评审

**状态**: ⬜ 待实现
**目标**: 让整个 MVP 闭环有稳定、可重复、尽量少 mock 的测试资产。

**任务是什么**

- 增加竞赛 manifest
- 增加真实运行回放目录
- 补齐 pytest 与 deepeval 用例

**要干什么**

- 建立 `tests/cases/competitions/*.yaml`
- 建立 `tests/cases/replays/*`
- 用真实回放替代当前能替代的 mock
- 为 `plan_summary`、`execute_summary`、`summarize_insight` 增加 deepeval 审阅

**涉及文件**

- `tests/cases/competitions/*`
- `tests/cases/replays/*`
- `tests/unit/*`
- `tests/integration/*`

**必过测试**

- `tests/integration/test_draft_pes_real_cases.py`
- `tests/integration/test_deepeval_draft_outputs.py`

**测试用例**

- CI 阻塞集：
  - `tabular-playground-series-may-2022`
  - `spaceship-titanic`
- 回放集：
  - `draft_success_tabular_v1`
  - `draft_missing_solution_file_v1`
  - `draft_empty_solution_file_v1`
  - `draft_syntax_error_v1`
  - `draft_runtime_error_v1`
  - `draft_submission_schema_error_v1`

**测试通过标准**

- CI 阻塞集在本地与 CI 中都能稳定运行
- 真实回放用例能覆盖当前 MVP 的成功与主要失败路径
- deepeval 只作为文本质量审阅，不替代结构化 `assert`

---

## 7. 验证计划

### 7.1 单元测试

- `tests/unit/test_feature_extract_pes.py` [NEW]
- `tests/unit/test_genome_template.py` [NEW]
- `tests/unit/test_scheduler_stages.py` [NEW]
- `tests/unit/test_main_bootstrap.py`
- `tests/unit/test_draft_pes.py`
- `tests/unit/test_prompt_manager.py`
- `tests/unit/test_task_spec_schema.py`
- `tests/unit/test_tool_write_contract.py`
- `tests/unit/test_exec_runner.py`
- `tests/unit/test_metric_extraction.py`
- `tests/unit/test_submission_validator.py`
- `tests/unit/test_solution_model.py`
- `tests/unit/test_workspace.py`
- `tests/unit/test_database_roundtrip.py`
- `tests/unit/test_grading.py`

### 7.2 集成测试

- `tests/integration/test_feature_extract_draft_pipeline.py` [NEW]
- `tests/integration/test_dispatch_flow.py`
- `tests/integration/test_scheduler_flow.py`
- `tests/integration/test_draft_pes_tool_write_flow.py`
- `tests/integration/test_draft_pes_runtime_flow.py`
- `tests/integration/test_draft_pes_grading_flow.py`
- `tests/integration/test_draft_pes_real_cases.py`
- `tests/integration/test_deepeval_draft_outputs.py`

### 7.3 功能测试

功能测试必须使用真实竞赛 case：

- `tabular-playground-series-may-2022`
- `spaceship-titanic`

功能测试的最小验收条件：

- 有 run 级 `metadata.json`
- `metadata.json` 中有 `started_at` 与 `finished_at`
- FeatureExtractPES 成功产出 `working/task_spec.json` 和 `working/data_profile.md`
- DraftPES 成功消费了 TaskSpec 和 data_profile
- 有真实 `working/solution.py`
- 有真实 `working/submission.csv`
- `solutions` 中有 FeatureExtract 和 Draft 两类 solution 记录
- 有 `llm_calls`（覆盖两个 PES 的所有 phase）
- 有 `exec_logs`
- 有 `val_metric_value`
- 有 `test_score`
- 二者被明确区分

### 7.4 deepeval

当前阶段 deepeval 只评审：

- `plan_summary`
- `execute_summary`
- `summarize_insight`

云端报告是可选项，不是硬依赖。

---

## 8. 文件结构与依赖

### 8.1 当前阶段关键目录

```text
Herald2/
├── core/
│   ├── main.py
│   ├── llm.py
│   ├── workspace.py
│   ├── scheduler/
│   ├── events/
│   ├── pes/
│   │   ├── base.py
│   │   ├── draft.py
│   │   ├── feature_extract.py    # [NEW]
│   │   ├── schema.py             # [MODIFY] 新增 load_genome_template()
│   │   ├── config.py
│   │   ├── types.py
│   │   └── ...
│   ├── prompts/
│   └── database/
├── config/
│   ├── herald.yaml
│   ├── pes/
│   │   ├── draft.yaml
│   │   └── feature_extract.yaml  # [NEW]
│   ├── genome_templates/          # [NEW]
│   │   ├── tabular.py
│   │   └── generic.py
│   ├── prompts/
│   │   ├── templates/
│   │   │   ├── draft_plan.j2
│   │   │   ├── draft_execute.j2
│   │   │   ├── draft_summarize.j2
│   │   │   ├── feature_extract_plan.j2       # [NEW]
│   │   │   ├── feature_extract_execute.j2    # [NEW]
│   │   │   └── feature_extract_summarize.j2  # [NEW]
│   │   └── prompt_spec.yaml      # [MODIFY]
│   └── agents/
├── docs/
│   ├── architecture.md
│   ├── evolve.md
│   └── TD.md
├── tests/
│   ├── unit/
│   ├── integration/
│   └── grading.py
└── plans/
```

### 8.2 Python 依赖

| 依赖 | 用途 |
|---|---|
| `PyYAML` | 配置加载 |
| `pluggy` | Hook 系统 |
| `claude_agent_sdk` | LLM 执行 |
| `jinja2` | Prompt 模板渲染 |
| `sqlite3` | 本地持久化 |
| `mlebench` | `test_score` 获取 |
| `pytest` | 单元/集成/功能测试 |
| `deepeval` | LLM 输出质量评估 |

---

## 9. 一句话结论

当前阶段的技术方案有两条主线：

1. **实现 `FeatureExtractPES` + GenomeSchema 模板体系**：让系统能动态分析竞赛数据、生成 TaskSpec、选择任务类型对应的代码模板，为 DraftPES 提供结构化的任务规格和数据概况
2. **把 `DraftPES` 从”能调用三次模型”的骨架，推进到”能生成真实代码、产出真实 submission、拿到 `val_metric_value` 与 `test_score`、并把全过程记录到 DB/日志/工件中”的最小可演化闭环**

一句话：**先让系统看懂数据（FeatureExtractPES），再让系统写对代码（DraftPES），最终让系统可追踪地演化（Harness）。**
