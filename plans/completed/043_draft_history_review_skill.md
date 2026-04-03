# 043 新建 draft-history-review Skill

## 元信息
- 状态: completed
- 创建: 2026-04-02
- 对应: TD.md §5.4 Task 4

## 目标

创建 `core/prompts/skills/draft-history-review/SKILL.md`，指导 Agent 在 draft plan 阶段查询前序 draft 经验（通过 `get-l2-insights` CLI）并规划差异化方向。

## 检查点
- [x] `core/prompts/skills/draft-history-review/SKILL.md` 创建
- [x] Frontmatter description 包含 plan 阶段触发词
- [x] CLI 示例参数与 `core/cli/db.py` argparse 定义一致
- [x] 三层操作步骤：必须查询 → 按需深查 → 差异化规划
- [x] 差异化维度与禁止事项明确
- [x] 空结果降级处理

## 涉及文件

| 文件 | 变更类型 |
|------|----------|
| `core/prompts/skills/draft-history-review/SKILL.md` | NEW |
