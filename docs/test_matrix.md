# Herald2 测试矩阵

> **版本**: v0.1
> **更新**: 2026-03-29
> **定位**: 覆盖 TD.md 所有 Task 的完整测试清单，与 `docs/evolve.md` §5 配合使用

---

## 1. 文档定位

本文档是 Herald2 测试体系的**实施级参考**，回答：

- 每个测试验证什么
- 输入从哪来（L1 / L2 / L3）
- 预期输出是什么
- 对应 TD.md 的哪个 Task

输入来源分层定义见 `docs/evolve.md` §5.1.1。

---

## 2. 测试文件存在性总览

基于 TD.md §7.1 / §7.2 列出的所有测试文件：

### 2.1 单元测试

| 测试文件 | TD.md Task | 状态 | 说明 |
|---|---|---|---|
| `tests/unit/test_feature_extract_pes.py` | Task 1 | 已存在 | FeatureExtractPES 三阶段 |
| `tests/unit/test_genome_template.py` | Task 2 | 已存在 | 模板加载与 slot 验证 |
| `tests/unit/test_scheduler_stages.py` | Task 3 | 已存在 | task_stages 调度顺序 |
| `tests/unit/test_main_bootstrap.py` | Task 4, 5 | 已存在 | bootstrap 装配与 run_id 注入 |
| `tests/unit/test_draft_pes.py` | Task 4, 6 | 已存在 | DraftPES 接口层 |
| `tests/unit/test_prompt_manager.py` | Task 4 | 已存在 | Prompt 模板渲染 |
| `tests/unit/test_tool_write_contract.py` | Task 6 | 已存在 | tool-write 契约校验 |
| `tests/unit/test_execute_fact_capture.py` | Task 7 | 已存在 | 执行事实采集 |
| `tests/unit/test_metric_extraction.py` | Task 8 | 已存在 | val_metric 提取 |
| `tests/unit/test_solution_model.py` | Task 8 | 已存在 | PESSolution 指标映射 |
| `tests/unit/test_database_roundtrip.py` | Task 6, 7, 10 | 已存在 | DB 读写一致性 |
| `tests/unit/test_agent_registry.py` | — | 已存在 | Agent profile 加载 |
| `tests/unit/test_task_spec_schema.py` | Task 1 | **待新建** | TaskSpec / GenomeSchema 从真实竞赛构造 |
| `tests/unit/test_exec_runner.py` | Task 7 | **待新建** | 执行事实采集的边界 case |
| `tests/unit/test_submission_validator.py` | Task 9 | **待新建** | submission.csv 格式校验 |
| `tests/unit/test_workspace.py` | Task 10 | **待新建** | save_version / promote_best |
| `tests/unit/test_grading.py` | Task 11 | **待新建** | GradingConfig / GradingResult 单元逻辑 |

### 2.2 集成测试

| 测试文件 | TD.md Task | 状态 | 说明 |
|---|---|---|---|
| `tests/integration/test_dispatch_flow.py` | Task 3 | 已存在 | 事件流到达 PES |
| `tests/integration/test_scheduler_flow.py` | Task 3 | 已存在 | Scheduler 调度闭环 |
| `tests/integration/test_feature_extract_draft_pipeline.py` | Task 4 | 已存在 | 双 PES 流水线上下文传递 |
| `tests/integration/test_draft_pes_tool_write_flow.py` | Task 6 | 已存在 | 成功 / 失败回放经 Scheduler 闭环 |
| `tests/integration/test_draft_pes_execute_fact_flow.py` | Task 7 | 已存在 | exec_logs 落库 |
| `tests/integration/test_draft_pes_runtime_flow.py` | Task 8 | 已存在 | fitness 回写 DB |
| `tests/integration/test_draft_pes_grading_flow.py` | Task 11 | **待新建** | test_score 补采集成 |
| `tests/integration/test_draft_pes_real_cases.py` | Task 12 | **待新建** | 真实竞赛端到端 |
| `tests/integration/test_deepeval_draft_outputs.py` | Task 12 | **待新建** | LLM 输出文本质量 |

