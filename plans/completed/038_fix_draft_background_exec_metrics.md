# 038 修复 DraftPES 后台执行模式下 val_metric 提取失败

## 元信息
- 状态: active
- 创建: 2026-03-31
- 负责人: Claude

## Context

DraftPES execute 阶段 LLM 使用 `run_in_background` 模式运行 `python solution.py`，导致 tool call 的 `result.stdout` 只包含后台任务通知文本（`"Command running in background with ID: ..."`），而非程序实际输出。`_extract_val_metrics()` 在 stdout 中找不到 metrics → 抛出 `ValueError("首次运行成功，但未提取到 val_metric_value")`。

实际 metrics 输出（`{"metric_name": "auc", "metric_value": 0.975...}`）存在于 `workspace/working/run.log` 最后一行。

## 1.1 摘要

`_fill_exec_fact_from_runtime_artifacts()` 已有 stdout 补全机制（读 `stdout.log`），但触发条件是 `stdout in (None, "")`。后台模式下 stdout 非空（是通知文本），所以补全被跳过。

修复策略：**检测后台执行模式的 stdout 特征，将其视为"无效 stdout"触发 run.log fallback**。

## 1.2 审查点

- 是否需要新增 `run.log` 读取路径？**是**，`stdout.log` 不存在，但 `run.log` 是 LLM 通过 `tee` 写入的
- 是否影响同步执行模式？**不影响**，同步模式 stdout 不含后台通知前缀，不会触发清除逻辑

## 1.3 流程图

```
当前链路（失败）：
  _extract_execute_fact()
    → 匹配 Turn 17: cmd="python -u solution.py 2>&1 | tee run.log"
    → stdout = "Command running in background with ID: ..."
    → exit_code = 0（后台启动成功，非程序 exit code）
  _fill_exec_fact_from_runtime_artifacts()
    → stdout 非空（是通知文本），跳过补全
    → metrics.json 不存在，跳过
  _extract_val_metrics()
    → exec_result["metrics"] = None → 跳过
    → exec_result["stdout"] = 通知文本 → 解析无 metric → 抛异常

修复后链路：
  _extract_execute_fact()  → 同上
  _fill_exec_fact_from_runtime_artifacts()
    → 检测 stdout 含 "Command running in background" 前缀
    → 视为无效，清除为 None
    → 尝试读 stdout.log → 不存在
    → 尝试读 run.log → 成功，替换 stdout ✅
    → metrics.json 不存在，跳过
  _extract_val_metrics()
    → exec_result["stdout"] = run.log 完整内容
    → 逐行解析找到 {"metric_name": "auc", ...} → 提取成功 ✅
```

## 1.4 拟议变更

### 变更 1: 补全逻辑增强 `[MODIFY]`

**文件**: `core/pes/draft.py`
**函数**: `_fill_exec_fact_from_runtime_artifacts()` (line 360)

当前代码仅在 `stdout in (None, "")` 时补全，且只读 `stdout.log`。改为：
1. 检测后台任务通知文本，视为无效 stdout
2. fallback 链扩展：`stdout.log` → `run.log`

```python
def _fill_exec_fact_from_runtime_artifacts(
    self,
    exec_fact: dict[str, Any],
) -> dict[str, Any]:
    # ... 前置检查不变 ...

    filled_fact = dict(exec_fact)

    # 后台执行模式检测：stdout 包含后台任务通知，视为无效
    if self._is_background_task_output(filled_fact.get("stdout")):
        filled_fact["stdout"] = None

    # Phase 1: 补全 stdout（优先 stdout.log，fallback run.log）
    if filled_fact.get("stdout") in (None, ""):
        for artifact_name in ("stdout.log", "run.log"):
            content = read_artifact(artifact_name)
            if content not in (None, ""):
                filled_fact["stdout"] = content
                break

    # Phase 2: 补全 stderr（不变）
    if filled_fact.get("stderr") in (None, ""):
        filled_fact["stderr"] = read_artifact("stderr.log")

    # Phase 3: 加载 metrics.json（不变）
    metrics = self._load_metrics_artifact()
    if metrics is not None:
        filled_fact["metrics"] = metrics

    return filled_fact
```

### 变更 2: 新增后台输出检测 `[NEW]`

**文件**: `core/pes/draft.py`
**函数**: `_is_background_task_output()` (模块级常量 + 实例方法)

```python
_BACKGROUND_TASK_PREFIX = "Command running in background with ID:"

def _is_background_task_output(self, stdout: object) -> bool:
    """检测 stdout 是否为后台任务通知文本。"""
    if not isinstance(stdout, str):
        return False
    return stdout.strip().startswith(_BACKGROUND_TASK_PREFIX)
```

## 1.5 验证计划

1. **代码检查**: `ruff check core/pes/draft.py && ruff format core/pes/draft.py`
2. **集成验证**: 重新运行 `bash scripts/run_real_l1.sh`，确认 Draft 成功提取 metrics 并完成
3. **回归确认**: 同步执行模式不受影响（stdout 不含后台前缀时走原逻辑）

## 涉及文件

- `core/pes/draft.py` — `_fill_exec_fact_from_runtime_artifacts()` 增强 + 新增 `_is_background_task_output()`
