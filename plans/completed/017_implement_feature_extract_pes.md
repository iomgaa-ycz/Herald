# 017: 实现 FeatureExtractPES

## 元信息
- 状态: in_progress
- 创建: 2026-03-28
- 对应 TD: Task 1（§6.1）

## 1. 摘要

实现前置数据分析 PES (`FeatureExtractPES`)，继承 `BasePES`，走完 plan/execute/summarize 三阶段。execute 阶段让 LLM Agent 用 Bash 工具读取竞赛数据，输出结构化 TaskSpec + data_profile + genome_template 选择。产出持久化到 workspace 并通过 `TaskCompleteEvent.output_context` 传递给下游。

## 2. 审查点

1. **execute 阶段 JSON 解析策略**: 从 `response.result` 中提取最后一个 JSON code block，解析失败则标记 solution 为 failed
2. **TaskCompleteEvent.output_context**: 当前 `TaskCompleteEvent` 缺少 `output_context` 字段——本任务只在 FeatureExtractPES 内部使用 dict 传递，**不修改** `TaskCompleteEvent`（Task 3 负责）
3. **data_profile 持久化**: 从 LLM 输出的 `data_profile` 字段直接写入，不做额外格式化

## 3. 流程图 / 伪代码

```
FeatureExtractPES.run(agent_profile, generation=0)
  │
  ├── create_solution(operation="feature_extract")
  │     └── persist to DB
  │
  ├── plan phase:
  │     ├── build_prompt_context() → 注入 competition_dir, solution
  │     ├── render "feature_extract_plan.j2"
  │     ├── call_phase_model(max_turns=1, allowed_tools=[])
  │     └── handle_phase_response("plan"):
  │           └── solution.plan_summary = response_text
  │
  ├── execute phase:
  │     ├── build_prompt_context() → 注入 competition_dir, workspace, solution
  │     ├── build_phase_model_options() → cwd=workspace.working_dir
  │     ├── render "feature_extract_execute.j2"
  │     ├── call_phase_model(max_turns=12, allowed_tools=["Bash","Read","Glob","Grep"])
  │     └── handle_phase_response("execute"):
  │           ├── _extract_response_text(response) → raw text
  │           ├── _parse_structured_output(raw_text) → dict with task_spec/data_profile/genome_template
  │           ├── 构造 TaskSpec dataclass 并序列化到 workspace/working/task_spec.json
  │           ├── 写入 workspace/working/data_profile.md
  │           ├── solution.metadata["genome_template"] = "tabular" | "generic"
  │           ├── solution.execute_summary = raw_text (截断)
  │           └── _attach_workspace_artifacts(solution)
  │
  └── summarize phase:
        ├── render "feature_extract_summarize.j2"
        ├── call_phase_model(max_turns=1, allowed_tools=[])
        └── handle_phase_response("summarize"):
              ├── solution.summarize_insight = response_text
              ├── solution.status = "completed"
              └── emit TaskCompleteEvent(task_name="feature_extract", status="completed")
```

**与现有代码嵌合**:
- `BasePES.__init__` 自动注册到 `PESRegistry`，`TaskDispatcher.handle_dispatch` 通过 `get_by_base_name("feature_extract")` 查找实例——配置 `name: feature_extract` 即可
- `BasePES._run_phase` 已封装 prompt 渲染 → 模型调用 → handle_phase_response → persist 的完整流程，FeatureExtractPES 只需实现 `handle_phase_response` 和 `build_phase_model_options`
- `PromptManager.build_prompt(operation="feature_extract", phase="plan")` 自动查找 `feature_extract_plan.j2`

## 4. 拟议变更

### 4.1 新建文件

| 文件 | 标识 | 说明 |
|------|------|------|
| `core/pes/feature_extract.py` | [NEW] | FeatureExtractPES 类 |
| `config/pes/feature_extract.yaml` | [NEW] | PES 配置 |
| `config/prompts/templates/feature_extract_plan.j2` | [NEW] | Plan 阶段 Prompt |
| `config/prompts/templates/feature_extract_execute.j2` | [NEW] | Execute 阶段 Prompt |
| `config/prompts/templates/feature_extract_summarize.j2` | [NEW] | Summarize 阶段 Prompt |
| `tests/unit/test_feature_extract_pes.py` | [NEW] | 单元测试 |

