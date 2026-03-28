# 019: Bootstrap 整合 + DraftPES 消费 data_profile

## 元信息
- 状态: draft
- 创建: 2026-03-28
- 对应 TD: Task 4（§6.4）

## 1.1 摘要

本任务把当前已具备的三个能力真正串成主链路：`main.py` 同时装配 `FeatureExtractPES` 与 `DraftPES`，`Scheduler` 按 `feature_extract -> draft` 两阶段执行，并让 `DraftPES` 通过调度上下文直接消费上游产出的 `task_spec`、`data_profile`、`schema` 与模板骨架。

同时补齐 run 级 `metadata.json`，保证一次运行从 bootstrap 开始就可追踪、可审阅。

## 1.2 审查点（Review Required）

1. **FeatureExtract 产出载荷范围**: 当前倾向在 `TaskCompleteEvent.output_context` 中直接传递 `task_spec`、`data_profile`、`schema`、`template_content`、`genome_template`，避免再引入单独的中间存储层
2. **DraftPES 消费方式**: 当前倾向不在 `DraftPES` 内新增复杂适配器，而是复用 `BasePES.build_prompt_context()` 现有的 `runtime_context + dispatch context` 合并语义，让 Prompt 模板直接消费
3. **run 元数据写入位置**: 当前倾向使用 `workspace/metadata.json` 作为 run 级入口文件，并在 run 结束时原地回写 `finished_at`

## 1.3 拟议变更（Proposed Changes）

### A. Bootstrap 装配与 run 元数据

- [MODIFY] `core/main.py`
  - [NEW] `bootstrap_feature_extract_pes(config, workspace, db) -> FeatureExtractPES`
    - 装配 `config/pes/feature_extract.yaml`
    - 注册前置 `FeatureExtractPES`
  - [MODIFY] `bootstrap_draft_pes(config, workspace, db) -> DraftPES`
    - 保持现有 DraftPES 装配逻辑
    - 与 FeatureExtract 使用一致的基础 runtime context
  - [NEW] `build_run_metadata(config, workspace, run_id, started_at) -> dict[str, Any]`
    - 生成 run 级元数据快照
  - [NEW] `write_run_metadata(workspace, metadata) -> Path`
    - 写入 `workspace/metadata.json`
  - [NEW] `update_run_metadata_finished_at(workspace, finished_at) -> None`
    - run 结束后回写完成时间
  - [MODIFY] `main()`
    - 生成 `run_id`
    - 同时装配 `FeatureExtractPES` 与 `DraftPES`
    - 将 `run_id` 注入两个 PES 的 `runtime_context`
    - 使用 `task_stages=[("feature_extract", 1), ("draft", max_tasks)]` 启动调度器
    - 在执行前后写入/回写 `metadata.json`

### B. FeatureExtractPES 输出可被 DraftPES 直接消费的上下文

- [MODIFY] `core/pes/feature_extract.py`
  - [MODIFY] `_handle_execute_response()`
    - 在解析 `genome_template` 后调用 `load_genome_template()`
    - 产出 `schema` 与 `template_content`
    - 将 `task_spec`、`data_profile`、`schema`、`template_content`、`genome_template` 写入 `solution.metadata`
  - [NEW] `_build_output_context(solution) -> dict[str, Any]`
    - 从 `solution.metadata` 组装调度器可合并的共享上下文
  - [MODIFY] `_handle_summarize_response()`
    - 发出带 `output_context` 的 `TaskCompleteEvent`

### C. Draft Prompt 模板消费 data_profile

- [MODIFY] `config/prompts/templates/draft_plan.j2`
  - [NEW] `data_profile` 区块
  - 明确要求 plan 利用上游数据概况决定建模/特征方向
- [MODIFY] `config/prompts/templates/draft_execute.j2`
  - [NEW] `data_profile` 区块
  - 明确要求 execute 结合数据特征落实实现与验证

### D. 测试补齐

- [MODIFY] `tests/unit/test_main_bootstrap.py`
  - [NEW] `bootstrap_feature_extract_pes()` 注册测试
  - [NEW] run 级 `metadata.json` 写入/回写测试
- [MODIFY] `tests/unit/test_feature_extract_pes.py`
  - [NEW] execute 阶段加载 `schema` / `template_content` 断言
  - [NEW] summarize 阶段 `output_context` 断言
- [MODIFY] `tests/unit/test_draft_pes.py`
  - [MODIFY] runtime_context 测试数据补入 `data_profile`
  - [NEW] 断言 plan / execute Prompt 中含 `data_profile`
- [MODIFY] `tests/unit/test_prompt_manager.py`
  - [NEW] 断言 `draft_plan` / `draft_execute` 渲染结果包含 `data_profile`
- [NEW] `tests/integration/test_feature_extract_draft_pipeline.py`
  - 使用真实 `FeatureExtractPES + DraftPES + Scheduler(task_stages)` 跑通两阶段链路
  - 断言 Draft 收到 `task_spec`、`data_profile`、`schema`、`template_content`

## 1.4 验证计划（Verification Plan）

1. 运行 `pytest tests/unit/test_main_bootstrap.py`
2. 运行 `pytest tests/unit/test_feature_extract_pes.py`
3. 运行 `pytest tests/unit/test_draft_pes.py`
4. 运行 `pytest tests/unit/test_prompt_manager.py`
5. 运行 `pytest tests/integration/test_feature_extract_draft_pipeline.py`
6. 人工验证点
   - `workspace/metadata.json` 存在，且包含 `run_id`、`started_at`、`finished_at`
   - `feature_extract` 完成后，`draft` 的 dispatch context 中可见 `task_spec`、`data_profile`、`schema`
   - `draft_plan` / `draft_execute` Prompt 明确出现 `data_profile` 区块

