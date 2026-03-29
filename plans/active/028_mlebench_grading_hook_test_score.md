# 028：接入 MLEBenchGradingHook 获取 test_score

## 元信息
- 状态: draft
- 创建: 2026-03-29
- 对应 TD: Task 11（§6.11）

## 1.1 摘要

本任务聚焦把 Task 9 已经产出的“有效 `submission.csv`”继续推进到 Task 11 所要求的“补采外部 `test_score` 并沉淀为人类评估信号”。最小闭环是：在 PES `after_run` 阶段挂接 `MLEBenchGradingHook`，仅对 `completed/success` 且通过 submission 校验的 solution 触发评分；评分成功时将 `test_score`、奖牌、阈值、时间戳等字段写入 `workspace/logs/grading_result.json`，并可同步写入 DB 的非 prompt 通道，评分失败时安全跳过，不影响主链路完成。

结合当前仓库现状，`tests/grading.py` 里其实已经存在 `GradingConfig`、`GradingResult`、`MLEBenchGradingHook` 和 `create_grading_hook()` 的实现，但它还没有正式装配到 `core/main.py -> BasePES.after_run` 的运行链路，也缺少 Task 11 对应的单元测试与集成测试。因此 `028` 的核心不是重写评分逻辑，而是完成“hook 注册、上下文补齐、结果持久化语义确认、测试补齐”这四件事。

## 1.2 审查点（Review Required）

1. **生产代码是否继续复用 `tests/grading.py`**
   当前倾向继续复用 `tests/grading.py` 作为 Task 11 的正式评分模块，而不是本任务里额外迁移到 `core/`。
   原因：`docs/TD.md` §6.11 明确把该文件列为涉及文件；仓库里也已有较完整实现。MVP 阶段优先接线跑通，避免为了“目录更优雅”扩大改动面。
2. **hook 注册粒度**
   当前倾向在 `bootstrap_draft_pes()` 装配完成后，仅给 `DraftPES` 注册 `after_run` 评分 hook，不给 `FeatureExtractPES` 注册。
   原因：Task 11 只关心 `submission.csv`；FeatureExtractPES 不产出 submission，注册也只会增加噪音。
3. **评分结果持久化位置**
   当前倾向把评分结果写入 `workspace/logs/grading_result.json`，并可同步写入 DB 的独立字段或独立记录，但**不写入 `solution.metadata`**。
   原因：当前 `solution.to_prompt_payload()` 会把 `metadata` 暴露给后续 prompt；而 `test_score` 只用于人类评估，不能进入 agent 可读上下文。
4. **评分失败策略**
   当前倾向严格遵守“失败安全跳过”：`mlebench` 未安装、上下文解析失败、submission 缺失、submission 未校验通过、评分异常，均只记录日志并返回 `None`，不改写 `solution.status`。
   原因：`test_score` 是补采真实性信号，不应反向破坏已完成的主链路。

## 1.3 拟议变更（Proposed Changes）

### A. 在 DraftPES 装配阶段注册 after_run 评分 hook

- [MODIFY] [core/main.py](/home/yuchengzhang/Code/Herald2/core/main.py)
  - [MODIFY] `bootstrap_draft_pes()`
    - 引入 `create_grading_hook()`
    - 基于当前 run 上下文注册 `DraftPES.hooks.register(...)`
    - 明确向 hook 注入：
      - `competition_root_dir`
      - `public_data_dir`
      - 可选 `competition_id`
      - 可选 `mlebench_data_dir`
  - [MODIFY] `main()`
    - 如有必要，补充 `runtime_context` 中与评分相关的稳定字段，确保 hook 不依赖路径猜测也能工作

### B. 让 HookManager 能稳定注册基于 `__call__` 的评分插件

- [MODIFY] [core/pes/hooks.py](/home/yuchengzhang/Code/Herald2/core/pes/hooks.py)
  - [MODIFY] `HookManager.register()`
    - 校验并支持注册带 `after_run(context)` hookimpl 的插件对象
    - 如 `MLEBenchGradingHook` 现状只有 `__call__`，则补一层适配方案
- [MODIFY] [tests/grading.py](/home/yuchengzhang/Code/Herald2/tests/grading.py)
  - [MODIFY] `MLEBenchGradingHook`
    - 让其以 pluggy 插件形态响应 `after_run(context)`
    - 保留 `__call__()` 作为核心逻辑入口，避免测试与外部直接调用方式失效
  - [DELETE] `_attach_result_to_solution()`
    - 删除“将评分结果写回 `solution.metadata`”的方案，避免 agent 后续通过 prompt 读到 `test_score`
  - [NEW] `_persist_grading_result(...)`
    - 将评分结果写入 `workspace/logs/grading_result.json`
    - 文件内容至少包含：
      - `solution_id`
      - `competition_id`
      - `test_score`
      - `test_score_direction`
      - `test_valid_submission`
      - `test_medal_level`
      - `test_above_median`
      - `test_gold_threshold`
      - `test_silver_threshold`
      - `test_bronze_threshold`
      - `test_median_threshold`
      - `test_graded_at`
  - [NEW] `_persist_grading_result_to_db(...)`
    - 若现有 DB 易于扩展，则把评分结果写入独立表或独立记录
    - 约束：不得复用 `solution.metadata` 作为 DB 落点

### C. 对评分上下文解析做最小补强，但不改写 fitness 语义

