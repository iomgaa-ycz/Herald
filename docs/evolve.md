# Herald2 Evolve 规范

> **版本**: v0.1
> **更新**: 2026-03-29
> **定位**: Herald2 的记录、观测、回放、评测与测试规范

---

## 1. 文档定位

`docs/evolve.md` 是 Herald2 在 MVP 阶段的 Harness 基线文档。

它不讨论抽象的“进化算法愿景”，而是回答四个工程问题：

1. 运行过程中哪些内容必须被记录
2. 这些记录分别以什么形式存在，以及如何被观测
3. 测试用例资产如何组织，特别是如何使用真实竞赛数据与真实运行回放
4. pytest、deepeval 与 MLE-Bench 评分如何接入

当前阶段不再维护独立的 `docs/test.md` 作为并行规范文档。
如果后续确实需要测试命令手册，`docs/test.md` 只能作为一个很薄的入口页，不能和本文档重复承载规范。

---

## 2. 当前阶段边界

Herald2 当前的阶段性目标是：

**单进程、单任务类型、串行驱动的 `DraftPES` MVP 闭环。**

因此本文档只约束当前阶段真正需要的 Harness 能力：

- `main.py -> Scheduler -> TaskDispatcher -> FeatureExtractPES.run() -> DraftPES.run()` 主链路
- `FeatureExtractPES` 的数据分析、TaskSpec 生成、GenomeSchema 模板选择
- `DraftPES` 的 `Plan / Execute / Summarize` 三阶段的记录与回放
- `solution.py`、`submission.csv`、执行日志与评分结果的落盘
- 基于真实数据和真实运行结果的测试体系

当前阶段明确不做：

- 分布式调度
- 多岛模型
- 多任务并行
- 以 `test_score` 驱动在线调度

### 2.1 “不依赖模型自述”的精确定义

Herald2 当前阶段强调“不依赖模型自述”，但这里的含义必须收紧，否则会误伤真正有价值的执行事实。

这里**不可信**的是：

- 模型在自然语言里声称“我成功了”
- 模型在自然语言里判断“这次结果更好”
- 模型在自然语言里自行宣布“通过 / 失败”

这里**可信**的是模型在 execute 阶段真实产出的机器事实：

- `working/solution.py`
- `working/submission.csv`
- Bash / Python 真实运行产生的 `stdout`、`stderr`、`exit_code`
- 脚本自己打印、写入 JSON 或落盘文件中的 `val_metric_value` / `fitness`

因此，Harness 的职责是：

- 记录和持久化这些执行事实
- 基于这些事实做最小一致性校验
- 避免把模型自然语言总结当作 pass/fail 或优劣判断依据

当前阶段**不要求** Harness 仅为了证明“不是模型自述”，就对已经昂贵的竞赛脚本再做一次强制全量重跑。对 Kaggle / mle-bench 这类高成本任务，优先复用 execute phase 首次真实运行产生的事实。

---

## 3. 分数语义契约

Herald2 必须强制区分两类分数。

| 字段 | 含义 | 来源 | 用途 | 是否参与调度 |
|---|---|---|---|---|
| `val_metric_value` | 当前方案在本地训练集切分出的验证集上的分数 | 脚本真实运行产物（stdout / JSON / 文件） | 方案比较、局部优化、fitness 计算 | 是 |
| `fitness` | 系统内部用于选择与进化的统一分数 | 由运行产出的 `val_metric_value` 归一化后得到 | 调度、选择、进化压力 | 是 |
| `test_score` | `submission.csv` 交给 MLE-Bench / Kaggle 官方评分后的分数 | 外部评分系统 | 评估系统真实可用性、检测过拟合、实验分析 | 否 |

硬规则如下：

1. `fitness` 默认来自 `val_metric_value`
2. `test_score` 绝不能直接作为在线调度依据
3. 每个成功生成 `submission.csv` 的 solution，都应尽可能补采 `test_score`
4. 报告中必须同时展示 `val_metric_value` 与 `test_score`
5. 当 `val_metric_value` 高、`test_score` 低时，应视为可疑过拟合信号
6. 自然语言总结中的“分数很好 / 方案更优”不能直接覆盖脚本真实运行产出的分数字段

