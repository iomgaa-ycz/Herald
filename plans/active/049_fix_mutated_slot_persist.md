# 049: 修复 mutated_slot 未持久化 + mutate fail-fast

## 1.1 摘要

修复三个 M1 遗留 bug：`mutated_slot` 未回填 DB、target_slot 解析失败时无 fail-fast、summarize 归因模糊。
根因是 solution 在 plan 之前写入 DB，plan 之后无人回填 `mutated_slot`；修复后问题 3 自动消解。

## 1.2 审查点

- 无需审查，已由用户批准方案 A（update_status 加参数）+ fail-fast 终止

## 1.3 调用流伪代码

```
BasePES.run()
  ├── create_solution()          → INSERT solutions (mutated_slot = NULL)
  ├── plan()
  │     └── MutatePES.handle_phase_response("plan")
  │           ├── _parse_target_slot()  → "FEATURE_ENG" 或 None
  │           ├── if None → raise RuntimeError (终止保留现场)  [NEW]
  │           ├── solution.target_slot = target_slot
  │           └── _persist_mutated_slot()                      [NEW]
  │                 └── db.update_solution_status(mutated_slot=target_slot)
  │                       └── UPDATE solutions SET mutated_slot = ? WHERE id = ?  [NEW]
  ├── execute_phase()
  └── summarize()   → mutate_summarize.j2 {{ target_slot }} 正确渲染
```

## 1.4 拟议变更

| 文件 | 函数 | 动作 |
|------|------|------|
| `core/database/repositories/solution.py` | `update_status()` | [MODIFY] 加 `mutated_slot: str \| None = None` 可选参数 |
| `core/pes/mutate.py` | `handle_phase_response()` plan 分支 | [MODIFY] 解析失败 raise RuntimeError |
| `core/pes/mutate.py` | `_persist_mutated_slot()` | [NEW] plan 后回填 DB |

## 1.5 验证计划

1. 现有单元测试全部通过
2. 下次 `run_real_l1.sh` 实跑后检查 `SELECT mutated_slot FROM solutions WHERE operation='mutate'` 不为空