---

## 3. L3 类测试（纯逻辑，人工构造输入合理）

这些测试验证**数据结构映射、配置解析、纯函数计算**，不涉及"对真实运行结果的处理"。

### 3.1 已有 L3 测试

| 编号 | 测试文件::用例 | 验证什么 | 输入 | 预期输出 | TD Task |
|---|---|---|---|---|---|
| L3-1 | `test_solution_model::test_to_record_maps_val_metric_fields` | `to_record()` 字段映射 | 手工 `PESSolution`（带 metrics） | `record["metric_name"]=="auc"`, `fitness==0.8123` | 8 |
| L3-2 | `test_solution_model::test_to_prompt_payload_exposes_aliases` | `to_prompt_payload()` 新旧键共存 | 同上 | `payload["metrics"]` 同时含 `val_metric_*` 和 `metric_*` | 8 |
| L3-3 | `test_genome_template::test_load_tabular` | tabular 模板加载 | 真实 `config/genome_templates/tabular.py` | GenomeSchema 含 4 个 slot + 非空 `template_content` | 2 |
| L3-4 | `test_genome_template::test_load_unknown_fallback` | 未知类型降级 generic | `task_type="unknown_xyz"` | 返回 generic 模板 | 2 |
| L3-5 | `test_prompt_manager::*` | Prompt 模板渲染 | 真实模板文件 + 手工 context | 渲染 prompt 含预期关键词 | 4 |
| L3-6 | `test_draft_pes::test_schema_types_can_be_constructed` | 类型构造 | 手工参数 | 实例字段正确 | — |
| L3-7 | `test_draft_pes::test_load_draft_yaml_config` | YAML 加载 | 真实 `config/pes/draft.yaml` | 字段值符合预期 | — |
| L3-8 | `test_database_roundtrip::*` | DB 读写一致性 | 手工 record 字典 | 写入后读出一致 | 6, 7 |
| L3-9 | `test_scheduler_stages::*` | 调度顺序与上下文传递 | 手工 `task_stages` | dispatch 事件顺序正确 | 3 |
| L3-10 | `test_main_bootstrap::test_bootstrap_*_registers_instance` | 装配函数注册 PES | 手工 config + `tmp_path` | PES 在 Registry 中可查 | 4, 5 |
| L3-11 | `test_main_bootstrap::test_main_injects_shared_run_id` | `main()` 注入 run_id | monkeypatch 替换组件 | 两个 PES + Scheduler 共享同一 run_id | 5 |

### 3.2 待新建 L3 测试

| 编号 | 测试文件::用例 | 验证什么 | 输入 | 预期输出 | TD Task |
|---|---|---|---|---|---|
| L3-12 | `test_task_spec_schema::test_task_spec_from_dict` | TaskSpec 可从字典构造 | 手工字典 `{"task_type":"tabular",...}` | `task_spec.metric_name == "auc"` | 1 |
| L3-13 | `test_task_spec_schema::test_genome_schema_with_template_file` | GenomeSchema.template_file 字段 | 手工构造含 `template_file` 的 schema | `schema.template_file` 指向有效路径 | 2 |
| L3-14 | `test_workspace::test_create_links_prepared_public` | Workspace.create() 链接数据 | `tmp_path` + 竞赛目录 | `data/` 目录正确映射竞赛数据 | 10 |
| L3-15 | `test_workspace::test_write_and_read_run_metadata` | run 级 metadata.json 读写 | 手工 metadata 字典 | 写入后 `read_run_metadata()` 返回一致内容 | 5 |
| L3-16 | `test_grading::test_grading_config_defaults` | GradingConfig 默认值 | 无参数构造 | `enabled==True`, `accepted_statuses==("completed","success")` | 11 |
| L3-17 | `test_grading::test_grading_result_fields_complete` | GradingResult 含全部 11 个必需字段 | 手工构造 GradingResult | 所有字段非 None（阈值除外） | 11 |

---