推荐字段命名：

- `val_metric_name`
- `val_metric_value`
- `val_metric_direction`
- `fitness`
- `test_score`
- `test_score_direction`
- `test_valid_submission`
- `test_medal_level`

---

## 4. 记录与观测契约

### 4.1 记录单元

Herald2 必须把一次完整运行拆成以下记录单元：

- Run：一次 `main.py` 启动
- Task：一次调度器发出的任务
- Solution：一次完整 PES 迭代产物
- Phase：`plan` / `execute` / `summarize`
- Artifact：代码、submission、报告、日志
- Evaluation：本地验证分数与外部 test score

### 4.2 记录内容与形式

| 对象 | 必须记录 | 记录形式 | 观测方式 |
|---|---|---|---|
| Run | `run_id`、配置快照、竞赛目录、工作空间目录、启动/结束时间 | 日志 + 元数据文件 | 读 `logs/`、看 `metadata.json` |
| Scheduler / Event | dispatch / execute / complete 的时间、状态、solution_id、pes_id、task_stages 进度 | 日志 | `tail -f` 实时观察 |
| FeatureExtract Plan | 竞赛描述分析策略、数据探索计划 | `llm_calls` + 日志 | 查 DB / 读日志 |
| FeatureExtract Execute | 数据探索命令与输出、TaskSpec JSON、data_profile 报告、GenomeSchema 模板选择 | `llm_calls` + `working/task_spec.json` + `working/data_profile.md` | 查 DB / 看 `working/` |
| FeatureExtract Summarize | 数据特征总结、关键发现、建模建议 | `llm_calls` + 日志 | 查 DB / 读日志 |
| Draft Plan Phase | prompt、agent profile、模型、tokens、latency、原始输出、plan 摘要 | `llm_calls` + 日志 | 查 DB / 读日志 |
| Draft Execute Phase | 原始输出、tool 调用轨迹、`solution.py`、契约检查结果、首次真实运行的执行命令、stdout、stderr、exit code、duration、`val_metric_value`、`submission.csv` 路径 | `llm_calls` + `contract_checks` + `code_snapshots` + `exec_logs` + 文件工件 | 查 DB / 看 `working/` |
| Draft Summarize Phase | summarize prompt、原始输出、最终 insight、下轮建议 | `llm_calls` + 报告文件 | 查 DB / 读报告 |
| 外部评分 | `test_score`、方向、奖牌、阈值、是否有效提交 | 独立评分结果 + 日志 + solution metadata | 看评分报告 / 查结果 |

### 4.3 记录通道职责

每种记录通道承担不同职责，不允许混用。

| 通道 | 角色 |
|---|---|
| 日志文件 | 实时观察、按时间顺序追问题 |
| SQLite / DB | 结构化事实、可查询、可聚合 |
| 工作空间工件 | 可回放、可人工检查的真实产物 |
| Markdown / JSON 报告 | 面向人类审阅的结论层 |

约束如下：

- **DB 存事实**
- **日志存过程**
- **文件存产物**
- **报告存结论**

补充约束：

- `exec_logs` 记录的是 execute phase 的真实运行事实，优先来自首次运行
- 高成本脚本不应仅为“去自述化”而被 Harness 强制重复全量执行
- 自然语言总结只能辅助审阅，不能单独充当通过判定或分数真相来源

### 4.4 当前阶段最少必须落地的记录

在 MVP 阶段，以下记录项必须先接通：

- `solutions`（含 FeatureExtractPES 和 DraftPES 两类 solution）
- `llm_calls`
- `code_snapshots`
- `exec_logs`
- `working/task_spec.json`（FeatureExtractPES 产出）
- `working/data_profile.md`（FeatureExtractPES 产出）
- `working/solution.py`
- `working/submission.csv`
- `val_metric_value`
- `test_score`

如果这些内容没有完整落地，Herald2 就还不具备可演化的 Harness 基础。

