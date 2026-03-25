# 006: Agent 与任务分离架构（事件流驱动）

## 元信息
- 状态: pending
- 创建: 2026-03-25
- 更新: 2026-03-25
- 负责人: Claude Agent

## 1. 摘要

实现 **事件流驱动** 的 Agent 与 PES 任务解耦基础设施。通过 EventBus 作为协调中心，实现多对多关系：调度器决策 → EventBus 协调 → AgentRegistry 提供数据 → PES 实例执行。**本次只实现基础设施，不包含具体任务类（DraftPES/MutatePES/EvolvePES）。**

## 2. 审查点

| # | 决策项 | 当前倾向 | 状态 |
|---|--------|----------|------|
| 1 | EventBus 通过 TaskExecuteEvent 路由到 PES | ✓ | 确认 |
| 2 | 本次不实现具体任务类 | ✓ | 确认 |
| 3 | PESRegistry 是否需要？ | 需要，管理实例生命周期 | 确认 |
| 4 | BasePES 调度入口是否复用现有 `execute()` | 否，新增 `on_execute()`，避免与三阶段 execute phase 冲突 | 确认 |

## 3. 架构设计

### 3.1 完整事件流

```
调度器 ──TaskDispatchEvent──▶ EventBus
                                   │
                    ┌──────────────┘
                    ▼ (1. 获取 AgentProfile)
              AgentRegistry.load()
                    │
                    ▼ (2. 组装 TaskExecuteEvent)
              EventBus
                    │
                    ▼ (3. 路由到特定 PES)
              特定 PES.on_execute(event)
                    │
                    ▼ (4. PES 自己调用)
              pes.run(agent_profile=event.agent)
```

### 3.2 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         事件流驱动架构                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   调度器                                                                     │
│     │                                                                       │
│     │ TaskDispatchEvent { task_name, agent_name, context }                 │
│     ▼                                                                       │
│   ┌─────────────────────┐                                                 │
│   │      EventBus       │                                                 │
│   │  发布/订阅通道       │                                                 │
│   └──────────┬──────────┘                                                 │
│              │                                                             │
│              ▼                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        TaskDispatcher                               │   │
│   │                                                                     │   │
│   │   1. 监听 TaskDispatchEvent                                        │   │
│   │   2. AgentRegistry.load(agent_name) → AgentProfile                 │   │
│   │   3. PESRegistry.get_by_base_name(task_name) → PES 实例             │   │
│   │   4. 组装 TaskExecuteEvent                                          │   │
│   │   5. EventBus.emit(TaskExecuteEvent)                                │   │
│   │                                                                     │   │
│   └───────────────┬───────────────────────────────┬─────────────────────┘   │
│                   │                               │                         │
│                   ▼                               ▼                         │
│       ┌─────────────────────┐         ┌─────────────────────┐              │
│       │   AgentRegistry     │         │    PESRegistry      │              │
│       │   (数据提供者)       │         │   (实例管理)         │              │
│       │                     │         │                     │              │
│       │  load() → Profile   │         │  register()         │              │
│       │  list_all()         │         │  get() → 实例       │              │
│       │  reload()           │         │  unregister()       │              │
│       └─────────────────────┘         └─────────────────────┘              │
│                                                                             │
│   ┌─────────────────────┐                                                   │
│   │      EventBus       │                                                   │
│   │  广播 TaskExecute   │                                                   │
│   └──────────┬──────────┘                                                   │
│              │                                                              │
│              ▼                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         PES 实例                                     │   │
│   │                                                                     │   │
│   │   BasePES.on_execute(event)  ◀── 接收 TaskExecuteEvent              │   │
│   │       └── 校验 event.target_pes_id == self._instance_id             │   │
│   │       └── 设置 self._current_agent = event.agent                    │   │
│   │       └── 调用 self.run(agent_profile=event.agent, ...)             │   │
│   │                                                                     │   │
│   │   build_prompt_context()                                            │   │
│   │       └── 注入 self._current_agent 到模板                           │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 组件职责

| 组件 | 职责 | 不负责 |
|------|------|--------|
| **AgentRegistry** | 加载配置、缓存、返回完整 AgentProfile | 决策、执行 |
| **PESRegistry** | 注册/查找/销毁 PES 实例 | 事件路由 |
| **EventBus** | 发布/订阅事件，不承载业务决策 | 查注册表、组装业务数据、执行 |
| **TaskDispatcher** | 消费 TaskDispatchEvent，协调两个 Registry，组装并发出 TaskExecuteEvent | 保存状态、执行 PES 逻辑 |
| **BasePES** | 监听与自己匹配的 TaskExecuteEvent、执行任务、构建上下文 | 调度决策、查找 Agent |
| **调度器** | 决定"哪个 Agent 执行哪个任务" | 数据加载、执行 |

