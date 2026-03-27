# 009: 将 tools.py 工具集改造为 CLI 子命令

## 元信息
- 状态: draft
- 创建: 2026-03-27
- 更新: 2026-03-27
- 负责人: Claude

## 1.1 摘要

008 将 `LLMClient` 迁移至 Claude Agent SDK 后，`core/tools.py` 的工具注入机制（Python 函数列表 → `call_with_tools()`）已失效；Agent SDK 通过 `allowed_tools=["Bash", ...]` 字符串列表控制工具，根本不接受 Python 函数。参考《MCP is dead. Long live the CLI》的核心论点：将工具改造为 CLI 命令，Agent 通过 Bash 调用，人类也可直接调试，无需任何注入机制。本次将 `tools.py` 的 5 个工具函数迁移为 `core/main.py` 的 `db` 子命令，并删除旧的工厂模式。

## 1.2 审查点（Review Required）

| # | 决策项 | 当前倾向 | 说明 |
|---|--------|----------|------|
| 1 | `core/main.py` 是否改造为 argparse subparsers | 是 | 原有 `main()` 逻辑包裹为 `run` 子命令，新增 `db` 子命令组 |
| 2 | db 子命令的 DB 路径如何获取 | `--db-path` 参数 | 最简单，Agent 调用时显式传入；也支持 `HERALD_DB_PATH` 环境变量 fallback |
| 3 | CLI 输出格式 | JSON 到 stdout | 方便 Agent 解析，也支持 `jq` 管道处理 |
| 4 | 是否完全删除 `core/tools.py` | 是 | 旧工厂模式完全废弃，不保留兼容层 |
| 5 | `query_l2` 是否也实现为 CLI 命令 | 否（跳过） | 该函数原本就是 `NotImplementedError`，等数据库逻辑就绪后再加 |

## 1.3 流程图

```
旧方案（008前）：
BasePES → create_tools(db) → [Python函数列表] → LLMClient.call_with_tools(tools=[...])

新方案（009后）：
DraftPES.execute() → LLMClient.execute_task(
                         allowed_tools=["Bash"],
                         cwd=workspace.root
                     )
                       ↓
               Claude Agent (CLI subprocess)
                       ↓ Bash 调用
  python -m core.main db query-lineage --slot MODEL --db-path /path/to/db
  python -m core.main db get-population-summary --db-path /path/to/db
  python -m core.main db read-gene-code --solution-id <uuid> --slot MODEL --db-path ...
  python -m core.main db write-l2-insight --slot MODEL --task-type tabular_ml \
      --pattern "..." --support --solution-id <uuid> --db-path ...

输出均为 JSON → stdout（Agent 直接读取，或 | jq 过滤）
```

## 1.4 拟议变更（Proposed Changes）

### core/cli/__init__.py [NEW]
- 空初始化文件，使 `cli/` 成为包

### core/cli/db.py [NEW]
- 独立可执行脚本，供 Agent 通过 Bash 直接调用：`python core/cli/db.py <subcommand> [args]`
- `_parse_args()` — argparse subparsers，定义 4 个子命令
- `cmd_query_lineage(args)` — 调用 `HeraldDB.get_slot_history(slot)`，输出 JSON
- `cmd_get_population_summary(args)` — 调用 `HeraldDB.get_population_summary()`，输出 JSON
- `cmd_read_gene_code(args)` — 调用 `HeraldDB.get_full_code()` + `_extract_gene_region()`，输出 JSON
- `cmd_write_l2_insight(args)` — 调用 `HeraldDB.upsert_l2_insight()`，输出 JSON
- `_get_db(args)` — 从 `args.db_path` 或 `HERALD_DB_PATH` 环境变量初始化 `HeraldDB`
- `_extract_gene_region(code, slot)` — 从 `tools.py` 直接迁移的纯函数
- `if __name__ == "__main__": main()` 入口

### core/tools.py [DELETE]
- 旧工厂模式（`create_tools`, `create_query_lineage` 等）完全删除

### core/main.py [NO-CHANGE]
- 不动

## 1.5 验证计划（Verification Plan）

1. 手工验证（smoke test）
   ```bash
   python core/cli/db.py get-population-summary --db-path /tmp/test.db
   python core/cli/db.py query-lineage --slot MODEL --db-path /tmp/test.db
   ```
   期望：输出合法 JSON，无 traceback

2. `ruff check . --fix && ruff format .` 通过
3. 原有引用 `core.tools` 的代码（如有）全部清理后，无 ImportError

## 2. 实施边界

- 只做工具的 CLI 改造，不涉及 DraftPES 如何调用工具
- 不实现 `query_l2`（原本就 NotImplementedError）
- 不改动 `HeraldDB` 内部逻辑
- 不改动 `core/main.py`
- 不涉及 Agent 侧的 `allowed_tools` 配置（由后续 skills 机制处理）
