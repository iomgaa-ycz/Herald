# 修复 MutatePES 全链路失败 + Draft 差异化失效

## 元信息
- 状态: in_progress
- 创建: 2026-04-05
- 负责人: Agent

## 目标

修复首次真实 L1 运行中暴露的三类问题，使 mutate 阶段能跑通闭环、draft 差异化能生效。

## 1.1 摘要

本次 `run_real_l1.sh` 运行中：
- feature_extract 首次失败（`json_repair` 未安装），重试成功
- 3 个 draft 全部成功但代码/AUC 完全相同（差异化失效）
- 3 个 mutate 全部失败（plan 阶段崩溃，未进入 execute）

本计划修复 4 个具体缺陷：P0-a、P0-b、P1、P2。

## 1.2 审查点

- [x] P0-a（max_turns 不足）和 P0-b（正则不兼容 markdown）是独立问题，分别修复
- [x] P1（json_repair 缺失）仅需 pip install，无代码改动
- [x] P2 的修法是补全 MutatePES 的 env 注入 + 修改 skill 模板使用 `$HERALD_DB_PATH`，不做 L2 强制注入（避免与 skill 机制冲突）

## 1.3 调用链与修改点

### 当前 mutate plan 失败链路

```
Scheduler.dispatch("mutate")
  → MutatePES._run_from_event()
    → BasePES.run() → BasePES._run_phase("plan")
      → build_phase_model_options()          # ← BasePES 默认空实现，无 cwd/env
      → call_phase_model(env={})             # ← agent 无 HERALD_DB_PATH
      → LLM 执行 skill → Bash 查 L2         # ← db_path 由 LLM 猜测，猜错
      → ResultMessage.result                 # ← max_turns=3 耗尽，result 为空
      → handle_phase_response()
        → _extract_response_text() → ""
        → _parse_target_slot("") → None      # ← 或 result 非空但含 ** markdown
        → raise RuntimeError                 # ← 全部失败
```

### 修复后链路

```
Scheduler.dispatch("mutate")
  → MutatePES._run_from_event()
    → BasePES.run() → BasePES._run_phase("plan")
      → build_phase_model_options()          # [MODIFY] 返回 cwd + HERALD_DB_PATH
      → call_phase_model(max_turns=8, env={HERALD_DB_PATH: ...})
      → LLM 执行 skill → Bash 用 $HERALD_DB_PATH 查 L2  # skill 不再猜路径
      → ResultMessage.result                 # max_turns=8 足够产出文本
      → handle_phase_response()
        → _extract_response_text() → "..."
        → _parse_target_slot("**选中 Slot**: ...") → "FEATURE_ENG"  # [MODIFY] 正则兼容 **
        → 正常继续 execute 阶段
```

## 1.4 拟议变更

### P1: 安装 json_repair 依赖
- **操作**: `pip install json-repair>=0.58.0`
- **无代码变更**，requirements.txt 已有声明

### P0-a: mutate plan max_turns 过小
- `[MODIFY]` `config/pes/mutate.yaml` — `phases.plan.max_turns: 3 → 8`

### P0-b: _parse_target_slot 正则不兼容 markdown bold
- `[MODIFY]` `core/pes/mutate.py` — `_parse_target_slot()` 方法（约 271 行）
  - 当前: `r"选中\s*Slot\s*[:：]\s*[` ]?(\w+)[`]?"`
  - 修改: 在 `Slot` 和 `[:：]` 之间允许 `[*]*` markdown 标记
  - 同时在整个方法开头加 markdown strip 预处理（去除 `**`/`*`/`` ` ``），一劳永逸

### P2: MutatePES 缺少 cwd/env 注入 + skill db_path 占位符
- `[MODIFY]` `core/pes/mutate.py` — 新增 `build_phase_model_options()` 覆写
  - 复用 DraftPES 同款逻辑：返回 `cwd=working_dir`, `env={HERALD_DB_PATH: db_path}`
- `[MODIFY]` `core/prompts/skills/draft-history-review/SKILL.md`
  - 将命令模板从 `--db-path <db_path>` 改为 `--db-path $HERALD_DB_PATH`
  - 同理 `get-draft-detail` 命令也改为 `$HERALD_DB_PATH`

## 1.5 验证计划

1. **P1 验证**: `python -c "from json_repair import repair_json; print('OK')"`
2. **P0-a 验证**: 确认 `config/pes/mutate.yaml` plan.max_turns == 8
3. **P0-b 验证**: 单元测试 `_parse_target_slot`，覆盖以下输入：
   - `"选中 Slot: MODEL"` → `"MODEL"`（原有格式）
   - `"**选中 Slot**: \`FEATURE_ENG\`"` → `"FEATURE_ENG"`（markdown bold）
   - `"选中Slot：DATA"` → `"DATA"`（中文冒号无空格）
4. **P2 验证**:
   - 确认 `MutatePES.build_phase_model_options()` 返回含 `HERALD_DB_PATH` 的 env
   - 确认 skill 文件中 `--db-path $HERALD_DB_PATH` 替换完成
5. **集成验证**: 再跑一次 `bash scripts/run_real_l1.sh`，确认 mutate 阶段至少 1 个进入 execute

## 检查点

- [x] P1: json_repair 已安装（json-repair==0.58.7）
- [x] P0-a: mutate.yaml max_turns 已改为 8
- [x] P0-b: _parse_target_slot 正则已兼容 markdown（6 个用例全通过）
- [x] P2: MutatePES 继承 DraftPES.build_phase_model_options，HERALD_DB_PATH 已注入（无需额外代码）
- [x] P2: draft-history-review skill 已改用 $HERALD_DB_PATH
- [x] 单元测试通过（7 passed，1 个已有集成测试失败与本次无关）
- [ ] 集成运行 mutate 阶段不再全部失败

## 决策日志

- 2026-04-05: 不做 `_extract_response_text` turns 降级 — 用户明确不需要，max_turns 调大后 result 应有值
- 2026-04-05: 不做 L2 强制注入 `build_prompt_context` — 与现有 skill 查询机制冲突，修 db_path 即可
- 2026-04-05: max_turns 用 8 而非 5 — 用户指定，留更大余量