## 4. L2 类测试（需真实运行回放）

这些测试验证**系统对真实运行产物的处理逻辑**。输入必须从 L1 运行截取。

### 4.1 回放场景清单

每个场景必须从一次真实 `main.py` 运行中截取（截取规范见 `docs/evolve.md` §5.1.1）。

| 回放目录 | 来源场景 | 截取内容 | TD Task |
|---|---|---|---|
| `draft_success_tabular_v1/` | 成功的 tabular DraftPES 运行 | turns, solution.py, stdout.log, metrics.json, submission.csv, expected.json | 6, 7, 8, 9 |
| `draft_runtime_error_v1/` | execute 阶段 solution.py 运行报错 | turns, solution.py, stderr.log | 7 |
| `draft_metric_missing_v1/` | 运行成功但无 val_metric 输出 | turns, solution.py, stdout.log | 8 |
| `draft_missing_solution_file_v1/` | Agent 没有写出 solution.py | turns（无 Write tool_call） | 6 |
| `draft_empty_solution_file_v1/` | Agent 写出空 solution.py | turns, solution.py（空文件） | 6 |
| `draft_syntax_error_v1/` | Agent 写出语法错误的 solution.py | turns, solution.py | 6 |
| `draft_submission_schema_error_v1/` | submission.csv 列名/行数不匹配 | turns, solution.py, submission.csv, stdout.log | 9 |
| `draft_submission_missing_v1/` | 运行成功但没有 submission.csv | turns, solution.py, stdout.log | 9 |
| `feature_extract_tabular_success_v1/` | 成功的 FeatureExtract 运行 | plan.txt, execute_raw.txt, summarize.txt, input.json, expected.json | 1, 4 |
| `feature_extract_degraded_v1/` | 竞赛描述缺失关键信息 | 同上 | 1 |

### 4.2 L2 单元测试

#### 4.2.1 Tool-Write 契约（`test_tool_write_contract.py`）

| 编号 | 用例 | 验证什么 | 回放输入 | 预期输出 | TD Task |
|---|---|---|---|---|---|
| L2-1 | `test_execute_reads_non_empty_solution` | 成功时从 workspace 读真实代码 | `draft_success_tabular_v1/turns.json` + `solution.py` | `workspace.read_working_solution()` 返回真实代码；`execute_summary` 含 `exit_code=0` | 6 |
| L2-2 | `test_persists_code_snapshot` | 代码快照写入 DB | 同上 | `db.get_latest_code_snapshot()` 与文件内容一致 | 6 |
| L2-3 | `test_fails_when_solution_missing` | 缺失 solution.py 标记失败 | `draft_missing_solution_file_v1/turns.json` | `ValueError("未写出代码文件")`；`status=="failed"` | 6 |
| L2-4 | `test_fails_when_solution_empty` | 空 solution.py 标记失败 | `draft_empty_solution_file_v1/turns.json` + `solution.py`（空） | `ValueError("代码文件为空")` | 6 |
| L2-5 | `test_fails_on_syntax_error` | 语法错误标记失败 | `draft_syntax_error_v1/turns.json` + `solution.py` | `ValueError("语法错误")` | 6 |

#### 4.2.2 执行事实采集（`test_execute_fact_capture.py`）

| 编号 | 用例 | 验证什么 | 回放输入 | 预期输出 | TD Task |
|---|---|---|---|---|---|
| L2-6 | `test_extract_from_real_tool_trace` | 从 turns 恢复执行事实 | `draft_success_tabular_v1/turns.json` | `exec_fact` 含正确 `command`, `stdout`, `stderr`, `exit_code`, `duration_ms` | 7 |
| L2-7 | `test_non_zero_exit_code_marks_failure` | 非零退出码处理 | `draft_runtime_error_v1/turns.json` + `solution.py` | `exec_logs` 中 `exit_code==1`；`stderr` 含真实 traceback；`status=="failed"` | 7 |

#### 4.2.3 执行事实采集边界（`test_exec_runner.py`，待新建）

