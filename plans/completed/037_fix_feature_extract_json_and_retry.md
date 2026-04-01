# 037 修复 FeatureExtract JSON 解析失败 + 增加 stage 级重试

## 元信息
- 状态: active
- 创建: 2026-03-30
- 负责人: Claude

## Context

每次 PES 运行耗时 2-20 分钟。当前 FeatureExtract execute 阶段因 LLM 输出的 JSON 中含未转义引号导致解析失败，整个运行链路浪费。需要：
1. JSON 解析增加修复兜底
2. Scheduler 层面支持 stage 级重试，FeatureExtract 失败后自动重试（最多 3 次尝试）

## 1. 摘要

两层防御：
- **L1（解析层）**：`json.loads` 失败时 fallback 到 `json_repair.loads` 修复 LLM 输出的常见 JSON 错误
- **L2（调度层）**：Scheduler 支持 stage 级 `max_retries`，FeatureExtract 失败后自动重新运行整个 PES（最多重试 2 次）

## 2. 审查点

- 重试时是否需要创建新 solution？**是**，每次重试都是一次独立的 PES.run()
- 重试时上下文是否变化？**不变**，使用相同的 dispatch context
- Draft PES 不做修改

## 3. 流程图

```
修复后链路：

FeatureExtractPES.execute
  → _parse_structured_output(response_text)
  → json.loads(json_text)  ❌ JSONDecodeError
  → json_repair.loads(json_text)  ✅ 修复成功（L1 拦住）
  → 继续正常流程 → 生成 task_spec.json + data_profile.md

若 L1 修复也失败（或其他原因导致 PES 失败）：
  → emit(TaskCompleteEvent, status="failed")
  → Scheduler 检测失败，attempt < max_retries
  → 重新 dispatch 同一 stage 的任务（L2 重试）
  → 新的 FeatureExtractPES.run() 启动
  → 最多重试 2 次（共 3 次尝试）

若 3 次全部失败：
  → 继续执行下一个 stage（Draft），保持当前行为
  → （Draft 有自己的错误处理机制）
```

## 4. 拟议变更

### 变更 1: JSON 解析鲁棒化 `[MODIFY]`

**文件**: `core/pes/feature_extract.py`
**函数**: `_parse_structured_output()`

```python
def _parse_structured_output(self, text: str) -> dict[str, Any]:
    matches = _JSON_BLOCK_RE.findall(text)
    if not matches:
        raise ValueError("LLM 输出中未找到 JSON code block")

    json_text = matches[-1].strip()

    # L1: 标准解析
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as first_error:
        # L1 fallback: json_repair
        logger.warning("JSON 标准解析失败，尝试修复: %s", first_error)
        try:
            from json_repair import repair_json
            repaired = repair_json(json_text, return_objects=True)
        except Exception as repair_error:
            raise ValueError(
                f"JSON 解析失败且修复无效: 原始={first_error}"
            ) from repair_error
        if not isinstance(repaired, dict):
            raise ValueError(
                f"修复后 JSON 非对象: {type(repaired).__name__}"
            ) from first_error
        parsed = repaired
        logger.info("JSON 修复成功")

    if not isinstance(parsed, dict):
        raise ValueError(f"JSON 顶层必须是对象，实际: {type(parsed).__name__}")
    return parsed
```

**新增依赖**: `requirements.txt` 添加 `json-repair`

### 变更 2: Scheduler stage 级重试 `[MODIFY]`

**文件**: `core/scheduler/scheduler.py`

核心改动：`_run_stage()` 支持单任务失败后重试。

```python
# __init__ 新增参数
stage_max_retries: dict[str, int] | None = None
# 例如: {"feature_extract": 2}  → 最多重试 2 次

# _run_stage 内部逻辑变更（伪代码）
async def _run_stage(self, stage_name, count, start_generation) -> int:
    max_retries = self._stage_max_retries.get(stage_name, 0)

    generation = start_generation
    for _ in range(count):
        success = False
        for attempt in range(1 + max_retries):
            self._dispatch_task(index=generation, task_name=stage_name)
            await self._wait_current_task()
            self._completed_count += 1

            if self._last_task_status == "completed":
                success = True
                break
            elif attempt < max_retries:
                logger.warning(
                    "stage '%s' 任务失败，重试 (%d/%d)",
                    stage_name, attempt + 1, max_retries,
                )
            generation += 1

        if success:
            generation += 1

    self._merge_stage_outputs()
    return generation
```

需要在 `_on_task_complete` 中记录 `_last_task_status`。

### 变更 3: 配置注入 `[MODIFY]`

**文件**: `core/main.py`（bootstrap 调用处）

```python
Scheduler(
    ...,
    task_stages=[("feature_extract", 1), ("draft", 1)],
    stage_max_retries={"feature_extract": 2},  # 新增
)
```

## 5. 验证计划

1. **安装依赖**: `pip install json-repair`
2. **单元测试**: 构造含未转义引号的 JSON 字符串，验证 `_parse_structured_output` 修复成功
3. **集成验证**: 重新运行 `bash scripts/run_real_l1.sh`，确认 `workspace/working/` 下生成 `task_spec.json` 和 `data_profile.md`
4. **代码检查**: `ruff check . && ruff format .`

## 涉及文件

- `core/pes/feature_extract.py` — JSON repair fallback
- `core/scheduler/scheduler.py` — stage 级重试
- `core/main.py` — 注入 `stage_max_retries` 配置
- `requirements.txt` — 新增 `json-repair`