- [MODIFY] [tests/grading.py](/home/yuchengzhang/Code/Herald2/tests/grading.py)
  - [MODIFY] `_resolve_competition_dir()` / `_resolve_competition_id()` / `_resolve_mlebench_data_dir()`
    - 优先读取显式注入字段
    - 回退到 `competition_root_dir` / `public_data_dir` / `competition_dir` 推断
  - [MODIFY] `MLEBenchGradingHook.__call__()`
    - 仅在 `status in ("completed", "success")`
    - 且 `submission_file_path` 存在
    - 且 `submission_validated` 不是 `False`
    - 时调用 `grade_submission()`
    - 明确保证不改写 `solution.metrics`、`solution.fitness`、`solution.metadata`

### D. 显式阻断 `test_score` 进入 prompt 上下文

- [MODIFY] [core/pes/types.py](/home/yuchengzhang/Code/Herald2/core/pes/types.py)
  - [MODIFY] `to_prompt_payload()`
    - 即使后续有人误把 grading 结果写到 `solution` 相关结构，也要在 prompt payload 层显式过滤 human-only grading 字段
    - 至少约束：
      - `test_score`
      - `test_score_direction`
      - `test_valid_submission`
      - `test_medal_level`
      - `test_above_median`
      - `test_competition_id`
      - `test_gold_threshold`
      - `test_silver_threshold`
      - `test_bronze_threshold`
      - `test_median_threshold`
      - `test_graded_at`
    - 目标：从接口层保证 claude agent sdk 看不到这些字段

### E. 补齐 Task 11 的单元测试与集成测试

- [NEW] [tests/unit/test_grading.py](/home/yuchengzhang/Code/Herald2/tests/unit/test_grading.py)
  - [NEW] `test_grading_config_defaults()`
    - 断言默认配置 `enabled=True`、`accepted_statuses==("completed", "success")`
  - [NEW] `test_grading_result_fields_complete()`
    - 构造完整 `GradingResult`，校验 Task 11 要求字段齐全
  - [NEW] `test_explicit_context_preferred()`
    - 显式 `competition_id` / `mlebench_data_dir` 优先于路径推断
  - [NEW] `test_fallback_from_competition_root()`
  - [NEW] `test_fallback_from_prepared_public()`
  - [NEW] `test_missing_submission_skips_safely()`
  - [NEW] `test_invalid_submission_skips_safely()`
  - [NEW] `test_persist_grading_result_writes_log_file()`
    - 校验 `workspace/logs/grading_result.json` 中字段集合完整
  - [NEW] `test_prompt_payload_does_not_expose_test_score()`
    - 即使存在 grading 结果，也不会通过 `to_prompt_payload()` 暴露

- [NEW] [tests/integration/test_draft_pes_grading_flow.py](/home/yuchengzhang/Code/Herald2/tests/integration/test_draft_pes_grading_flow.py)
  - [NEW] `test_after_run_grades_valid_submission()`
    - 使用成功回放资产 + monkeypatch 伪造 `grade_submission()` 返回值
    - 断言 `workspace/logs/grading_result.json` 写入成功，且字段齐全
  - [NEW] `test_grading_does_not_override_fitness()`
    - 断言评分后 `solution.fitness` 仍等于 `val_metric_value`
  - [NEW] `test_grading_does_not_enter_prompt_payload()`
    - 断言后续 `solution.to_prompt_payload()` 中不含 `test_score` 字段
  - [NEW] `test_missing_submission_skips_without_breaking_run()`
    - 使用 `draft_submission_missing_v1`
    - 断言 run 结束路径稳定，hook 不抛异常
  - [NEW] `test_invalid_submission_skips_grading()`
    - 使用 schema 错误 case
    - 断言不会触发 `grade_submission()`

### F. 文档同步

- [MODIFY] [docs/TD.md](/home/yuchengzhang/Code/Herald2/docs/TD.md)
  - [MODIFY] 将 Task 11 状态从 `⬜ 待实现` 更新为已完成（若编码与测试通过）
- [MODIFY] [docs/test_matrix.md](/home/yuchengzhang/Code/Herald2/docs/test_matrix.md)
  - [MODIFY] 将 `tests/unit/test_grading.py`、`tests/integration/test_draft_pes_grading_flow.py` 状态从“待新建”更新为“已存在”（若编码与测试通过）

## 1.4 验证计划（Verification Plan）

1. 运行 `pytest tests/unit/test_grading.py`
2. 运行 `pytest tests/integration/test_draft_pes_grading_flow.py`
3. 回归运行
   - `pytest tests/integration/test_draft_pes_runtime_flow.py`
   - `pytest tests/unit/test_draft_pes.py`
   - `pytest tests/unit/test_database_roundtrip.py`
4. 人工验证点
   - 成功 case 的 `workspace/logs/grading_result.json` 中出现 `test_score`、`test_score_direction`、`test_valid_submission`、`test_medal_level`
   - 同时出现 `test_competition_id`、四个阈值字段、`test_graded_at`
   - `solution.metrics["val_metric_value"]` 与 `solution.fitness` 在评分前后保持不变
   - `solution.to_prompt_payload()` 不包含任何 `test_*` grading 字段
   - `submission.csv` 缺失、submission 校验失败、`mlebench` 不可用时，run 主链路仍能完成，不因评分补采失败而转为 failed

## 约束与备注

- 本任务不把 `test_score` 用作在线调度信号
- 本任务优先写 `workspace/logs/grading_result.json`；DB 持久化仅在不暴露给 prompt 的前提下进行
- 本任务不修改 Task 8 已建立的 `fitness <- val_metric_value` 语义
- 本任务明确禁止通过 `solution.metadata` 暴露 `test_score`
- 若实现时发现 `tests/grading.py` 作为生产模块会触发明显导入/打包问题，再单独开后续任务迁移到 `core/`，本任务先以最小接线为目标
