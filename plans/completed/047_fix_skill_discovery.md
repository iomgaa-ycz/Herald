# 047: 修复 plan/summarize 阶段 skill 不可发现

## 1.1 摘要

两个问题导致 plan/summarize 阶段的 project skill 完全失效：

1. **`cwd` 未设置**：`build_phase_model_options` 只给 execute phase 设置 `cwd=workspace/working/`，plan/summarize 阶段的 Claude Code CLI 在项目根目录运行，SDK 扫描 `.claude/skills/` 时找不到 `draft-history-review` 等 skill（项目根只有 `skill-creator`）。
2. **plan 阶段缺少 `Skill` 工具**：即使 SDK 发现了 skill，agent 也需要通过 `Skill` 工具调用它来读取完整的 SKILL.md 指引。当前 plan 的 `allowed_tools` 是 `["Bash", "Read", "Glob", "Grep"]`，不含 `Skill`。

结果：Agent 每次输出 `draft-history-review skill 不存在，跳过`，差异化规划彻底失效，Draft 2 直接复用 Draft 1 的 solution.py（MD5 完全相同）。

## 1.2 审查点

- [ ] 给 plan/summarize 传 `cwd` 时是否也需要传 `env.HERALD_DB_PATH`？（plan 阶段的 skill 需要调用 `python core/cli/db.py get-l2-insights --db-path <path>`，需要知道 db_path）

## 1.3 当前 vs 新流程

### 当前（只有 execute 拿到 cwd）
```
build_phase_model_options(phase):
  if phase != "execute":  → return {}        # plan/summarize: cwd=None → SDK 用项目根
  return {cwd: working_dir, env: {DB_PATH}}  # execute: cwd=working/ → 能发现 .claude/skills/
```

Claude Code CLI 启动时按 `cwd` 查找 `.claude/skills/`：
- execute: `workspace/working/.claude/skills/` → 5 个 skill 全部可见
- plan:    项目根 `.claude/skills/` → 只有 skill-creator，draft-history-review 不可见
- summarize: 同 plan

### 修改后（所有 phase 共享 cwd）
```
build_phase_model_options(phase):
  if workspace is None:  → return {}
  base = {cwd: working_dir, env: {DB_PATH}}
  if phase == "execute":
    # execute 阶段的 env 可按需扩展
    pass
  return base
```

## 1.4 拟议变更

### `core/pes/draft.py` [MODIFY]

#### `build_phase_model_options` (line 22-44)

将 `if phase != "execute"` 守卫改为 `if self.workspace is None`，使所有 phase 都拿到 `cwd` 和 `env`。

变更前：
```python
def build_phase_model_options(self, phase, solution, parent_solution):
    del solution, parent_solution
    if phase != "execute" or self.workspace is None:
        return {}
    working_dir = getattr(self.workspace, "working_dir", None)
    db_path = getattr(self.workspace, "db_path", None)
    if working_dir is None or db_path is None:
        return {}
    return {
        "cwd": str(working_dir),
        "env": {"HERALD_DB_PATH": str(db_path)},
    }
```

变更后：
```python
def build_phase_model_options(self, phase, solution, parent_solution):
    del phase, solution, parent_solution
    if self.workspace is None:
        return {}
    working_dir = getattr(self.workspace, "working_dir", None)
    db_path = getattr(self.workspace, "db_path", None)
    if working_dir is None or db_path is None:
        return {}
    return {
        "cwd": str(working_dir),
        "env": {"HERALD_DB_PATH": str(db_path)},
    }
```

docstring 从 `为 execute phase 提供工作目录与环境变量` 改为 `为所有 phase 提供工作目录与环境变量`。

### `config/pes/draft.yaml` [MODIFY]

plan 阶段 `allowed_tools` 增加 `Skill`，使 agent 能调用 `Skill` 工具读取 skill 内容。

变更前：
```yaml
  plan:
    template_name: null
    tool_names: []
    max_retries: 1
    allowed_tools: ["Bash", "Read", "Glob", "Grep"]
    max_turns: 3
```

变更后：
```yaml
  plan:
    template_name: null
    tool_names: []
    max_retries: 1
    allowed_tools: ["Bash", "Read", "Glob", "Grep", "Skill"]
    max_turns: 3
```

### 不变更的文件

| 文件 | 理由 |
|------|------|
| `core/pes/base.py` | cwd 传递链路无变化 |
| `core/llm.py` | cwd 参数处理无变化 |
| `core/prompts/skills/*` | skill 内容无变化 |
| 测试文件 | 现有测试不依赖 plan/summarize 阶段的 cwd 值和 allowed_tools |

## 1.5 验证计划

| 验证项 | 方法 | 预期 |
|--------|------|------|
| 单元测试 | `conda run -n herald pytest tests/unit/ -v` | 全部通过 |
| 集成测试 | `conda run -n herald pytest tests/integration/ -v` | 全部通过 |
| 端到端 | `bash scripts/run_real_l1.sh` | Draft 2/3 plan 输出不再含「skill 不存在」；3 个 draft solution.py MD5 互不相同 |

## 涉及文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `core/pes/draft.py` | MODIFY | `build_phase_model_options` 移除 phase 守卫，所有 phase 共享 cwd+env |
| `config/pes/draft.yaml` | MODIFY | plan 阶段 allowed_tools 增加 `Skill` |