### 3.4 核心接口

```python
# 后续任务类需要实现的接口
class BasePES(ABC):

    def on_execute(self, event: TaskExecuteEvent) -> None:
        """接收执行事件（由 EventBus 调用）

        流程：
        1. 若 event.target_pes_id != self._instance_id 则忽略
        2. 设置 self._current_agent = event.agent
        3. 调用 asyncio.create_task(self.run(agent_profile=event.agent))
        """
        ...

    async def run(
        self,
        agent_profile: AgentProfile,
        generation: int = 0,
        parent_solution: PESSolution | None = None,
    ) -> PESSolution:
        """实际执行逻辑（固定三阶段主流程）"""
        ...

    def build_prompt_context(...) -> dict[str, Any]:
        """构建 Prompt 上下文（包含 Agent 信息）"""
        ...
```

## 4. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `core/agent/__init__.py` | NEW | 模块入口 |
| `core/agent/profile.py` | NEW | AgentProfile 数据类 |
| `core/agent/registry.py` | NEW | AgentRegistry 注册表 |
| `core/pes/registry.py` | NEW | PESRegistry 注册表 |
| `core/events/dispatcher.py` | NEW | TaskDispatchEvent -> TaskExecuteEvent 转换器 |
| `core/events/types.py` | MODIFY | 新增 TaskDispatchEvent / TaskExecuteEvent |
| `core/pes/base.py` | MODIFY | 新增 on_execute()，修改 run() / build_prompt_context() |
| `core/main.py` | MODIFY | 启动时注册 TaskDispatcher |
| `config/agents/*.yaml` | NEW | Agent 配置文件 |
| `config/agents/prompts/*.md` | NEW | Agent Prompt 文本 |

## 5. 详细设计

### 5.1 AgentProfile

```python
# core/agent/profile.py

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AgentProfile:
    """Agent 人格配置（纯数据类）"""

    name: str
    display_name: str
    prompt_text: str  # 完整 Prompt 文本（已从 md 加载）

    def to_prompt_payload(self) -> dict[str, Any]:
        """转换为 Prompt 上下文"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "prompt_text": self.prompt_text,
        }
```

### 5.2 AgentRegistry

```python
# core/agent/registry.py

class AgentRegistry:
    """Agent 注册表（纯数据提供者）"""

    _instance: AgentRegistry | None = None

    def __init__(self, agents_dir: Path | str | None = None) -> None:
        self.agents_dir = Path(agents_dir) or self._default_agents_dir()
        self._cache: dict[str, AgentProfile] = {}

    @classmethod
    def get(cls, ...) -> "AgentRegistry":
        """获取单例"""
        ...

    def load(self, name: str) -> AgentProfile:
        """加载 Agent（返回完整 AgentProfile，不是地址）"""
        # 1. 读取 YAML 获取元数据
        # 2. 读取 prompt_file 指向的 Markdown
        # 3. 返回 AgentProfile(name, display_name, prompt_text)
        ...

    def reload(self, name: str) -> AgentProfile:
        """重新加载（清除缓存）"""
        ...

    def list_all(self) -> list[str]:
        """列出所有可用 Agent"""
        ...
```

### 5.3 PESRegistry

```python
# core/pes/registry.py

class PESRegistry:
    """PES 实例注册表（生命周期管理）"""

    _instance: PESRegistry | None = None

    def __init__(self) -> None:
        self._instances: dict[str, BasePES] = {}
        self._counters: dict[str, int] = {}

    @classmethod
    def get(cls) -> "PESRegistry":
        ...

    def register(self, pes: BasePES) -> str:
        """注册 PES 实例，返回实例 ID（如 'draft#001'）"""
        ...

    def get(self, instance_id: str) -> BasePES | None:
        """按实例 ID 获取"""
        ...

    def get_by_base_name(self, base_name: str) -> list[BasePES]:
        """按基础名称获取所有实例（如所有 'draft' 实例）"""
        ...

    def unregister(self, instance_id: str) -> bool:
        """注销实例"""
        ...
```

### 5.4 TaskDispatcher（EventBus 处理器）

