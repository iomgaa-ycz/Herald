# 016: main.py 装配 DraftPES

## 元信息
- 状态: draft
- 创建: 2026-03-28
- 负责人: Codex

## 1.1 摘要

补齐 `main.py` 的生产级装配逻辑：在启动 `Scheduler` 之前，显式创建 `DraftPES`、`LLMClient` 与对应 `PESConfig`，让 `TaskDispatchEvent -> TaskExecuteEvent -> DraftPES.run()` 主链路真正可达。

本轮只解决“注册表里没有可调度的 `DraftPES` 实例”这一断点，不处理 `task_spec/schema` 注入，也不处理真实代码落盘。

## 1.2 审查点（Review Required）

| # | 决策项 | 当前倾向 | 说明 |
|---|--------|----------|------|
| 1 | 装配位置 | 直接放在 `core/main.py` | MVP 阶段保持显式，避免过早抽象工厂 |
| 2 | PES 配置来源 | 固定读取 `config/pes/draft.yaml` | 当前系统只支持 `draft` |
| 3 | 本轮边界 | 只打通到 `DraftPES.run()` | 不合并断点 B/C，避免计划失焦 |
| 4 | runtime_context 范围 | 仅注入最小字段 | 先只放 `competition_dir`，其余后续再补 |

## 1.3 流程图

```text
main.py
    │
    ├── ConfigManager.parse()
    ├── Workspace.create()
    ├── HeraldDB(...)
    ├── EventBus.get()
    ├── setup_task_dispatcher()
    │
    ├── load_pes_config("config/pes/draft.yaml")   [NEW]
    ├── LLMClient(...)                             [NEW]
    ├── DraftPES(...)                              [NEW]
    │      │
    │      ├── BasePES.__init__()
    │      │      ├── PESRegistry.register(self)
    │      │      └── EventBus.on(TaskExecuteEvent, self.on_execute)
    │      ▼
    │   draft#001 已注册
    │
    └── Scheduler.run()
           │
           ▼
      TaskDispatchEvent
           │
           ▼
      TaskDispatcher.handle_dispatch()
           │
           ▼
      PESRegistry.get_by_base_name("draft")   ✅ 可找到实例
           │
           ▼
      TaskExecuteEvent
           │
           ▼
      DraftPES.on_execute()
           │
           ▼
      DraftPES.run()
```

## 1.4 拟议变更（Proposed Changes）

### A. 在 `main.py` 增加 DraftPES 装配阶段

- [MODIFY] `core/main.py`
  - [MODIFY] 将 `HeraldDB(...)` 赋值到变量，供 PES 注入
  - [NEW] import `DraftPES`
  - [NEW] import `LLMClient`
  - [NEW] import `load_pes_config`
  - [NEW] 在 `Scheduler.run()` 前增加“PES 装配”阶段
  - [NEW] 显式创建：
    - `pes_config = load_pes_config("config/pes/draft.yaml")`
    - `llm_client = LLMClient(...)`
    - `draft_pes = DraftPES(...)`

参考形态：

```python
# Phase 5: 装配 DraftPES
db = HeraldDB(str(workspace.db_path))

pes_config = load_pes_config("config/pes/draft.yaml")
llm_client = LLMClient(
    LLMConfig(
        model=config.llm.model,
        max_tokens=config.llm.max_tokens,
        max_turns=config.llm.max_turns,
    )
)
draft_pes = DraftPES(
    config=pes_config,
    llm=llm_client,
    db=db,
    workspace=workspace,
    runtime_context={
        "competition_dir": config.run.competition_dir,
    },
)

# Phase 6: 启动调度器
scheduler = Scheduler(...)
scheduler.run()
```

### B. 明确 LLM 配置映射

- [MODIFY] `core/main.py`
  - [NEW] 将 `ConfigManager().parse()` 得到的 `config.llm` 映射到 `core.llm.LLMClient`
  - [NEW] 仅映射当前 `LLMClient` 已支持字段：
    - `model`
    - `max_tokens`
    - `max_turns`