---

## 5. 测试用例资产策略

### 5.1 原则

测试资产优先级如下：

1. 真实竞赛数据
2. 真实运行回放
3. 最小人工构造样例

原则上应避免无语义的 mock。
若必须替代外部 LLM，则只能使用**基于真实历史运行结果的回放式测试资产**。

#### 5.1.1 输入来源分层定义（L1 / L2 / L3）

Herald2 的测试输入按**可信度**分为三层。每层有明确的适用边界，禁止越级使用。

| 层级 | 名称 | 定义 | 前置条件 | 适用范围 |
|---|---|---|---|---|
| **L1** | 真实竞赛 + 真实 LLM | 对真实竞赛数据目录执行 `python core/main.py`，由真实 LLM 驱动全链路 | `HERALD_TEST_DATA_ROOT` 可用 + `claude_agent_sdk` 可用 | 功能测试（evolve.md §6.4） |
| **L2** | 真实运行回放 | 从一次 **L1 运行**的产物中截取的 `turns.json`、`solution.py`、`stdout.log` 等文件，通过 `ReplayLLM` 回放 | L1 至少成功运行过一次，截取的资产已存入 `tests/cases/replays/` | 单元测试 + 集成测试（替代 LLM 调用） |
| **L3** | 最小人工构造 | 手工编写的最小输入数据（字典、字符串、配置文件） | 无 | **仅限**纯逻辑验证：数据结构映射、配置解析、类型构造、DB 读写一致性 |

**硬约束：**

1. **L2 必须从 L1 截取。** 如果 `tests/cases/replays/` 中的文件不是从真实运行中截取，而是手工编写的，那它本质上是 L3 冒充 L2——系统会误以为自己验证了"对真实运行结果的处理"，实际上没有。
2. **L3 不得用于验证执行事实处理逻辑。** 以下场景必须使用 L2 或更高层级的输入：
   - tool trace 解析（`_extract_execute_fact`）
   - val_metric 提取（`_extract_val_metrics`）
   - submission 格式校验
   - code snapshot 持久化
   - exec_logs 写入
3. **L1 运行的副产物应自动归档为 L2 资产。** 建议在 `conftest.py` 或 CI 中加入截取逻辑，确保 L2 资产随 L1 运行持续更新。

**反模式示例：**

```python
# BAD: L3 冒充 L2
# turns.json 中 stdout 为手写的 "training done\nsubmission written"
# solution.py 是空壳 solve() 函数
# metrics.json 是手写的 {"val_metric_value": 0.8123}
# 这些数据没有经过真实 LLM + 真实脚本运行，不能验证系统对真实产物的处理能力

# GOOD: 真正的 L2
# turns.json 截取自一次真实 main.py 运行的 llm_calls 表
# solution.py 是 Agent 真实生成的代码（含 pandas import、模型训练等）
# stdout.log 含真实训练日志、warning、metric 输出
# metrics.json 由真实脚本计算产出
```

**L2 截取规范：**

从一次 L1 运行中截取回放资产时，每个回放目录应包含：

| 文件 | 来源 | 说明 |
|---|---|---|
| `input.json` | 运行配置 | `competition_id`、`task_type`、`metric_name` |
| `turns.json` | `llm_calls` 表中 execute phase 的完整记录 | 保留所有 tool_call 与 result |
| `solution.py` | `working/solution.py` 副本 | Agent 真实写出的代码 |
| `stdout.log` | turns 中 Bash tool_call result 的 stdout | 真实脚本输出 |
| `stderr.log` | 同上的 stderr | 含 warning / traceback |
| `metrics.json` | `working/metrics.json` 副本（如存在） | 脚本产出的结构化指标 |
| `submission.csv` | `working/submission.csv` 副本（如存在） | 脚本产出的提交文件 |
| `expected.json` | 人工标注 | 该回放应通过的断言值 |

详细测试矩阵见 `docs/test_matrix.md`。

### 5.2 真实竞赛数据用例

竞赛数据不直接复制进仓库，统一通过本地 MLE-Bench 数据目录引用。

