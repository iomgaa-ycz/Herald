# 041 CLI 新增 list-drafts / get-draft-detail / get-l2-insights

## 元信息
- 状态: completed
- 创建: 2026-04-01
- 对应: TD.md §5.3 Task 3

## 目标

让 Agent 能通过 Bash 按需查询历史 draft 和 L2 经验。

## 检查点
- [x] `SolutionRepository.list_by_run_and_operation()` 新增
- [x] `HeraldDB.list_solutions_by_run_and_operation()` 便捷方法新增
- [x] `cmd_list_drafts` — 列出 draft 简报，含 `summary_excerpt`
- [x] `cmd_get_draft_detail` — 返回完整 `summarize_insight`
- [x] `cmd_get_l2_insights` — 返回 L2 经验列表（insight 截断 500 字符）
- [x] argparse subparser 注册 + `_COMMANDS` 映射
- [x] `tests/unit/test_cli_db.py` 新建（5 个用例全部通过）
- [x] ruff format 通过
- [x] 已有测试不受影响（失败项为历史遗留，与本次变更无关）

## 决策日志
- 2026-04-01: `summary_excerpt` 复用 `core/utils/text.py::extract_summary_excerpt()`（与 Task 2 的 L2 pattern 提取共用），040 计划已确认此设计
- 2026-04-01: `get-l2-insights` 固定 `slot="strategy"`（MVP 阶段方案级，不做 slot 拆分）
- 2026-04-01: `list-drafts` 通过 `HeraldDB.list_solutions_by_run_and_operation()` 调用，而非直接调 repo，保持门面一致性

## 涉及文件

| 文件 | 变更类型 |
|------|----------|
| `core/database/repositories/solution.py` | MODIFY |
| `core/database/herald_db.py` | MODIFY |
| `core/cli/db.py` | MODIFY |
| `tests/unit/test_cli_db.py` | NEW |
