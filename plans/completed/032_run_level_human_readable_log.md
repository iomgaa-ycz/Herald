# 032：增加 run 级人类可读日志文件

## 元信息
- 状态: completed
- 创建: 2026-03-29
- 对应 TD: Task 17（§6.17）

## Context

当前 execute 阶段 Agent 通过 Bash 工具运行 `solution.py`，stdout/stderr 仅出现在终端输出和 `llm_calls.turns` 中。人类想实时观察训练日志时只能盯终端或事后查 DB。

**核心思路**：修改 `draft_execute.j2` prompt，指示 Agent 运行 solution.py 时用 `tee` 将输出同时写入终端和 `working/run.log`（与 solution.py 同目录），实现实时可观察的日志文件。

## 1.1 摘要

修改 `draft_execute.j2` prompt，要求 Agent 运行 solution.py 时必须用 `set -o pipefail; python solution.py 2>&1 | tee -a working/run.log`，将训练输出实时写入日志文件。同时在 Workspace 上暴露 `run_log_path` 并注入 prompt context。

## 1.2 审查点（Review Required）

1. **日志文件位置：`working/run.log`**
   与 solution.py 同目录（`working/`），而非 `logs/` 目录。方便 Agent 和人类在同一上下文中找到。

2. **tee 对 exit_code 的影响及解决方案**

   **问题**：`python solution.py 2>&1 | tee -a run.log` 中，bash 默认返回管道最后一个命令（tee）的 exit code，即使 python 失败也会报告 exit_code=0。这会破坏现有的 `_extract_execute_fact` → `exit_code != 0` 失败检测链路。

   **解决**：使用 `set -o pipefail`，让管道返回第一个非零 exit code。命令变为：
   ```bash
   set -o pipefail; python solution.py 2>&1 | tee -a run.log
   ```
   `pipefail` 是 bash 标准特性，Claude Agent SDK 的 Bash 工具使用 bash 执行命令，应正确支持。

   **受影响链路验证**：
   - `_extract_execute_fact()` 从 `tool_call.result` 中取 `exit_code` → 不受影响，tee + pipefail 正确传播 exit_code
   - `_persist_exec_log()` 写入 DB → 不受影响
   - `exit_code != 0` 分支 → 不受影响，失败时仍能正确 raise
   - stdout/stderr 内容 → tee 不改变终端输出内容，turns 中的 stdout/stderr 不受影响

3. **追加模式 (`tee -a`)**
   Agent 可能在 execute 阶段多次调试运行 solution.py，用 `-a` 追加所有运行记录。

## 1.3 伪代码 / 数据流

```text
draft_execute.j2 新增指令:
  "运行 solution.py 时，使用以下命令确保日志同时写入文件:
   set -o pipefail; python solution.py 2>&1 | tee -a run.log"

数据流:
  Agent execute phase
    ├── 写 solution.py 到 working/
    ├── Bash(cwd=working/):
    │     set -o pipefail; python solution.py 2>&1 | tee -a run.log
    │     ├── stdout+stderr → 终端输出（被 turns 捕获，与之前一致）
    │     ├── stdout+stderr → working/run.log（实时写入）
    │     └── exit_code = python 的 exit_code（pipefail 保证）
    └── _handle_execute_response 后续流程完全不变

人类观察:
  tail -f workspace/working/run.log  # 实时看到训练输出
```

## 1.4 拟议变更（Proposed Changes）

### A. Workspace 新增 run_log_path

- `core/workspace.py` [MODIFY]
  - [NEW] `run_log_path` 属性 → 返回 `self.working_dir / "run.log"`
  - [MODIFY] `summary()` → 新增 `"run_log_path": str(self.run_log_path)` 键

### B. 修改 draft_execute 模板

- `config/prompts/templates/draft_execute.j2` [MODIFY]
  - 在"工作空间"部分新增 `run_log_path` 展示
  - 在"执行要求"→"代码要求"部分新增日志约束：
    ```
    - 运行 solution.py 时，必须使用以下命令将输出同时保存到日志文件，方便人类实时观察:
      `set -o pipefail; python solution.py 2>&1 | tee -a {{ workspace.run_log_path }}`
    ```

### C. 测试

- `tests/unit/test_run_logging.py` [NEW]
  - `test_run_log_path_property`：验证 `Workspace.run_log_path == working_dir / "run.log"`
  - `test_workspace_summary_contains_run_log_path`：验证 `summary()` 含 `run_log_path` 键
  - `test_draft_execute_prompt_contains_tee_and_run_log`：渲染 `draft_execute.j2` 并验证输出含 `tee` 指令和 `run.log` 路径
  - `test_draft_execute_prompt_contains_pipefail`：验证 prompt 中含 `set -o pipefail`

- `tests/integration/test_run_log_flow.py` [NEW]
  - `test_prompt_assembles_run_log_path`：构造完整 DraftPES 并验证 prompt context 正确包含 `run_log_path`

## 1.5 验证计划

1. `pytest tests/unit/test_run_logging.py -v`
2. `pytest tests/integration/test_run_log_flow.py -v`
3. `pytest tests/ -v` — 回归验证
4. 检查点（对应 TD.md §6.17）：
   - 存在 `workspace/working/run.log`
   - `tail -f run.log` 可实时看到 solution.py 训练输出
   - `set -o pipefail` 保证 exit_code 正确传播，不影响现有失败检测
   - 现有 `exec_logs`、`llm_calls`、工件持久化和回放不受影响