建议使用环境变量：

```bash
HERALD_TEST_DATA_ROOT=~/.cache/mle-bench/data
```

测试用例清单建议放在：

```text
tests/cases/competitions/
  tabular-playground-series-may-2022.yaml
  spaceship-titanic.yaml
  histopathologic-cancer-detection.yaml
  chaii-hindi-and-tamil-question-answering.yaml
```

每个 manifest 至少包含：

- `competition_id`
- `task_type`
- `metric_name`
- `metric_direction`
- `relative_root`
- `required_public_files`

### 5.3 当前阶段的竞赛测试矩阵

| 分组 | 竞赛 | 用途 |
|---|---|---|
| CI 阻塞集 | `tabular-playground-series-may-2022` | MVP 主航道，标准 tabular + AUC |
| CI 阻塞集 | `spaceship-titanic` | tabular 补充集，测试不同指标与 submission 语义 |
| 扩展观测集 | `histopathologic-cancer-detection` | 预留 image classification / 文件布局验证 |
| 扩展观测集 | `chaii-hindi-and-tamil-question-answering` | 预留 UTF-8 / NLP / 长文本验证 |

当前 CI 只阻塞前两项。
扩展观测集用于后续任务类型扩展，不进入当前硬门禁。

### 5.4 真实运行回放用例

真实运行回放用例是替代 mock 的标准测试资产，目录建议为：

```text
tests/cases/replays/
  draft_success_tabular_v1/
    input.json
    plan.txt
    turns.json
    solution.py
    stdout.log
    stderr.log
    submission.csv
    expected.json
  draft_missing_solution_file_v1/
  draft_empty_solution_file_v1/
  draft_syntax_error_v1/
  draft_submission_schema_error_v1/
  draft_runtime_error_v1/
```

回放用例的来源必须是：

- 真正的 `main.py` 运行结果
- 或者真正的 phase 输出与执行结果快照

当前阶段必须至少积累以下回放类型：

**FeatureExtractPES 回放：**

- 成功识别 tabular 任务并生成完整 TaskSpec 的 case
- 成功生成 data_profile 的 case
- 竞赛描述缺失关键信息的降级 case

**DraftPES 回放：**

- 成功生成可评分 submission 的 case
- 未写出 `solution.py` 的 case
- 写出了空 `solution.py` 的 case
- Python 语法错误 case
- 运行时报错 case
- submission schema 错误 case

---

## 6. 测试体系

### 6.1 单元测试

单元测试使用 `pytest + assert`，要求：

- 尽量不使用 mock
- 必须使用真实数据 manifest、真实回放文本、真实临时 workspace、真实 sqlite
- 如需替代 LLM，只允许使用文件回放式 client

当前阶段需要的单元测试包括：

- `Workspace` 能正确链接 `prepared/public`
- `FeatureExtractPES` 能从 execute 输出中解析 TaskSpec JSON 和 data_profile
- `GenomeSchema` 模板加载能根据 task_type 返回正确的模板（tabular / generic）
- `TaskSpec` 能从真实 `description.md` 抽取任务目标与 metric
- `PromptManager` 能对真实 `task_spec/schema/workspace/data_profile` 正常渲染
- `tool-write` 契约检查器能基于真实 workspace 判断 `solution.py` 是否被成功写出
- execute 事实采集器能从真实 tool trace / stdout / 文件中恢复首次运行事实
- submission 校验器能对真实 `sample_submission.csv` 做格式判定
- `solutions / llm_calls / exec_logs / code_snapshots` 能正确 roundtrip
- `val_metric_value` 解析器能从脚本 stdout 或结构化结果中抽取分数
- `test_score` 评分工具能对真实 `submission.csv` 发起评分并格式化结果

### 6.2 模块测试

模块测试验证单个 phase 的业务完整性，仍以真实用例为输入。

当前阶段的模块测试包括：