| 编号 | 用例 | 验证什么 | 回放输入 | 预期输出 | TD Task |
|---|---|---|---|---|---|
| L2-8 | `test_multiple_bash_calls_picks_last_python_run` | 多次 Bash 调用时选最后一次 python 运行 | 含多个 Bash tool_call 的 turns.json | 返回最后一次 `python solution.py` 的结果 | 7 |
| L2-9 | `test_no_bash_call_returns_none` | turns 中无 Bash 调用 | 仅含 Write tool_call 的 turns.json | 返回 None 或空 fact | 7 |

#### 4.2.4 指标提取（`test_metric_extraction.py`）

| 编号 | 用例 | 验证什么 | 回放输入 | 预期输出 | TD Task |
|---|---|---|---|---|---|
| L2-10 | `test_extract_from_structured_payload` | 从 metrics.json 提取 | `draft_success_tabular_v1/metrics.json` | `val_metric_name`, `val_metric_value`, `val_metric_direction` 正确 | 8 |
| L2-11 | `test_extract_from_real_stdout` | 从真实 stdout 提取 | `draft_success_tabular_v1/stdout.log` | 同上 | 8 |
| L2-12 | `test_missing_metric_raises` | 缺失 metric 时失败 | `draft_metric_missing_v1/stdout.log` | `ValueError("未提取到 val_metric_value")` | 8 |

#### 4.2.5 Submission 校验（`test_submission_validator.py`，待新建）

| 编号 | 用例 | 验证什么 | 回放输入 | 预期输出 | TD Task |
|---|---|---|---|---|---|
| L2-13 | `test_valid_submission_passes` | 格式正确的 submission 通过 | `draft_success_tabular_v1/submission.csv` + 真实 `sample_submission.csv` | 列名、列顺序、行数一致 | 9 |
| L2-14 | `test_schema_mismatch_detected` | 列名/行数不匹配被识别 | `draft_submission_schema_error_v1/submission.csv` | 明确报告不匹配项 | 9 |
| L2-15 | `test_missing_submission_detected` | submission 不存在时的处理 | `draft_submission_missing_v1/`（无 submission.csv） | 返回明确的缺失标记 | 9 |
| L2-16 | `test_validation_gates_test_score` | 未通过校验时阻止进入评分流程 | schema 错误的 submission | 评分流程不被触发 | 9 |

#### 4.2.6 Workspace 版本归档（`test_workspace.py`，待新建）

| 编号 | 用例 | 验证什么 | 输入 | 预期输出 | TD Task |
|---|---|---|---|---|---|
| L2-17 | `test_save_version_creates_directory` | save_version 创建版本目录 | `draft_success_tabular_v1/solution.py` + `submission.csv` | `history/{generation}_{solution_id}/` 含 solution.py + submission.csv | 10 |
| L2-18 | `test_promote_best_updates_best_dir` | 高 fitness 时更新 best/ | 版本目录 + metadata | `best/` 目录内容与版本目录一致 | 10 |
| L2-19 | `test_promote_best_skips_lower_fitness` | 低 fitness 不覆盖 best/ | best/ 已有 0.9，新 fitness 0.5 | `best/` 内容不变 | 10 |
| L2-20 | `test_artifact_paths_match_db` | DB 工件路径与文件一致 | save_version 后查 DB | `solution_file_path` 指向的文件存在且内容一致 | 10 |

#### 4.2.7 评分模块（`test_grading.py`，待新建）