### 4.2 修改文件

| 文件 | 标识 | 变更 |
|------|------|------|
| `config/prompts/prompt_spec.yaml` | [MODIFY] | 添加 `feature_extract_plan`/`feature_extract_execute`/`feature_extract_summarize` 三个模板规格 |

### 4.3 各文件详细设计

#### 4.3.1 `core/pes/feature_extract.py` [NEW]

```python
class FeatureExtractPES(BasePES):
    """前置数据分析 PES，每竞赛运行一次。

    职责：分析竞赛数据 → 生成 TaskSpec + data_profile + 选择 GenomeSchema 模板。
    """

    VALID_GENOME_TEMPLATES = ("tabular", "generic")

    def build_phase_model_options(self, phase, solution, parent_solution) -> dict:
        """execute phase 设置 cwd 为 workspace.working_dir。"""
        # 仅 execute 阶段需要 cwd，plan/summarize 不需要工具
        if phase != "execute" or self.workspace is None:
            return {}
        working_dir = getattr(self.workspace, "working_dir", None)
        if working_dir is None:
            return {}
        return {"cwd": str(working_dir)}

    async def handle_phase_response(self, phase, solution, response, parent_solution) -> dict:
        """消费各阶段响应。

        plan:     写入 plan_summary
        execute:  解析结构化输出 → 持久化 TaskSpec + data_profile
        summarize: 写入 summarize_insight → 标记完成 → 发事件
        """

    def _extract_response_text(self, response: object) -> str:
        """提取模型响应文本。"""

    def _parse_structured_output(self, text: str) -> dict[str, Any]:
        """从 LLM 输出提取最后一个 JSON code block。

        期望 JSON 包含: task_spec, data_profile, genome_template
        解析失败抛出 ValueError。
        """

    def _persist_task_spec(self, task_spec_dict: dict) -> None:
        """序列化 TaskSpec 到 workspace/working/task_spec.json。"""

    def _persist_data_profile(self, data_profile: str) -> None:
        """写入 workspace/working/data_profile.md。"""

    def _attach_workspace_artifacts(self, solution: PESSolution) -> None:
        """挂载工件路径到 solution。"""
```

关键实现细节：

- `_parse_structured_output`: 用正则 `r'```json\s*\n(.*?)\n```'` 匹配，取最后一个 match，`json.loads` 解析
- execute 阶段解析失败时，调用 `self.handle_phase_failure()` 标记 solution 为 failed，附带错误原因
- `genome_template` 不在 `VALID_GENOME_TEMPLATES` 中时，降级为 `"generic"`
- `solution.metadata` 存储: `genome_template`, `schema_task_type` (= task_spec.task_type)

#### 4.3.2 `config/pes/feature_extract.yaml` [NEW]

```yaml
name: feature_extract
operation: feature_extract
solution_file_name: data_profile.md
submission_file_name: null

phases:
  plan:
    template_name: null
    tool_names: []
    max_retries: 1
    allowed_tools: []
    max_turns: 1
  execute:
    template_name: null
    tool_names: []
    max_retries: 1
    allowed_tools: ["Bash", "Read", "Glob", "Grep"]
    max_turns: 12
  summarize:
    template_name: null
    tool_names: []
    max_retries: 1
    allowed_tools: []
    max_turns: 1
```

#### 4.3.3 Prompt 模板

**`feature_extract_plan.j2`**:
- 输入 context: `solution`, `competition_dir`（from runtime_context）
- 引导 LLM: "你需要分析一个 Kaggle 竞赛数据集。请规划数据探索步骤。"
- 要求输出: 数据探索策略（分析哪些文件、关注什么字段、如何判断任务类型）