```python
# core/events/dispatcher.py

class TaskDispatcher:
    """任务分发器（监听 TaskDispatchEvent，转换为 TaskExecuteEvent）"""

    def __init__(self) -> None:
        self.agent_registry = AgentRegistry.get()
        self.pes_registry = PESRegistry.get()

    def handle_dispatch(self, event: TaskDispatchEvent) -> None:
        """处理任务分发事件"""

        # 1. 获取完整 Agent 信息
        agent = self.agent_registry.load(event.agent_name)

        # 2. 获取 PES 实例
        instances = self.pes_registry.get_by_base_name(event.task_name)
        if not instances:
            logger.error("PES 实例不存在: %s", event.task_name)
            return
        pes = instances[0]  # 简化：取第一个

        # 3. 组装并发出执行事件
        execute_event = TaskExecuteEvent(
            timestamp=time.time(),
            target_pes_id=pes.instance_id,
            task_name=event.task_name,
            agent=agent,
            generation=event.generation,
            context=dict(event.context),
        )
        EventBus.get().emit(execute_event)


# 初始化
def setup_task_dispatcher() -> None:
    dispatcher = TaskDispatcher()
    EventBus.get().on("task:dispatch", dispatcher.handle_dispatch)
```

### 5.5 TaskDispatchEvent / TaskExecuteEvent

```python
# core/events/types.py（新增）

@dataclass(slots=True)
class TaskDispatchEvent(Event):
    """任务分发事件（调度器发出）"""

    type: str = "task:dispatch"
    timestamp: float = field(default_factory=time.time)
    task_name: str = ""
    agent_name: str = ""
    generation: int = 0
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TaskExecuteEvent(Event):
    """任务执行事件（由 TaskDispatcher 组装后发出）"""

    type: str = "task:execute"
    timestamp: float = field(default_factory=time.time)
    target_pes_id: str = ""
    task_name: str = ""
    agent: AgentProfile | None = None
    generation: int = 0
    context: dict[str, Any] = field(default_factory=dict)
```

### 5.6 BasePES 修改

```python
# core/pes/base.py（修改部分）

class BasePES(ABC):

    def __init__(
        self,
        config: PESConfig,
        llm: Any,
        # ... 其他现有参数
    ) -> None:
        # ... 现有初始化

        # [NEW] 当前 Agent（由 on_execute 设置）
        self._current_agent: AgentProfile | None = None
        self._execution_context: dict[str, Any] = {}
        self._instance_id: str | None = None

        # [NEW] 自动注册
        from core.pes.registry import PESRegistry
        self._instance_id = PESRegistry.get().register(self)

        # [NEW] 注册执行事件监听
        EventBus.get().on("task:execute", self.on_execute)

    @property
    def instance_id(self) -> str:
        """返回当前 PES 实例 ID。"""
        assert self._instance_id is not None
        return self._instance_id

    # [NEW] 接收执行事件
    def on_execute(
        self,
        event: TaskExecuteEvent,
    ) -> None:
        """接收执行事件（由 EventBus 调用）"""
        if event.target_pes_id != self.instance_id:
            return

        if event.agent is None:
            raise ValueError("TaskExecuteEvent.agent 不能为空")

        self._current_agent = event.agent
        self._execution_context = dict(event.context)
        asyncio.create_task(
            self.run(
                agent_profile=event.agent,
                generation=event.generation,
            )
        )

    # [MODIFY] 主运行入口
    async def run(
        self,
        agent_profile: AgentProfile,
        generation: int = 0,
        parent_solution: PESSolution | None = None,
    ) -> PESSolution:
        """执行完整 PES 三阶段流程"""
        self._current_agent = agent_profile
        ...

    # [MODIFY] 构建 Prompt 上下文
    def build_prompt_context(
        self,
        phase: str,
        solution: PESSolution,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "phase": phase,
            "solution": solution.to_prompt_payload(),
            "operation": self.config.operation,
            "pes_name": self.config.name,
            **self.runtime_context,
            **self._execution_context,
        }

        # [NEW] 注入 Agent 信息
        if self._current_agent:
            context["agent"] = self._current_agent.to_prompt_payload()

        if parent_solution:
            context["parent_solution"] = parent_solution.to_prompt_payload()

        return context
```

### 5.7 Prompt 注入调整

```yaml
# config/prompts/prompt_spec.yaml（修改示意）

templates:
  default_plan:
    required_context: ["agent"]
```

```jinja2
{# config/prompts/templates/default_plan.j2（修改示意） #}
{{ static_fragments_text }}

## Agent Persona
{{ agent.prompt_text }}
```

```python
# core/main.py（修改示意）

def main() -> None:
    ...
    EventBus.get()
    setup_task_dispatcher()
```

## 6. 配置文件

