# Herald2 当前调用链路（016 之后状态）

## 1. `main.py` 到 `DraftPES.run()`

```text
main.py
  │
  ├── ConfigManager.parse()                     ✅
  ├── Workspace.create()                        ✅
  ├── HeraldDB(...)                             ✅
  ├── EventBus.get()                            ✅
  ├── setup_task_dispatcher()                   ✅
  ├── bootstrap_draft_pes(...)                  ✅ 016 已补齐
  │      │
  │      ├── load_pes_config("config/pes/draft.yaml")   ✅
  │      ├── importlib.import_module("core.llm")        ✅
  │      ├── LLMClient(...)                             ✅
  │      ├── DraftPES(...)                              ✅
  │      └── BasePES.__init__()
  │             ├── PESRegistry.register(self)          ✅
  │             └── EventBus.on(TaskExecuteEvent, ...)  ✅
  │
  └── Scheduler.run()                           ✅
          │
          ▼
    Scheduler._dispatch_task()
          │
          ▼
    EventBus.emit(TaskDispatchEvent)            ✅
          │
          ▼
    TaskDispatcher.handle_dispatch()            ✅
          │
          ├── AgentRegistry.load()              ✅
          └── PESRegistry.get_by_base_name("draft")  ✅ 可找到 `draft#001`
                  │
                  ▼
            EventBus.emit(TaskExecuteEvent)     ✅
                  │
                  ▼
            DraftPES.on_execute()               ✅
                  │
                  ▼
            asyncio.create_task(DraftPES.run()) ✅
```

## 2. `DraftPES.run()` 内部链路

```text
DraftPES.run()
    │
    ├── plan()                                  ✅
    │    ├── render_prompt()                    ✅
    │    ├── draft_plan.j2                      ✅
    │    └── LLMClient.execute_task()           ✅
    │
    ├── execute_phase()                         ✅
    │    ├── render_prompt()                    ✅
    │    ├── draft_execute.j2                   ✅
    │    └── LLMClient.execute_task()           ✅
    │
    └── summarize()                             ✅
         ├── render_prompt()                    ✅
         ├── draft_summarize.j2                 ✅
         ├── LLMClient.execute_task()           ✅
         └── EventBus.emit(TaskCompleteEvent)   ✅
```

## 3. 从 `DraftPES.run()` 到“真实 `solution.py`”仍不通的断点

```text
DraftPES.run()
    │
    ├── handle_phase_response("execute")
    │       │
    │       ├── solution.execute_summary = response_text   ✅
    │       └── _attach_workspace_artifacts()              ⚠️
    │               │
    │               ├── working_dir.mkdir(...)             ✅
    │               ├── solution.workspace_dir = ...       ✅
    │               ├── solution.solution_file_path = ...  ✅
    │               └── solution.py.touch()                ❌ 只建空文件
    │
    └── handle_phase_response("summarize")
            └── TaskCompleteEvent                          ✅
```

### 当前剩余主问题

1. 断点 B：`task_spec/schema` 仍未注入运行时上下文
   - `draft_plan.j2`、`draft_execute.j2` 支持 `task_spec/schema/workspace`
   - 当前生产链路只注入了最小 `competition_dir`
   - Prompt 仍会退化为“基于最小假设继续”

2. 断点 C：`execute` 阶段没有把模型产出的代码落盘到 `working/solution.py`
   - 当前只把 `response.result` 记到 `solution.execute_summary`
   - 然后 `touch()` 一个空的 `solution.py`
   - 因此 `DraftPES.run()` 跑完不等于得到真实可执行代码

3. 断点 D：缺少“代码提取 -> 落盘 -> 执行验证 -> 版本保存”闭环
   - 尚未从 `draft_execute` 响应中解析代码块
   - 尚未调用 `Workspace.save_version()`
   - 尚未更新 `best/solution.py`
   - 尚未形成真实产物沉淀链路

## 4. 当前状态总结

| 组件 | 状态 | 说明 |
|------|------|------|
| `main.py` 初始化 | ✅ | 配置、工作空间、数据库、事件总线已启动 |
| `Scheduler` | ✅ | `015` 已补齐 `TaskDispatchEvent` 触发点 |
| `main.py -> DraftPES` 装配 | ✅ | `016` 已显式装配并注册 `DraftPES` |
| `TaskDispatcher` | ✅ | 可把 `TaskDispatchEvent` 转成 `TaskExecuteEvent` |
| `DraftPES.on_execute()/run()` | ✅ | 生产链路已可到达 |
| Prompt 模板链路 | ✅ | `draft_plan/draft_execute/draft_summarize` 可渲染 |
| `TaskCompleteEvent` | ✅ | 调度闭环已补齐 |
| `task_spec/schema` 注入 | ❌ | Prompt 仍缺真实任务规格上下文 |
| 真实 `solution.py` 写入 | ❌ | 当前只 `touch()` 空文件 |
| 代码执行验证与版本沉淀 | ❌ | 尚未接到 `Workspace.save_version()/promote_best()` |

## 5. 一句话结论

现在 `main.py -> Scheduler -> TaskDispatcher -> DraftPES.run()` 主链路已经打通；当前真正剩下的阻塞点，不再是“没有人执行 DraftPES”，而是“DraftPES 还不能把 execute 输出沉淀成真实可运行的 `working/solution.py`”。