- `FeatureExtractPES.execute` 的输出是否包含有效 TaskSpec 和 data_profile
- `FeatureExtractPES` 是否能正确选择 GenomeSchema 模板（tabular vs generic）
- `DraftPES.plan` 的输出是否覆盖任务目标与约束（含 data_profile 消费验证）
- `DraftPES.execute` 是否能真正通过 tools 写出 `solution.py` 并记录首次运行事实
- `DraftPES.summarize` 的结论是否忠实于执行日志

### 6.3 集成测试

集成测试验证链路是否打通。

当前阶段的核心集成测试包括：

- `main.py -> Scheduler(task_stages) -> FeatureExtractPES.run() -> DraftPES.run()` 全链路
- `FeatureExtractPES` 产出的 TaskSpec / data_profile 是否成功注入 DraftPES context
- 一次 run 结束后 DB、workspace、日志、submission 是否同步存在
- 成功执行后能否补采 `test_score`

### 6.4 功能测试

功能测试验证 Herald2 是否完成了“从竞赛输入到可评测 submission”的最小闭环。

当前阶段的功能测试必须回答：

1. 是否生成了真实 `solution.py`
2. 是否生成了真实 `submission.csv`
3. 是否拿到了 `val_metric_value`
4. 是否拿到了 `test_score`
5. 二者是否被明确区分并持久化

---

## 7. deepeval 使用策略

### 7.1 当前阶段

当前仓库尚未接入 deepeval tracing，因此本阶段只把 deepeval 用在**无法纯靠 assert 判定的 LLM 输出质量**上。

适用对象：

- `plan_summary`
- `execute_summary`
- `summarize_insight`
- 基于日志的人工审阅型结论

建议评测方式：

- 基于真实竞赛描述与回放日志构造 goldens
- 用 deepeval 对文本进行 rubric-based 评估
- 结果输出到本地报告

### 7.2 后续阶段

当 phase / tool trace 接好后，再接入 agentic metrics：

- `TaskCompletionMetric`
- `ToolCorrectnessMetric`
- 其他基于 trace 的评测

### 7.3 云端报告策略

deepeval 云端报告是**可选项**。

当前阶段的硬要求只有两条：

- 本地可运行
- 本地有可审阅报告

如果后续团队需要更方便的审阅与历史对比，再开启云端汇总。

---

## 8. MLE-Bench test score 获取链路

### 8.1 基本要求

Herald2 必须提供一个独立的 `test_score` 获取链路，用于对 `submission.csv` 进行外部评分。

该链路的职责只有两个：

1. 调用 MLE-Bench 评分接口拿到 `test_score`
2. 将结果与当前 solution 关联并持久化

它不负责：

- 驱动在线调度
- 覆盖 `fitness`
- 替代本地 `val_metric_value`

### 8.2 触发时机

推荐触发时机：

- `after_run`

原因：

- 当前 hook 体系已有 `after_run`
- 此时 `solution.py`、`submission.csv`、`summarize` 已经结束
- 最适合在闭环末尾补采外部 `test_score`

### 8.3 路径约定

当前阶段不应依赖模糊的路径推断。

运行时上下文推荐显式传：

- `competition_id`
- `competition_root_dir`
- `public_data_dir`
- `mlebench_data_dir`

路径推断只能作为 fallback，而不是主方案。

### 8.4 当前实现约定

当前仓库中 `DraftPES` 的完成态是 `completed`。

因此评分链路必须接受：

- `completed`
- `success`

而不能只检查 `success`。

### 8.5 最少持久化字段

每次成功评分后，至少要留下：

- `solution_id`
- `competition_id`
- `test_score`
- `test_score_direction`
- `test_valid_submission`
- `test_medal_level`
- `gold_threshold`
- `silver_threshold`
- `bronze_threshold`
- `median_threshold`
- `graded_at`

---

## 9. 一句话结论

Herald2 的 `evolve` 基础不是“更复杂的搜索策略”，而是：

**先把由脚本真实运行产生的 `val_metric_value`、`test_score`、代码工件、执行日志、评分结果和真实测试用例资产全部沉淀下来，再在这个可回放、可观测、可评测的 Harness 上继续演化。**