### 6.1 目录结构

```
config/agents/
├── aggressive.yaml
├── conservative.yaml
├── balanced.yaml
└── prompts/
    ├── aggressive.md
    ├── conservative.md
    └── balanced.md
```

### 6.2 配置示例

```yaml
# config/agents/aggressive.yaml
name: aggressive
display_name: 激进探索者
prompt_file: prompts/aggressive.md
```

```markdown
<!-- config/agents/prompts/aggressive.md -->
你是一个激进的机器学习竞赛选手，追求极限性能而非稳定性。

## 行为特征
- 敢于尝试前沿方法
- 快速迭代，优先追求效果
- 愿意承担高风险换取高收益

## 决策倾向
1. 优先选择上限最高的方案
2. 效果不佳立即切换方向
3. 不怕失败，快速试错
```

## 7. 实施阶段

### Phase 1: Agent 模块
- [ ] 创建 `core/agent/__init__.py`
- [ ] 实现 `core/agent/profile.py`
- [ ] 实现 `core/agent/registry.py`
- [ ] 创建 `config/agents/` 配置

### Phase 2: PESRegistry
- [ ] 创建 `core/pes/registry.py`
- [ ] 修改 `BasePES.__init__` 自动注册

### Phase 3: 事件分发
- [ ] 新增 `TaskDispatchEvent`
- [ ] 新增 `TaskExecuteEvent`
- [ ] 实现 `TaskDispatcher`
- [ ] 修改 `BasePES.on_execute()`
- [ ] 在启动流程注册 TaskDispatcher
- [ ] 确保 `TaskDispatchEvent.context` 原样透传到 `TaskExecuteEvent.context`

### Phase 4: 集成验证
- [ ] 单元测试
- [ ] 集成测试
- [ ] 验证 Agent Persona 已进入 Prompt

### Phase 5: 文档
- [ ] 更新 `docs/architecture.md`

## 8. 验证方案

### 8.1 单元测试

```python
# tests/unit/test_agent_registry.py

def test_load_returns_complete_profile():
    """load 返回完整 AgentProfile"""
    registry = AgentRegistry()
    profile = registry.load("aggressive")

    assert profile.name == "aggressive"
    assert len(profile.prompt_text) > 0  # 完整文本


def test_pes_registry_register():
    """PES 注册和查找"""
    registry = PESRegistry()
    instance_id = registry.register(mock_pes)

    assert registry.get(instance_id) is not None
    assert len(registry.get_by_base_name("draft")) >= 1
```

### 8.2 集成测试

```python
# tests/integration/test_dispatch_flow.py

async def test_dispatch_to_pes():
    """完整事件流"""
    # 1. 创建并注册 PES
    pes = MockPES(config, llm)
    setup_task_dispatcher()

    # 2. 发送分发事件
    event = TaskDispatchEvent(
        task_name="mock",
        agent_name="aggressive",
        context={"slot": "l2"},
    )
    EventBus.get().emit(event)

    # 3. 验证分发事件被转换并路由到目标 PES
    await asyncio.sleep(0.1)
    assert pes._current_agent.name == "aggressive"
    assert pes.received_execute_event.target_pes_id == pes.instance_id
    assert pes.received_execute_event.context["slot"] == "l2"
```

## 9. 后续扩展（本次不实现）

后续可基于本基础设施实现：

| 任务类 | 说明 | 继承自 |
|--------|------|--------|
| DraftPES | 初版代码生成 | BasePES |
| MutatePES | 代码变异优化 | BasePES |
| EvolvePES | 进化策略执行 | BasePES |

实现时只需：
1. 继承 `BasePES`
2. 实现 `run()` 方法
3. 创建时自动注册到 `PESRegistry`

## 10. 决策日志

| 日期 | 决策 | 状态 |
|------|------|------|
| 2026-03-25 | 以 `TaskDispatchEvent -> TaskExecuteEvent -> PES.on_execute()` 为唯一真值 | 确认 |
| 2026-03-25 | EventBus 仅负责发布/订阅，查 Registry 和组装事件由 TaskDispatcher 负责 | 确认 |
| 2026-03-25 | AgentRegistry 返回完整 AgentProfile | 确认 |
| 2026-03-25 | PESRegistry 管理实例，不参与路由 | 确认 |
| 2026-03-25 | 本次不实现具体任务类 | 确认 |
| 2026-03-25 | Agent 人格为 Markdown 文本 | 确认 |
| 2026-03-25 | 不复用 `BasePES.execute()` 作为调度入口，避免与 execute phase 冲突 | 确认 |
