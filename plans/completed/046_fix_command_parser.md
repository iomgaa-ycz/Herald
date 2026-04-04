# 046 修复 `_command_targets_solution_file` 嵌套命令解析失败

## 元信息
- 状态: draft
- 创建: 2026-04-03
- 对应: TD.md §5.6 端到端验证

## 背景

端到端运行中 3 个 draft 全部失败，错误：`执行事实未指向最终 solution.py：ls ...`。

**实际情况**：agent 行为完全正确——写出 solution.py 并成功执行（AUC 0.97+，run.log 非空，submission.csv 生成）。但 `_command_targets_solution_file` 无法识别 agent 使用的执行命令格式。

**根因**：agent 使用 `conda run -n herald bash -c "set -o pipefail; python -u solution.py 2>&1 | tee -a run.log"` 执行代码。`shlex.split()` 将 `bash -c` 的参数视为**单个 token**：

```
shlex.split 结果:
  [0] 'conda'
  [1] 'run'
  ...
  [7] 'set -o pipefail; python -u solution.py 2>&1 | tee -a run.log'
       ↑ 整个 bash -c 参数为一个 token，以 run.log 结尾
```

`part.endswith(".py")` 对所有 token 都返回 False → 验证器回退到第一个 Bash 命令（`ls`）→ 断言失败。

**证据（DB turns_json）**：

| Draft | Turn | 命令 | exit_code | 解析器检测结果 |
|-------|------|------|-----------|-------------|
| 1 (gen=1) | 6 | `conda run -n herald ... bash -c "... python -u solution.py ... \| tee -a run.log"` | 1 (首次崩溃) | ❌ 未识别 |
| 1 (gen=1) | 9 | 同上 | 0 (修复后成功) | ❌ 未识别 |
| 2 (gen=2) | 4 | `conda run -n herald bash -c '... python -u solution.py ... \| tee -a run.log'` | 0 | ❌ 未识别 |
| 3 (gen=3) | — | 未执行 solution.py（检测到前一 draft 遗留文件，误判为已完成） | — | — |

## 审查点

- [ ] 修复策略：对 `shlex.split` 产生的 compound token（含空格），做二次 whitespace split 展开。这样 `"... python -u solution.py ... | tee run.log"` → 展开后包含 `solution.py` → `endswith(".py")` 命中。是否认同此方案？
- [ ] 是否需要同时处理 `_extract_execute_fact` 中 `solution_path=None` 的调用路径（line 175）？当前 `_extract_execute_fact` 和 `_assert_execute_fact_matches_final_solution` 分别调用 `_command_targets_solution_file`，前者传 `None`，后者传真实路径——修复后两条路径都受益，无需额外改动。

## 1.3 现有调用链路与修复嵌合点

```
_handle_execute_response (line 86)
  ├── _extract_execute_fact(response)                    # line 99
  │     └── for each tool_call:
  │           _parse_exec_fact_from_tool_call(tc)        # 提取 command + exit_code
  │           _command_targets_solution_file(cmd, None)  # ← BUG: 嵌套命令未展开
  │           若匹配 → return fact
  │           否则 → fallback = 第一个 Bash fact
  │
  ├── _assert_execute_fact_matches_final_solution(...)   # line 100
  │     └── _command_targets_solution_file(cmd, Path)    # ← 同一 BUG
  │         若不匹配 → raise ValueError（当前报错点）
  │
  └── _fill_exec_fact_from_runtime_artifacts(...)        # line 101（不受影响）
```

**修复点**：仅需改 `_command_targets_solution_file` 一个方法，两条调用路径同时修复。

## 拟议变更

### `core/pes/draft.py` [MODIFY]

**变更方法**：`_command_targets_solution_file` (line 357-394)

在 `shlex.split` 后，对含空格的 compound token 做二次展开，将子 token 加入检查列表：

```python
def _command_targets_solution_file(
    self,
    command: str,
    solution_path: Path | None,
) -> bool:
    """判断命令是否在运行目标 solution.py。"""

    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()

    # 对嵌套命令（如 bash -c "... python solution.py ... | tee run.log"）
    # shlex 将 bash -c 参数视为单个 token，需二次展开
    expanded: list[str] = list(parts)
    for part in parts:
        if " " in part:
            expanded.extend(part.split())

    working_dir = getattr(self.workspace, "working_dir", None)
    workspace_dir = (
        Path(working_dir).resolve()
        if isinstance(working_dir, (str, Path))
        else None
    )
    expected_path = solution_path.resolve() if solution_path is not None else None

    for part in expanded:
        if not part.endswith(".py"):
            continue
        candidate = Path(part)
        if not candidate.is_absolute() and workspace_dir is not None:
            candidate = (workspace_dir / candidate).resolve()
        elif candidate.is_absolute():
            candidate = candidate.resolve()

        if expected_path is not None and candidate == expected_path:
            return True
        if (
            expected_path is None
            and candidate.name == self.config.solution_file_name
        ):
            return True

    return False
```

**改动最小化**：仅增加 4 行（`expanded` 构造 + 循环展开），其余逻辑不变。将 `for part in parts` 改为 `for part in expanded`。

### 不变更的文件

| 文件 | 理由 |
|------|------|
| `core/pes/base.py` | 无命令解析逻辑 |
| `core/pes/feature_extract.py` | 无 `_command_targets` 方法 |
| `config/pes/draft.yaml` | `max_turns: 12` 不调整 |
| `config/prompts/templates/draft_execute.j2` | prompt 已修改（上一轮），无需再改 |
| `core/llm.py` | 消息采集逻辑正确 |

## 验证计划

| 验证项 | 方法 | 预期 |
|--------|------|------|
| 单元验证 | Python 交互式测试，对实际 agent 命令调用修改后的方法 | 3 种命令格式均返回 True |
| 端到端 | `bash scripts/run_real_l1.sh` | draft 通过 execute → 进入 summarize → history 非空 |

### 单元验证用例

```python
# Case 1: 简单命令（原有逻辑已覆盖）
"python -u solution.py" → True

# Case 2: conda run + bash -c + tee（本次修复的核心场景）
'conda run -n herald bash -c "set -o pipefail; python -u solution.py 2>&1 | tee -a run.log"' → True

# Case 3: conda run + --no-capture-output（Draft 1 实际命令）
'conda run -n herald --no-capture-output bash -c "set -o pipefail; python -u solution.py 2>&1 | tee -a run.log"' → True

# Case 4: 非 solution.py 命令（不应误匹配）
"ls /workspace/data/ && ls /workspace/working/" → False
```

## 涉及文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `core/pes/draft.py` | MODIFY | `_command_targets_solution_file` 增加 compound token 展开 |
