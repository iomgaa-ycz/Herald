# 033 修复 execute phase stdout 缓冲导致事实提取失败

## 元信息
- 状态: draft
- 创建: 2026-03-30
- 负责人: Claude

## 目标

修复 DraftPES execute phase 因 Python stdout 全缓冲导致 `run.log` 为空、Agent 无法从 tool turns 中提取运行事实而抛出 `ValueError: 未从 execute turns 中提取到 solution.py 的真实运行事实` 的问题。

## 问题分析

### 故障链路

```
draft_execute.j2 指示 Agent 执行:
  set -o pipefail; python solution.py 2>&1 | tee -a run.log
                                        ↑
                              管道模式触发 Python 全缓冲
                                        ↓
              stdout 全部缓存在内存 → run.log 始终 0 字节
                                        ↓
          Agent max_turns=12 用尽仍无输出 → _extract_execute_fact() 失败
```

### 根本原因

Python 在检测到 stdout 不是 tty（如管道 `| tee`）时，默认切换为**全缓冲**（block buffering），缓冲区通常 8KB。对于长时间运行的训练脚本（本例约 20+ 分钟），所有 `print()` 输出都积压在内存中，直到程序结束才 flush。

而 Claude Agent SDK 的 `max_turns=12` 限制下，Agent 在有限轮次内看到 Bash 工具调用结果为空（或超时），无法提取到 exit_code 和 stdout，导致 `_extract_execute_fact()` 遍历所有 turns 后抛出 ValueError。

## 修复方案

### 唯一变更点

**文件**: `config/prompts/templates/draft_execute.j2` (第 132 行)

```
# Before
set -o pipefail; python solution.py 2>&1 | tee -a {{ run_log_path }}

# After
set -o pipefail; python -u solution.py 2>&1 | tee -a {{ run_log_path }}
```

`python -u` 等价于 `PYTHONUNBUFFERED=1`，强制 stdout/stderr 为无缓冲模式，每次 `print()` 立即 flush 到管道。

### 为什么不选其他方案

| 方案 | 评估 |
|------|------|
| `python -u` (模板改一个字符) | ✅ **最简**，零代码改动，仅改 prompt 模板 |
| 环境变量 `PYTHONUNBUFFERED=1` 注入到 `build_phase_model_options()` | 可行但改动更大，且仅对 execute phase 有效需额外判断 |
| 在生成的 solution.py 中强制 `sys.stdout.reconfigure(line_buffering=True)` | 侵入生成代码，且依赖 Agent 正确插入 |
| 增大 `max_turns` 或超时 | 治标不治本，浪费 token |

## 拟议变更

| 操作 | 文件 | 说明 |
|------|------|------|
| `[MODIFY]` | `config/prompts/templates/draft_execute.j2:132` | `python` → `python -u` |

## 验证计划

1. 重新运行 `bash scripts/run_real_l1.sh`
2. 在 execute phase 运行期间检查 `workspace/working/run.log` 是否有实时输出
3. 确认 DraftPES execute phase 成功完成，`_extract_execute_fact()` 正常提取到 exit_code/stdout
4. 确认 `submission.csv` 正常生成
