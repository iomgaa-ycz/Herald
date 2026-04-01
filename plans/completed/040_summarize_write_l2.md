# 040 Summarize 阶段写入 L2

## 元信息
- 状态: completed
- 创建: 2026-04-01
- 对应: TD.md §5.2 Task 2

## 目标

让每次 draft 的经验自动沉淀到 L2 知识层（`l2_insights` + `l2_evidence`）。

## 检查点
- [x] 新建 `core/utils/text.py`，实现 `extract_summary_excerpt` 公共函数
- [x] `core/pes/draft.py` 新增 `_get_task_type`、`_write_l2_knowledge`、`_build_failure_insight`
- [x] `handle_phase_response` summarize 分支调用 `_write_l2_knowledge`（成功路径 support）
- [x] `_handle_execute_response` 场景 4/5/6 暂存 `_l2_failure_context` 到 metadata
- [x] `handle_phase_failure` override，检测 `_l2_failure_context` 写 L2 contradict
- [x] 新建 `tests/unit/test_text_utils.py`（6 个用例全部通过）
- [x] 修改 `tests/unit/test_draft_pes.py` 新增 4 个 L2 测试（全部通过）
- [x] ruff check + format 通过

## 决策日志
- 2026-04-01: `extract_summary_excerpt` 放 `core/utils/text.py` 公共位置，Task 3 CLI 复用
- 2026-04-01: 失败场景 1/2/3（无代码/空/语法错）不写 L2，场景 4/5/6（运行失败/缺指标/submission 无效）写 contradict
- 2026-04-01: 失败路径 L2 insight 数据来自内存中的 exec_result（stderr/stdout）和 validation.errors，不额外读 workspace 文件

## 涉及文件

| 文件 | 变更类型 |
|------|----------|
| `core/utils/text.py` | NEW |
| `core/pes/draft.py` | MODIFY |
| `tests/unit/test_text_utils.py` | NEW |
| `tests/unit/test_draft_pes.py` | MODIFY |