说明：
- 若 `config.classconfig.llm.LLMConfig` 与 `core.llm.LLMConfig` 字段不完全一致，本轮只做最小显式映射
- 不在本轮统一配置类定义

### C. 保持 `PESRegistry` 纯注册职责

- [MODIFY] 无新增文件
- [NEW] 设计约束说明：
  - 不让 `PESRegistry` 负责创建 PES
  - 继续保持：
    - `main.py` 负责装配
    - `DraftPES/BasePES` 负责自注册
    - `TaskDispatcher` 负责查找并分发

### D. 为主链路补一条集成验证

- [MODIFY] `tests/integration/test_scheduler_flow.py`
  - [MODIFY] 可选增强：增加断言，验证 `PESRegistry.get_by_base_name("draft")` 在调度前非空

或

- [NEW] `tests/integration/test_main_bootstrap_flow.py`
  - [NEW] 最小主流程测试：
    - 初始化 `workspace/db/event_bus`
    - 装配 `DraftPES`
    - 启动单次调度
    - 验证 `DraftPES.received_execute_event` 非空

当前倾向：
- 优先复用现有 `test_scheduler_flow.py`
- 只有在 `main.py` 装配逻辑难以隔离时，再新增主流程测试

## 1.5 明确不做（Out of Scope）

- 不注入 `task_spec`
- 不注入 `schema`
- 不解析 `draft_execute` 返回的代码块
- 不写入真实 `working/solution.py` 内容
- 不接入 `Workspace.save_version()` / `promote_best()`
- 不新增 `PESFactory` / `BootstrapManager` / IoC 容器
- 不处理多 PES 类型动态装配

## 1.6 验证计划（Verification Plan）

1. **单元/装配级验证**
   - 调用装配后，`PESRegistry.get_by_base_name("draft")` 返回至少一个实例
   - 实例类型为 `DraftPES`

2. **集成测试**
   - 运行 `tests/integration/test_scheduler_flow.py`
   - 验证调度开始前已有可用 `draft` 实例
   - 验证 `TaskDispatchEvent` 最终能触发 `DraftPES.on_execute()`

3. **端到端验证**
   - 运行：
     ```bash
     python core/main.py --run_competition_dir=/path/to/competition --run_max_tasks=1
     ```
   - 观察日志包含：
     - DraftPES 装配完成
     - Scheduler 分发任务
     - DraftPES 收到执行事件
   - 程序可正常退出，不再出现 `PES 实例不存在`

## 2. 实施边界

- 本轮只装配一个 `DraftPES` 实例
- 本轮只支持 `draft` 任务名
- 本轮不引入工厂层
- 本轮优先显式、可读、可追踪，不追求通用化

## 3. 风险与缓解

| 风险 | 缓解 |
|------|------|
| `main.py` 直接装配导致入口继续膨胀 | MVP 接受；待出现第二种 PES 再抽工厂 |
| `core.llm.LLMConfig` 与全局配置类字段不一致 | 在 `main.py` 做显式字段映射，避免隐式耦合 |
| `DraftPES` 虽已注册，但后续 Prompt/代码产物仍不完整 | 明确本轮只解决断点 A，不承诺真实 `solution.py` 产出 |
| 端到端测试依赖外部模型环境 | 集成测试优先验证“实例存在 + 事件可达”，E2E 只做补充 |

## 4. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `core/main.py` | MODIFY | 增加 `DraftPES` / `LLMClient` / `PESConfig` 装配 |
| `tests/integration/test_scheduler_flow.py` | MODIFY | 增加“调度前已注册 DraftPES”验证，或复用现有链路验证 |

## 5. 待审核结论

建议按本计划执行。核心不是改造 `PESRegistry`，而是补齐 `main.py` 的 bootstrap 责任：显式创建并注册 `DraftPES`，让 `015_scheduler` 补上的调度链路真正落到 `DraftPES.run()`。