| 编号 | 用例 | 验证什么 | 输入 | 预期输出 | TD Task |
|---|---|---|---|---|---|
| L2-21 | `test_explicit_context_preferred` | 显式上下文字段优先于路径猜测 | `GradingConfig(competition_id="x", mlebench_data_dir="y")` | 使用显式值，不做路径推断 | 11 |
| L2-22 | `test_fallback_from_competition_root` | 从 `competition_root_dir` 推断 | `GradingConfig(competition_dir="/path/to/comp")` | 正确推断 `competition_id` 和 `data_dir` | 11 |
| L2-23 | `test_fallback_from_prepared_public` | 从 `prepared/public` 路径推断 | 含 `prepared/public` 的竞赛目录 | 正确推断 | 11 |
| L2-24 | `test_missing_submission_skips_safely` | 缺 submission.csv 安全跳过 | `GradingConfig` + 不存在的 submission 路径 | 返回 None，不抛异常 | 11 |
| L2-25 | `test_invalid_submission_skips_safely` | 无效 submission 安全跳过 | 格式错误的 submission.csv | 返回 None 或 `test_valid_submission==False` | 11 |
| L2-26 | `test_result_has_all_required_fields` | 评分结果含全部 11 个必需字段 | 有效评分结果 | `solution_id`, `competition_id`, `test_score`, `test_score_direction`, `test_valid_submission`, `test_medal_level`, 四个阈值, `graded_at` 全部非缺失 | 11 |

### 4.3 L2 集成测试

| 编号 | 测试文件::用例 | 验证什么 | 回放输入 | 预期输出 | TD Task |
|---|---|---|---|---|---|
| L2-I1 | `test_draft_pes_tool_write_flow::test_success` | Scheduler -> DraftPES 成功闭环 | `draft_success_tabular_v1/` 全套 | `TaskCompleteEvent.status=="completed"`；DB 有 code_snapshot | 6 |
| L2-I2 | `test_draft_pes_tool_write_flow::test_failure` | 失败路径不卡调度 | `draft_missing/empty/syntax_error` | `TaskCompleteEvent.status=="failed"`；DB 中 `execute_summary` 含失败原因 | 6 |
| L2-I3 | `test_draft_pes_execute_fact_flow::test_success` | exec_logs 落库 | `draft_success_tabular_v1/` | `exec_logs` 含正确 `exit_code`, `duration_ms`, `val_metric_value` | 7 |
| L2-I4 | `test_draft_pes_execute_fact_flow::test_failure` | 失败 exec_logs 落库 | `draft_runtime_error_v1/` | `exec_logs` 含 `exit_code==1` 和真实 stderr | 7 |
| L2-I5 | `test_draft_pes_runtime_flow::test_success_backfills_fitness` | fitness 回写 DB | `draft_success_tabular_v1/` | `solutions.fitness==真实值`；`metric_*` 字段正确 | 8 |
| L2-I6 | `test_draft_pes_runtime_flow::test_missing_metric_marks_failed` | 缺 metric 时 failed | `draft_metric_missing_v1/` | `solutions.status=="failed"`；`fitness is None` | 8 |
| L2-I7 | `test_feature_extract_draft_pipeline::test_context_flows` | FeatureExtract 产出注入 Draft | `feature_extract_tabular_success_v1/` + `draft_success_tabular_v1/` | Draft context 含 `task_spec`, `data_profile`, `schema`, `template_content` | 4 |

---

## 5. L1 类测试（真实竞赛 + 真实 LLM）

功能测试，验证 evolve.md §6.4 的五个最小验收条件。

### 5.1 前置条件

```bash
HERALD_TEST_DATA_ROOT=~/.cache/mle-bench/data   # MLE-Bench 数据目录
# claude_agent_sdk 可用
# mlebench 可用（仅 test_score 测试需要）
```

所有 L1 测试标记 `@pytest.mark.slow`，CI 按需运行。

### 5.2 功能测试（`test_draft_pes_real_cases.py`，待新建）

| 编号 | 用例 | 验证什么 | 输入 | 预期输出 | TD Task |
|---|---|---|---|---|---|
| L1-1 | `test_tabular_playground_full_loop` | 单竞赛 DraftPES 全闭环 | `tabular-playground-series-may-2022` 真实数据 + 真实 LLM | 1. `working/solution.py` 存在且非空 2. `working/submission.csv` 存在 3. `val_metric_value` 存在 4. `solutions` 表有记录 5. `exec_logs` >= 1 条 6. `code_snapshots` >= 1 条 | 6-10 |
| L1-2 | `test_spaceship_titanic_full_loop` | 第二竞赛闭环 | `spaceship-titanic` 真实数据 + 真实 LLM | 同上 | 6-10 |
| L1-3 | `test_feature_extract_then_draft` | 双 PES 流水线闭环 | 同上 + `task_stages` | L1-1 的全部输出 + FeatureExtract 产出 `task_spec.json` 和 `data_profile.md` | 1-10 |
| L1-4 | `test_version_saved_and_best_promoted` | 成功后版本归档 | L1-1 成功运行后 | `history/` 含版本目录；`best/` 被设置 | 10 |

