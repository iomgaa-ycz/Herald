---
name: mutate-diff-check
description: >-
  This skill should be used when the Mutate Agent needs to
  "verify mutation purity", "check code diff",
  "compare solution_parent.py with solution.py",
  "ensure only the target slot was modified", or
  "validate that non-target genes were not changed".
  Uses diff to verify that only the intended GENE region was modified.
---

# 变异纯度检查

在 `MutatePES.execute` 阶段完成代码修改后使用。

## 何时使用

- 完成 solution.py 编写后、提交最终输出前
- 需要确认只有目标 Slot 的 GENE 区域被修改

## 操作步骤

### Step 1: 执行 diff 对比

```bash
diff solution_parent.py solution.py || true
```

### Step 2: 分析 diff 输出

检查 diff 输出中的变更行：

1. **定位变更区域**：变更应全部在 `# === GENE:TARGET_SLOT_START ===` 和 `# === GENE:TARGET_SLOT_END ===` 标记之间
2. **检查非目标区域**：标记之外的代码不应有任何变化（import 调整除外）

### Step 3: 判断结果

- **纯净变异**：所有变更都在目标 Slot 标记区域内 → 直接继续
- **轻微溢出**：少量 import 语句变更（如新增模型依赖的 import） → 可接受，在执行报告中说明
- **严重溢出**：非目标 Slot 的 GENE 区域被修改 → 必须回退修改，只保留目标 Slot 的变更

## 注意事项

- `solution_parent.py` 是只读参考文件，**禁止修改**
- diff 输出为空表示没有任何变更，这是错误情况——说明变异未生效
- 如果 diff 发现问题，优先通过 Edit 工具精确修复，避免重写整个文件
