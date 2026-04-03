# 042 合并 CLI — 删除 list-drafts，增强 get-l2-insights

## 元信息
- 状态: completed
- 创建: 2026-04-02
- 对应: TD.md §5.3.5 Task 3.5

## 目标

消除冗余 CLI 入口。删除 `list-drafts`，将其功能（fitness/metric/run-id 过滤）合并到 `get-l2-insights`。

## 检查点
- [x] `L2Repository.get_insights_with_solution_info()` 新增（含 1:1 防御检查）
- [x] `HeraldDB.get_l2_insights_with_solution_info()` 便捷方法新增
- [x] `cmd_list_drafts` 删除（函数 + argparse + _COMMANDS）
- [x] `cmd_get_l2_insights` 增强（调增强查询 + --run-id 参数）
- [x] 测试更新（删除 list-drafts 测试 + 更新/新增 get-l2-insights 测试）
- [x] ruff 通过
- [x] pytest tests/unit/test_cli_db.py 通过

## 涉及文件

| 文件 | 变更类型 |
|------|----------|
| `core/database/repositories/l2.py` | MODIFY |
| `core/database/herald_db.py` | MODIFY |
| `core/cli/db.py` | MODIFY |
| `tests/unit/test_cli_db.py` | MODIFY |