### 5.3 评分集成（`test_draft_pes_grading_flow.py`，待新建）

| 编号 | 用例 | 验证什么 | 输入 | 预期输出 | TD Task |
|---|---|---|---|---|---|
| L1-5 | `test_score_acquisition` | test_score 补采 | L1-1 产出的 `submission.csv` | `solution.metadata` 含 `test_score`, `test_medal_level`, 四个阈值, `graded_at` | 11 |
| L1-6 | `test_score_does_not_override_fitness` | test_score 不覆盖 fitness | 同上 | `solution.fitness` == 原始 `val_metric_value`（未被改写） | 11 |
| L1-7 | `test_val_and_test_score_distinguished` | 二者被明确区分并持久化 | 同上 | `val_metric_value` 在 `solutions` 表；`test_score` 在 `solution.metadata`；两者值不同 | 11 |

### 5.4 L1 副产物归档

每次 L1 测试成功运行后，其产物应被截取为 L2 回放资产。建议流程：

1. L1 测试 fixture 在运行结束后将产物复制到 `tests/cases/replays/_staging/`
2. 人工审查后移入正式回放目录（如 `draft_success_tabular_v1/`）
3. 更新 `expected.json` 中的断言值

---

## 6. deepeval 评审

验证 LLM 输出的文本质量，不替代结构化 assert。

### 6.1 测试清单（`test_deepeval_draft_outputs.py`，待新建）

| 编号 | 用例 | 评审什么 | 输入 | 评判标准 | TD Task |
|---|---|---|---|---|---|
| D-1 | `test_plan_summary_quality` | plan_summary 覆盖任务目标与约束 | L1 运行产出的 `plan_summary` + 竞赛 `description.md` | rubric: 提及 metric、task_type、数据特征、约束条件 | 12 |
| D-2 | `test_execute_summary_quality` | execute_summary 忠实于执行日志 | L1 运行产出的 `execute_summary` + `exec_logs` | rubric: 提及 exit_code、metric_value，未虚构不存在的结果 | 12 |
| D-3 | `test_summarize_insight_quality` | summarize_insight 的可操作性 | L1 运行产出的 `summarize_insight` | rubric: 包含可操作建议，不是空泛总结 | 12 |

### 6.2 约束

- deepeval 只用于**无法纯靠 assert 判定的 LLM 输出质量**
- 云端报告是可选项，不是硬依赖
- 本地可运行 + 本地有报告即满足当前阶段要求

---

## 7. 竞赛 Manifest（Task 12 资产基建）

### 7.1 目录结构

```text
tests/cases/competitions/
  tabular-playground-series-may-2022.yaml
  spaceship-titanic.yaml
```

### 7.2 Manifest 最小字段

```yaml
competition_id: tabular-playground-series-may-2022
task_type: tabular
metric_name: auc
metric_direction: maximize
relative_root: tabular-playground-series-may-2022
required_public_files:
  - train.csv
  - test.csv
  - sample_submission.csv
```

### 7.3 CI 阻塞策略

| 分组 | 竞赛 | CI 行为 |
|---|---|---|
| CI 阻塞集 | `tabular-playground-series-may-2022` | L1 测试失败则 CI 红 |
| CI 阻塞集 | `spaceship-titanic` | 同上 |
| 扩展观测集 | `histopathologic-cancer-detection` | 仅报告，不阻塞 |
| 扩展观测集 | `chaii-hindi-and-tamil-question-answering` | 同上 |

