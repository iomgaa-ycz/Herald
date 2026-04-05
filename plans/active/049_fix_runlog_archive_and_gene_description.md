# 修复 run.log 归档与 genes description 填充

## 元信息
- 状态: draft
- 创建: 2026-04-04
- 负责人: Agent

## 目标

修复两个 M1 遗留缺陷：
1. run.log 是 append-only，导致 fitness 提取始终取到 gen1 的值
2. genes 表 description 为空，mutate plan 阶段缺少父方案的语义描述

## 审查点

- save_version 新增 run.log 归档+清空是否会影响 LLM Agent 正在运行时的行为？
  → 不会。save_version 发生在 summarize 阶段，此时 execute 阶段的 LLM Agent 已结束，不再写 run.log。

## 伪代码 / 嵌合说明

### Fix 1: run.log 归档

当前调用链：
```
summarize 阶段
  → _archive_completed_solution()
    → _archive_successful_solution()
      → workspace.save_version(code, submission, generation, solution_id)
          只写 solution.py + submission.csv 到 history/genX_xxx/
```

修改后：
```
workspace.save_version(code, submission, generation, solution_id)
  → 写 solution.py + submission.csv（不变）
  → 若 self.run_log_path 存在且非空：
      拷贝到 version_dir / "run.log"
      清空 self.run_log_path（truncate，而非删除——避免 tee -a 时文件不存在）
```

这样下一轮 execute 阶段 `tee -a run.log` 写入的是空文件，`_extract_val_metrics_from_stdout()` 只能读到当次运行的 JSON payload。

### Fix 2: genes description 填充

当前：
```python
# draft.py:785-789
gene_records = [
    {"slot": slot_name, "description": None, "code_anchor": slot_code[:200]}
    for slot_name, slot_code in genes.items()
]
```

修改后：
```python
# 用 solution.summarize_insight 作为所有 slot 的共享 description
shared_desc = (solution.summarize_insight or "")[:500]
gene_records = [
    {"slot": slot_name, "description": shared_desc, "code_anchor": slot_code[:200]}
    for slot_name, slot_code in genes.items()
]
```

截断 500 字符避免 DB 膨胀过快。所有 slot 共享同一 description（即本轮 summarize 的摘要）。

## 拟议变更

### `core/workspace.py` — `save_version()` `[MODIFY]`
- 在写完 solution.py + submission.csv 后，检查 `self.run_log_path` 存在且非空
- 拷贝到 `version_dir / "run.log"`
- 清空（truncate）`self.run_log_path`

### `core/pes/draft.py` — `_write_genes()` `[MODIFY]`
- 将 `description: None` 改为 `description: (solution.summarize_insight or "")[:500]`

### `tests/unit/test_workspace.py` — `[MODIFY]`
- 新增 `test_save_version_archives_and_clears_run_log`：验证 run.log 被拷贝到 history 并清空

### `tests/unit/test_draft_pes_write_genes.py` — `[MODIFY]`
- 修改 `test_write_genes_calls_insert_genes`：断言 description 不为 None，为 summarize_insight 内容

## 验证计划

1. 运行 `pytest tests/unit/test_workspace.py` — 含新增 run.log 归档测试
2. 运行 `pytest tests/unit/test_draft_pes_write_genes.py` — 验证 description 填充
3. 运行 `pytest tests/` — 全量回归
