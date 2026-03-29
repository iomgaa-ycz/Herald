# 026：生成并校验真实 `submission.csv`

## 元信息
- 状态: completed
- 创建: 2026-03-29
- 完成: 2026-03-29
- 对应 TD: Task 9（§6.9）

## 1.1 摘要

本任务聚焦把 `DraftPES.execute` 从“代码运行成功且拿到本地验证分数”推进到“产出一个真实、可评分、可被后续 hook 安全消费的 `submission.csv` 工件”。最小闭环是：在 execute 成功路径中确认 `working/submission.csv` 真实存在，基于真实 `sample_submission.csv` 做最小 schema 校验，并把校验结论纳入 `solution` 成功语义。

基于当前现状，`025` 已完成 execute 事实采集与 `val_metric_value -> fitness` 回写，但仓库里还没有把 `submission.csv` 当作硬约束工件来校验，L2 回放资产也缺少真实 `submission.csv` / `stdout.log` / `metrics.json`。因此 `026` 不处理版本归档或 test_score 采集本身，只补“submission 工件发现、schema 校验、失败闭环、评分前置门禁”四件事。

## 1.2 审查点（Review Required）

1. **校验范围收敛**：当前倾向只做 TD 明确要求的最小校验：
   - 文件存在
   - 列名一致
   - 列顺序一致
   - 行数一致
   不在本任务引入 dtype、空值比例、ID 集合完全相等等更重规则，保持 MVP 边界
2. **schema 来源**：当前倾向以 `competition_dir/prepared/public/sample_submission.csv` 为第一来源，若不存在则回退到 `competition_dir/sample_submission.csv`
3. **成功语义收紧**：当前倾向把“`exit_code == 0` 且提取到 `val_metric_value`，但 `submission.csv` 缺失或 schema 不匹配”视为 execute 失败，避免无效提交继续进入 `test_score` 流程
4. **评分门禁位置**：当前倾向先在 `DraftPES` 内把 `submission_validated=True/False` 写入 `solution.metadata`，`Task 11` 的 grading hook 再读取该事实决定是否评分；本任务不提前改造 grading hook 的整体结构

## 1.3 拟议变更（Proposed Changes）

### A. 在 DraftPES execute 成功路径中接入 submission 校验

- [MODIFY] [core/pes/draft.py](/home/yuchengzhang/Code/Herald2/core/pes/draft.py)
  - [MODIFY] `_handle_execute_response()`
    - 在 `_apply_val_metrics()` 之后、生成最终 `execute_summary` 之前，补充 `submission.csv` 校验
    - 校验失败时抛出明确错误，使 `BasePES.handle_phase_failure()` 统一标记 `solution.status="failed"`
    - 校验成功时把结论写入 `solution.metadata`
  - [NEW] `_validate_submission_artifact(solution: PESSolution) -> dict[str, Any]`
    - 读取 `working/submission.csv`
    - 定位真实 `sample_submission.csv`
    - 执行最小 schema 校验
    - 返回结构化校验结果
  - [NEW] `_resolve_sample_submission_path() -> Path`
    - 从 `runtime_context["competition_dir"]` 或 execute context 解析样例提交文件
    - 支持 `prepared/public/` 与根目录两种竞赛布局
  - [NEW] `_load_submission_schema(csv_path: Path) -> dict[str, Any]`
    - 读取 CSV 表头与行数
    - 仅返回本任务需要的 schema 事实：`columns`、`row_count`
  - [NEW] `_compare_submission_schema(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]`
    - 生成明确 mismatch 列表，如 `列顺序不一致`、`缺失列`、`行数不匹配`
  - [NEW] `_apply_submission_validation(solution: PESSolution, result: dict[str, Any]) -> None`
    - 成功时写入：
      - `solution.metadata["submission_validated"] = True`
      - `solution.metadata["submission_schema_columns"]`
      - `solution.metadata["submission_row_count"]`
      - `solution.metadata["sample_submission_path"]`
    - 失败时写入：
      - `solution.metadata["submission_validated"] = False`
      - `solution.metadata["submission_validation_errors"]`

### B. 抽出最小 submission 校验模块，避免 DraftPES 继续膨胀

- [NEW] [core/pes/submission.py](/home/yuchengzhang/Code/Herald2/core/pes/submission.py)
  - [NEW] `SubmissionSchema`
    - 字段：`columns: list[str]`、`row_count: int`
  - [NEW] `SubmissionValidationResult`
    - 字段：`is_valid: bool`、`errors: list[str]`、`submission_schema: SubmissionSchema`、`sample_schema: SubmissionSchema`
  - [NEW] `load_submission_schema(csv_path: str | Path) -> SubmissionSchema`
  - [NEW] `validate_submission_against_sample(submission_path: str | Path, sample_submission_path: str | Path) -> SubmissionValidationResult`
  - 说明：
    - 优先使用 `csv` 标准库实现，避免为 MVP 引入额外依赖
    - 保持函数纯净，便于 L3 / L2 单测覆盖