---

## 8. TD.md Task 覆盖交叉索引

确保每个 TD.md Task 的验证 Checkpoint 在本矩阵中都有对应测试。

### Task 1: FeatureExtractPES

| Checkpoint | 覆盖测试 |
|---|---|
| `FeatureExtractPES.run()` 能完整执行三阶段 | L2-I7（回放）、L1-3（真实） |
| execute 产出 TaskSpec JSON 可解析 | `test_feature_extract_pes.py`（已有）、L3-12 |
| `data_profile.md` 非空 | `test_feature_extract_pes.py`（已有）、L1-3 |
| `genome_template` 值合法 | `test_feature_extract_pes.py`（已有）、L3-3, L3-4 |

### Task 2: GenomeSchema 模板

| Checkpoint | 覆盖测试 |
|---|---|
| `load_genome_template("tabular")` 返回 4 slot + 模板 | L3-3 |
| `load_genome_template("unknown")` 返回 generic | L3-4 |
| 模板 GENE 标记可识别 | L3-3（在 `test_genome_template.py` 中验证） |

### Task 3: Scheduler task_stages

| Checkpoint | 覆盖测试 |
|---|---|
| `task_stages` 按序执行 | L3-9 |
| `output_context` 跨 stage 传递 | L3-9、L2-I7 |
| 不传 `task_stages` 时向后兼容 | L3-9 |

### Task 4: Bootstrap 整合

| Checkpoint | 覆盖测试 |
|---|---|
| `bootstrap_feature_extract_pes()` 返回有效实例 | L3-10 |
| DraftPES dispatch context 含 `task_spec`, `data_profile`, `schema` | L2-I7 |
| `draft_plan` 模板渲染 `data_profile` | L3-5 |
| `metadata.json` 存在 | L3-15 |

### Task 5: run_id 与 run 元数据

| Checkpoint | 覆盖测试 |
|---|---|
| `runtime_context` 含 `run_id` | L3-11 |
| `metadata.json` 含 `run_id`, `started_at` | L3-15 |
| run 结束后 `metadata.json` 含 `finished_at` | L3-15 |

### Task 6: Tool-Write 契约

| Checkpoint | 覆盖测试 |
|---|---|
| success case 生成非空 `solution.py` | L2-1、L2-I1、L1-1 |
| missing/empty 标记失败 | L2-3、L2-4、L2-I2 |
| syntax error 标记失败 | L2-5、L2-I2 |
| `code_snapshots` 存在且一致 | L2-2、L2-I1、L1-1 |

### Task 7: 执行事实采集

| Checkpoint | 覆盖测试 |
|---|---|
| 成功 case 至少一条 `exec_logs` | L2-6、L2-I3、L1-1 |
| `stdout`, `stderr`, `exit_code`, `duration_ms` 可查 | L2-6、L2-I3 |
| runtime error 标记 failed | L2-7、L2-I4 |
| 多次 Bash 调用选最后一次 python 运行 | L2-8 |
| 无 Bash 调用时安全处理 | L2-9 |

### Task 8: val_metric 提取与 fitness 回写

| Checkpoint | 覆盖测试 |
|---|---|
| `solution.metrics` 含 `val_metric_name/value/direction` | L2-10、L2-11、L2-I5、L1-1 |
| `fitness` 来自 `val_metric_value` | L2-I5、L1-1 |
| 缺失 `val_metric_value` 不判为成功 | L2-12、L2-I6 |
| `to_record()` 正确映射到 DB 列 | L3-1 |
| `to_prompt_payload()` 暴露新旧键 | L3-2 |

### Task 9: submission.csv 校验

| Checkpoint | 覆盖测试 |
|---|---|
| schema 正确的 submission 通过校验 | L2-13 |
| 列名/行数不匹配被识别 | L2-14 |
| submission 不存在被检测 | L2-15 |
| 未通过校验阻止进入评分 | L2-16 |
| 真实 `sample_submission.csv` 作为基准 | L2-13（使用真实竞赛的 sample） |

