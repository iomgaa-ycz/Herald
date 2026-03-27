# 012: PromptManager 加载 Draft 模板并打通 DraftPES

## 元信息
- 状态: in_progress
- 创建: 2026-03-28
- 更新: 2026-03-28
- 负责人: Codex

## 1.1 摘要

本轮目标是让 `PromptManager` 能稳定加载 `draft_plan.j2`、`draft_execute.j2`、`draft_summarize.j2`，并让 `DraftPES.run()` 在不关心真实业务输出的前提下完整走完 `plan -> execute -> summarize` 三阶段。

本轮坚持 MVP：只打通链路，不做真实解析，不追求高质量输出；凡是流程上需要但内容暂时不重要的文件，一律按空占位思路处理。

## 1.2 审查点（Review Required）

| # | 决策项 | 当前倾向 | 说明 |
|---|--------|----------|------|
| 1 | `DraftPES` phase 响应如何处理 | 最小落盘/挂载到 solution | 不解析结构化协议，只保证 run 不失败 |
| 2 | 是否改动 `PromptManager` 主逻辑 | 否，优先不动 | 当前 manager 已能按 `operation + phase` 取模板 |
| 3 | 涉及的 `.md` 文件如何处理 | 缺失则创建空文件 | 不清空已有共享文档，避免影响其他链路 |

## 1.3 拟议变更（Proposed Changes）

### A. 确认 Draft 模板装配链路

- [VERIFY] `config/prompts/prompt_spec.yaml`
  - 确保存在 `draft_plan`
  - 确保存在 `draft_execute`
  - 确保存在 `draft_summarize`
  - 三者都能被 `PromptManager.build_prompt()` 实际渲染到

### B. 让 `DraftPES.run()` 最小可跑

- [MODIFY] `core/pes/draft.py`
  - [MODIFY] `handle_phase_response()`
    - `plan`：写入 `solution.plan_summary`
    - `execute`：写入 `solution.execute_summary`
    - `summarize`：写入 `solution.summarize_insight`
    - `summarize` 结束时将 `solution.status` 标记为完成并写入完成时间
  - [NEW] 最小辅助函数
    - 统一提取响应文本
    - 在有 workspace 时挂载最小工件路径

### C. 增加真实运行冒烟测试

- [MODIFY] `tests/unit/test_draft_pes.py`
  - [MODIFY] 原占位异常测试，改为验证最小 phase 状态更新
  - [NEW] `test_draft_pes_run_with_real_prompt_manager()`
    - 使用真实 `PromptManager`
    - 验证三份 `draft_*.j2` 都会被渲染
    - 验证 `DraftPES.run()` 三阶段可完成

### D. `.md` 文件占位策略

- [VERIFY] 已被链路引用的 `.md` 文件是否存在
- [NEW] 缺失时创建空白占位文件
- [NO-CHANGE] 已存在的共享 `.md` 文件内容

## 1.4 验证计划（Verification Plan）

1. PromptManager 冒烟
   - `PromptManager.get_template_spec("draft", phase)` 成功
   - `build_prompt("draft", phase, context)` 三阶段均成功

2. DraftPES 冒烟
   - `DraftPES.run()` 能完整走完三阶段
   - `solution.status == "completed"`
   - `phase_outputs` 含 `plan/execute/summarize`

3. 参数透传
   - `execute` phase 仍能把 `cwd/env` 传给 LLM

4. `.md` 占位
   - 链路引用的 `.md` 文件均存在

## 1.5 风险

- 本轮只保证流程可运行，不保证 `plan/execute/summarize` 的语义质量
- `DraftPES` 当前仍未做结构化解析，后续若接正式协议需要再收敛字段
- “空白占位文件”策略只适合本研究期 MVP，不适合作为长期产物接口
