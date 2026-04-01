# 039 Draft Summarize 固定格式

## 元信息
- 状态: completed
- 创建: 2026-03-31
- 对应: TD.md §5.1 Task 1

## 目标

让 summarize 输出结构化、可解析、可被后续 draft 消费。

## 检查点
- [x] 新建 `core/prompts/skills/draft-summarize-format/SKILL.md` 定义五小节段落式格式
- [x] 重写 `config/prompts/templates/draft_summarize.j2`，引导 Agent 使用 Skill
- [x] 修改 `config/pes/draft.yaml`，summarize phase 开放 `Skill` 工具 + `max_turns: 2`
- [x] 更新测试（test_prompt_manager / test_llm_skill_config / test_draft_pes），全部通过
- [x] 修复 `test_load_draft_yaml_config` 中 execute phase allowed_tools 缺少 `Skill` 的预存断言错误

## 决策日志
- 2026-03-31: 采用 Skill + 开放工具方案（而非模板内嵌），与 `feature-extract-report-format` 保持一致 — 格式定义在 Skill 中，模板只做引导
- 2026-03-31: summarize phase 开放 `Skill` 工具 + `max_turns: 2` — 允许 Agent 一轮查看 Skill + 一轮输出

## 涉及文件

| 文件 | 变更类型 |
|------|----------|
| `core/prompts/skills/draft-summarize-format/SKILL.md` | NEW |
| `config/prompts/templates/draft_summarize.j2` | MODIFY |
| `config/pes/draft.yaml` | MODIFY |
| `tests/unit/test_prompt_manager.py` | MODIFY |
| `tests/unit/test_llm_skill_config.py` | MODIFY |
| `tests/unit/test_draft_pes.py` | MODIFY（修复预存断言错误）|