### Task 10: 版本归档

| Checkpoint | 覆盖测试 |
|---|---|
| `save_version()` 创建版本目录 | L2-17 |
| 版本目录含 solution.py + submission.csv | L2-17 |
| `promote_best()` 在 fitness 更优时更新 `best/` | L2-18 |
| 低 fitness 不覆盖 best | L2-19 |
| DB 工件路径与文件一致 | L2-20 |
| `metadata.json` 含 `finished_at` | L3-15 |
| L1 真实运行后验证归档 | L1-4 |

### Task 11: test_score 评分

| Checkpoint | 覆盖测试 |
|---|---|
| 显式上下文优先 | L2-21 |
| 路径 fallback（competition_root） | L2-22 |
| 路径 fallback（prepared/public） | L2-23 |
| missing submission 安全跳过 | L2-24 |
| invalid submission 安全跳过 | L2-25 |
| 评分结果含 11 个必需字段 | L2-26、L3-17 |
| 有效 submission 拿到 `test_score` | L1-5 |
| `fitness` 不被改写 | L1-6 |
| `val_metric_value` 与 `test_score` 明确区分 | L1-7 |

### Task 12: 真实用例与 deepeval

| Checkpoint | 覆盖测试 |
|---|---|
| 竞赛 manifest 存在 | §7 竞赛 Manifest |
| CI 阻塞集稳定运行 | L1-1、L1-2 |
| 真实回放覆盖成功与失败路径 | §4.1 回放场景清单 |
| deepeval 审阅文本质量 | D-1、D-2、D-3 |

---

## 9. 当前回放资产替换对照表

当前 `tests/cases/replays/` 中所有资产均为人工构造（L3），需要从 L1 运行截取后替换。

| 回放目录 | 当前来源 | 需替换内容 | 差异说明 |
|---|---|---|---|
| `draft_success_tabular_v1/turns.json` | 手写（stdout=`"training done\n..."`） | L1 运行截取 | 真实 turns 含多轮 tool_call、Write+Bash 组合、完整训练日志 |
| `draft_success_tabular_v1/solution.py` | 空壳 `solve()` | L1 产出 | 真实代码含 pandas、sklearn、模型训练逻辑 |
| `draft_success_tabular_v1/metrics.json` | 手写 `auc=0.8123` | L1 产出 | 真实值由脚本计算得出 |
| `draft_success_tabular_v1/submission.csv` | 不存在 | L1 产出 | 真实提交文件 |
| `draft_success_tabular_v1/stdout.log` | 不存在 | L1 截取 | 真实训练日志含 epoch、loss、metric |
| `draft_runtime_error_v1/turns.json` | 手写 `raise RuntimeError("boom")` | L1 截取 | 真实 traceback 含文件路径和行号 |
| `draft_runtime_error_v1/stderr.log` | 不存在 | L1 截取 | 完整多行 traceback |
| `draft_metric_missing_v1/stdout.log` | 手写两行 | L1 截取 | 真实 stdout 含训练日志但无 metric 行 |
| `draft_submission_schema_error_v1/` | 不存在 | L1 截取 | 需要一次列名不匹配的真实运行 |
| `draft_submission_missing_v1/` | 不存在 | L1 截取 | 需要一次未产出 submission 的真实运行 |

---

## 10. 执行优先级

| 优先级 | 动作 | 阻塞什么 |
|---|---|---|
| **P0** | 跑一次 L1（`tabular-playground-series-may-2022`），截取全套回放资产 | 所有 L2 测试的可信度 |
| **P1** | 用真实资产替换现有 `tests/cases/replays/` | 现有 L2 测试的合规性 |
| **P2** | 新建 Task 9 测试（submission 校验） | Task 9 开发 |
| **P2** | 新建 Task 10 测试（版本归档） | Task 10 开发 |
| **P2** | 新建 Task 11 测试（评分 hook） | Task 11 开发 |
| **P3** | 新建 Task 12 测试（竞赛 manifest + deepeval） | 测试体系完整性 |