### C. 补最小 workspace 读取能力，减少路径拼装散落

- [MODIFY] [core/workspace.py](/home/yuchengzhang/Code/Herald2/core/workspace.py)
  - [NEW] `read_working_submission(file_name: str = "submission.csv") -> str`
    - 语义对齐 `read_working_solution()`
    - 文件不存在或为空时抛出明确 `ValueError`
  - [NEW] `get_competition_file_path(relative_name: str) -> Path | None`
    - 如实现成本低，可统一返回 `data/` 映射中的文件路径
    - 若会引入歧义，则保留在 `DraftPES` 中直接解析 `competition_dir`

### D. 为 Task 9 补齐真实回放资产与测试面

- [NEW] [tests/unit/test_submission_validator.py](/home/yuchengzhang/Code/Herald2/tests/unit/test_submission_validator.py)
  - [NEW] `test_valid_submission_passes()`
  - [NEW] `test_schema_mismatch_detected()`
  - [NEW] `test_missing_submission_detected()`
  - [NEW] `test_missing_sample_submission_raises()`
- [MODIFY] [tests/integration/test_draft_pes_execute_fact_flow.py](/home/yuchengzhang/Code/Herald2/tests/integration/test_draft_pes_execute_fact_flow.py)
  - success case 中真实写入 `submission.csv`
  - 断言 `TaskCompleteEvent.status == "completed"` 的前提包含 submission 校验通过
  - failure case 新增 `schema_error` 回放场景，断言 solution 被标记 `failed`
- [NEW] [tests/integration/test_draft_pes_runtime_flow.py](/home/yuchengzhang/Code/Herald2/tests/integration/test_draft_pes_runtime_flow.py)
  - [NEW] success case：`submission_validated == True`
  - [NEW] invalid case：schema 错误时 `submission_validated == False` 且 `fitness` 不改变既有事实，但 solution 状态为 `failed`
- [NEW] `tests/cases/replays/draft_success_tabular_v1/submission.csv`
- [NEW] `tests/cases/replays/draft_success_tabular_v1/stdout.log`
- [NEW] `tests/cases/replays/draft_success_tabular_v1/metrics.json`
- [NEW] `tests/cases/replays/draft_submission_schema_error_v1/`
  - [NEW] `turns.json`
  - [NEW] `solution.py`
  - [NEW] `submission.csv`
  - [NEW] `stdout.log`
  - [NEW] `expected.json`
- [NEW] `tests/cases/replays/draft_submission_missing_v1/`
  - [NEW] `turns.json`
  - [NEW] `solution.py`
  - [NEW] `stdout.log`
  - [NEW] `expected.json`

### E. 为后续 Task 11 预留评分门禁事实

- [MODIFY] [tests/grading.py](/home/yuchengzhang/Code/Herald2/tests/grading.py)
  - [MODIFY] `MLEBenchGradingHook.__call__()`
    - 在读取 `submission_file_path` 后，优先检查 `submission_validated`
    - 若显式为 `False`，直接跳过评分
    - 若缺失该字段，维持当前兼容行为，不在 `026` 中强制升级所有历史调用点
  - 备注：
    - 这里只加最小 gating，不在本任务里完整实现 Task 11

## 1.4 验证计划（Verification Plan）

1. 运行 `pytest tests/unit/test_submission_validator.py`
2. 运行 `pytest tests/integration/test_draft_pes_execute_fact_flow.py`
3. 运行 `pytest tests/integration/test_draft_pes_runtime_flow.py`
4. 回归运行
   - `pytest tests/unit/test_tool_write_contract.py`
   - `pytest tests/unit/test_execute_fact_capture.py`
   - `pytest tests/unit/test_database_roundtrip.py`
5. 人工验证点
   - success 回放中 `working/submission.csv` 存在，且与真实 `sample_submission.csv` 的列名、列顺序、行数一致
   - schema-error 回放会稳定失败，并把 mismatch 原因写入 `solution.metadata` / `execute_summary`
   - `submission_validated=False` 的 case 不会继续进入 `test_score` 评分
   - 本任务不会引入二次重跑，也不会覆盖 `025` 已写入的 `val_metric_value` / `fitness`

## 约束与备注

- 本任务不实现版本归档与 `best/` 提升；那是 `Task 10`
- 本任务不做完整评分功能，只补评分前置门禁；`test_score` 真正采集仍属于 `Task 11`
- 本任务不引入 pandas 作为 submission 校验依赖，优先使用标准库完成最小 schema 校验
- 若真实 L2 资产暂时缺失，可先补最小可运行回放目录，但应尽快用 L1 真回放替换，避免 L3 冒充 L2