**`feature_extract_execute.j2`**:
- 输入 context: `solution`, `workspace`, `competition_dir`
- 引导 LLM: 用 Bash/Read 工具读取 `data/` 目录中的文件
- 具体操作指引:
  1. 读取 description.md 提取任务目标和评估指标
  2. ls data/ 了解文件结构
  3. head -20 train.csv 查看数据样本
  4. python -c "import pandas as pd; ..." 获取数据概况
  5. 分析 sample_submission.csv 了解输出格式
- 最终输出要求: 一个 JSON code block 包含:
  ```json
  {
    "task_spec": {"task_type": "...", "competition_name": "...", "objective": "...", "metric_name": "...", "metric_direction": "..."},
    "data_profile": "数据概况报告文本",
    "genome_template": "tabular"
  }
  ```

**`feature_extract_summarize.j2`**:
- 输入 context: `solution`, `execution_log`
- 引导 LLM: 总结数据特征、关键发现、建模建议
- 输出格式: 数据特征总结 / 关键发现 / 建模建议

#### 4.3.4 `config/prompts/prompt_spec.yaml` [MODIFY]

追加三个模板规格:

```yaml
  feature_extract_plan:
    required_context: ["solution"]
    static_fragments: ["system_context"]
    artifacts: []
  feature_extract_execute:
    required_context: ["solution"]
    static_fragments: ["system_context"]
    artifacts: []
  feature_extract_summarize:
    required_context: ["solution", "execution_log"]
    static_fragments: ["system_context"]
    artifacts: []
```

#### 4.3.5 `tests/unit/test_feature_extract_pes.py` [NEW]

测试用例清单:

| # | 测试函数 | 验证目标 |
|---|---------|---------|
| 1 | `test_feature_extract_yaml_config_loads` | 加载 `feature_extract.yaml` 验证字段 |
| 2 | `test_handle_plan_phase` | plan 阶段更新 plan_summary |
| 3 | `test_handle_execute_phase_parses_json` | execute 阶段从 JSON code block 解析 TaskSpec |
| 4 | `test_handle_execute_phase_persists_files` | task_spec.json 和 data_profile.md 写入 workspace |
| 5 | `test_handle_summarize_emits_complete` | summarize 设置 completed 并发事件 |
| 6 | `test_run_full_cycle` | DummyLLM + 真实 PromptManager 跑完三阶段 |
| 7 | `test_parse_structured_output_extracts_json` | JSON 解析正确 |
| 8 | `test_parse_structured_output_fails_on_no_json` | 无 JSON 时抛异常 |
| 9 | `test_genome_template_defaults_to_generic` | 无效 genome_template 降级为 "generic" |

测试基础设施: 复用 `test_draft_pes.py` 中的 `DummyResponse`, `DummyLLM`, `DummyWorkspace` 模式

## 5. 验证计划

### 5.1 单元测试
```bash
conda activate herald && python -m pytest tests/unit/test_feature_extract_pes.py -v
```

### 5.2 回归验证
```bash
python -m pytest tests/unit/test_draft_pes.py -v
```

### 5.3 代码质量
```bash
ruff check core/pes/feature_extract.py tests/unit/test_feature_extract_pes.py --fix
ruff format core/pes/feature_extract.py tests/unit/test_feature_extract_pes.py
```

### 5.4 冒烟验证
```bash
python -c "from core.prompts.manager import PromptManager; from pathlib import Path; pm = PromptManager(Path('config/prompts/templates'), Path('config/prompts/fragments'), Path('config/prompts/prompt_spec.yaml')); print(pm.get_template_spec('feature_extract', 'plan'))"
```

### 5.5 通过标准（TD §6.1）
- [ ] `FeatureExtractPES.run()` 能完整执行三阶段
- [ ] execute 阶段产出的 TaskSpec JSON 可解析为 `TaskSpec` dataclass
- [ ] `data_profile.md` 非空
- [ ] `genome_template` 值合法（`"tabular"` 或 `"generic"`）
