# Herald 编码指南

> **定位**: 本文档聚焦代码细节层面的规范，与 CLAUDE.md（流程 SOP）互为补充。
> **更新**: 2026-03-17
> **状态**: M0 阶段

---

## 1. 项目结构与模块组织

### 1.1 核心设计哲学

Herald 采用 **领域驱动的扁平化结构**，而非传统的技术分层（MVC/三层架构）：

```
core/
├── models.py       # 数据模型（Gene/Solution/SlotContract）
├── database.py     # 持久化层（SQLite WAL 模式）
├── templates.py    # 模板引擎（GenomeSchema 注册 + 代码注入）
├── contract.py     # 契约验证（AST 解析 + 静态/运行时检查）
├── sandbox.py      # 沙箱执行器（隔离环境 + 超时控制）
├── llm.py          # LLM 客户端（Claude SDK 封装）
├── pes.py          # PES 引擎（Plan/Execute/Summarize 流程编排）
└── main.py         # CLI 入口（argparse + async 调度）
```

**关键原则**（参考 Karpathy autoresearch）：

| 维度 | Herald 实践 | 反面模式 |
|------|------------|---------|
| 目录层级 | ≤2 层（`core/` + 模块文件） | `src/core/services/utils/` 多层嵌套 |
| 职责划分 | 按**业务领域**（模型/数据库/模板/LLM） | 按技术角色（`models/`, `views/`, `controllers/`） |
| 文件粒度 | 单文件 = 单完整生命周期（如 `database.py` 包含建表 + CRUD） | 拆散成 `db_connection.py` + `db_models.py` + `db_crud.py` |

---

## 2. 命名规范

### 2.1 文件命名

| 类型 | 示例 | 规范 |
|------|------|------|
| 模块 | `models.py`, `database.py` | **名词单数**，描述内容 |
| 工具集 | `templates.py`, `contract.py` | 领域聚合 |

### 2.2 类命名 — PascalCase + 精准描述

```python
# ✅ 优秀示例（参考 nanobot）
Gene              # 核心概念，无需赘述
SlotContract      # 复合名词，职责清晰
HeraldDB          # 项目特定前缀 + 功能
DraftPES          # 操作类型 + 核心概念

# ❌ 避免模糊命名
Manager           # 过度抽象，不知道管理什么
Handler           # 万能胶水，责任不明确
```

### 2.3 函数/方法命名 — 动词驱动 + 语义对称

**原则**（AI Scientist 法则 2）：
- 顶层编排：`动词 + 主题`（如 `register_tabular_ml()`）
- 辅助工具：`动词 + 具体对象`（如 `load_template()`）
- 生命周期管理：`create` / `init` / `close` / `cleanup`

**对称性设计**（nanobot 美学）：
```python
# ✅ 成对操作
insert_solution() / get_solution()
insert_genes() / get_genes()
log_llm_call() / log_exec()

# ✅ 布尔判断
check_syntax() -> ValidationResult (不是 True/False)
_check_oom() -> bool

# ❌ 避免混乱
add_solution() / fetch_sol()  # 不对称
is_valid() 但返回 dict      # 类型不匹配
```

### 2.4 变量命名 — 常量带单位后缀

```python
# ✅ 优秀示例（autoresearch 法则 8）
MAX_ITERS = 5              # 常量大写，无歧义
timeout_s = 600            # 带单位后缀（秒）
latency_ms = 1200          # 带单位后缀（毫秒）

# ❌ 避免模糊
TIMEOUT = 600              # 不知道单位
MAX = 5                    # 不知道是什么的最大值
```

### 2.5 私有变量/方法命名

```python
# 模块级私有（单下划线）
_TYPE_MAP = {...}
_resolve_path()

# 实例私有（单下划线，不用双下划线）
self._client
self._parse_metrics()
```

---

## 3. 类型注解 — 强制规范（法则 5）

### 3.1 完整性要求

**所有** 函数签名必须包含类型注解：

```python
# ✅ 完整示例
def insert_solution(self, solution: Solution) -> None:
    """插入方案（不含 genes）"""
    ...

async def call(
    self,
    prompt: str,
    system_prompt: str | None = None,  # Python 3.10+ Union 语法
) -> LLMResponse:
    """调用 LLM（单轮模式）"""
    ...

# ❌ 禁止省略类型
def process(data):        # 什么类型？
    return do_something(data)
```

### 3.2 复杂类型处理

```python
# ✅ 使用现代语法（Python 3.10+）
def get_genes(self) -> dict[str, Gene]:      # 泛型参数清晰
def validate(self) -> list[ValidationResult]:

# ✅ 使用 Union 简化语法
timeout: int | None = None                  # 而非 Optional[int]

# ✅ 使用 Any 作为占位符（M0 阶段可接受）
metrics: dict[str, Any]                     # M1 再细化

# ❌ 避免过度复杂
def process(data: Union[Dict[str, Union[List[str], int]], str]) -> ...  # 难读
```

### 3.3 数据类型注解

```python
# ✅ dataclass 字段必须有类型
@dataclass
class SlotContract:
    function_name: str                     # 必须
    params: dict[str, str]                 # 必须
    return_type: str                       # 必须

# ✅ 使用 field() 处理默认值
constraints: list[str] = field(default_factory=list)  # 避免可变默认值陷阱
```

---

## 4. 函数设计 — 单一职责 + 阶段化注释

### 4.1 长度与职责控制

**原则**（autoresearch 法则 5）：

| 函数类型 | 行数上限 | 示例 |
|---------|---------|------|
| 胶水代码 | ≤5 行 | `close()` → 1 行 `self.conn.close()` |
| 工具函数 | ≤30 行 | `extract_code_block()` → 20 行 |
| 核心算法 | ≤60 行 | `run_static_validation()` → 30 行 |
| 流程编排 | ≤80 行 | `execute()` → 70 行（但有清晰分段） |

**关键**：算法内聚性 > 行数限制。宁可 60 行函数写清楚一个逻辑，不要拆成 3 个函数猜调用顺序。

### 4.2 阶段化注释强制规范

**所有流程编排函数** 必须用 `# Phase N:` 注释分隔（AI Scientist 法则 3）：

```python
# ✅ 优秀示例（database.py:create_tables）
def create_tables(self) -> None:
    """建所有表（10 张表）+ 索引 + generation_stats View"""
    cursor = self.conn.cursor()

    # 核心实体表
    cursor.execute("""CREATE TABLE IF NOT EXISTS solutions ...""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS genes ...""")

    # L1 追踪表
    cursor.execute("""CREATE TABLE IF NOT EXISTS llm_calls ...""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS exec_logs ...""")

    # L2 知识层（M0 建表但不提供 CRUD）
    cursor.execute("""CREATE TABLE IF NOT EXISTS l2_insights ...""")

    # 创建索引
    cursor.execute("""CREATE INDEX IF NOT EXISTS idx_llm_calls_solution ...""")

    self.conn.commit()
```

```python
# ✅ 优秀示例（pes.py:run）
async def run(self) -> Solution:
    """执行完整 Draft PES 循环"""

    # Phase 1: 创建 Solution 实例
    solution = Solution(...)
    self.db.insert_solution(solution)

    # Phase 2: Plan 阶段
    solution = await self.plan(solution)

    # Phase 3: Execute 阶段
    solution = await self.execute(solution)

    # Phase 4: Summarize 阶段
    solution = await self.summarize(solution)

    return solution
```

**格式要求**：
- 分隔符：`# Phase N: 描述`（Phase 大写，冒号后空格，描述简洁）
- 替代格式：`# 核心实体表` / `# L1 追踪表`（语义分组优于数字编号）
- **禁止废话注释**：不要写 `# 执行主流程`（代码已经说明）

### 4.3 参数设计 — 最小化原则

**法则**（AI Scientist 法则 8）：核心函数参数数量 ≤5，超过则重构为配置对象。

```python
# ✅ 优秀示例
def __init__(
    self,
    db: HeraldDB,                   # 1. 必需依赖
    llm: LLMClient,                  # 2. 必需依赖
    schema: GenomeSchema,            # 3. 必需配置
    competition_dir: str,            # 4. 必需路径
) -> None:

# ❌ 参数过多，应重构
def execute(
    self, slot, code, contract, db, llm, schema, work_dir, timeout, retry, ...  # 10+ 个参数
) -> Result:
```

**重构策略**：
```python
# ✅ 使用 dataclass 封装配置
@dataclass
class ExecutionConfig:
    timeout_s: int = 600
    retry_count: int = 3
    conda_env: str = "herald"

def execute(self, config: ExecutionConfig) -> Result:
    ...
```

---

## 5. 注释规范 — WHY > WHAT

### 5.1 Docstring 三层模型（nanobot 法则）

```python
# ✅ 类级 Docstring — What + Context
@dataclass
class Gene:
    """基因二态模型——描述态

    Gene 是系统中的第一公民表示，存在两种形态：
    - 描述态（本 dataclass）：供 Planner / Summarizer / 人类消费
    - 代码态（GENE 区域代码）：供 Executor / 沙箱执行

    Attributes:
        slot: 位点名，如 "MODEL"
        description: 自然语言描述 + 关键参数
        ...
    """

# ✅ 方法 Docstring — Why + How
def check_function_name(code: str, contract: SlotContract) -> ValidationResult:
    """检查函数名是否匹配契约

    遍历 AST 树查找 FunctionDef 节点，检查是否存在与契约匹配的函数名。

    Args:
        code: 待检查的 Python 代码
        contract: SlotContract 实例

    Returns:
        验证结果，失败时 detail 说明期望的函数名
    """
```

### 5.2 内联注释 — 解释非直观决策

```python
# ✅ 优秀示例（解释 WHY）
self.conn.row_factory = sqlite3.Row  # 返回字典形式，方便序列化
self.conn.execute("PRAGMA journal_mode=WAL")  # WAL 模式提升并发性能

# ✅ 优秀示例（解释技术约束）
# 跳过项目内部模块（避免循环依赖误报）
if not top_module.startswith("core"):
    top_level_modules.add(top_module)

# ❌ 废话注释
i = 0  # 初始化计数器（代码已经说明）
```

### 5.3 零注释场景

```python
# ✅ 简单函数无需注释（autoresearch 法则 4）
def close(self) -> None:
    """关闭连接"""
    self.conn.close()

# ✅ 类型注解即文档
def extract_code_block(text: str) -> str | None:
    """从 LLM 响应中提取 ```python ... ``` 代码块"""
    ...
```

---

## 6. 数据模型设计 — 类型安全 + 不可变性

### 6.1 dataclass 优先规则

**所有** 数据传输对象（DTO）和领域模型使用 `@dataclass`：

```python
# ✅ 优秀示例
@dataclass
class SlotContract:
    """基因位点的接口契约"""
    function_name: str
    params: dict[str, str]
    return_type: str

# ❌ 避免纯字典
contract = {
    "function_name": "load_data",  # 无类型检查
    "params": {"config": "dict"},  # 易拼写错误
}
```

### 6.2 字段默认值处理

```python
# ✅ 使用 field() 处理可变默认值（避免陷阱）
constraints: list[str] = field(default_factory=list)
parent_ids: list[str] = field(default_factory=list)

# ✅ 使用 field(init=False) 处理计算字段
code_anchor: str = field(init=False)

def __post_init__(self) -> None:
    self.code_anchor = f"GENE:{self.slot.upper()}"

# ❌ 可变默认值陷阱
constraints: list[str] = []  # 所有实例共享同一列表！
```

### 6.3 模型一致性验证

**关键**：`core/models.py` 中的字段必须与 `docs/TD.md` 规范一致。

```python
# ✅ 与 TD.md §1.1 一致
@dataclass
class Gene:
    slot: str                     # TD.md: "位点名"
    description: str              # TD.md: "自然语言描述"
    contract: SlotContract        # TD.md: "接口契约"
    version: int = 0              # TD.md: "变异计数，M0 固定 0"

# ❌ 禁止添加未经 TD.md 批准的字段
priority: int = 1               # 未在 TD.md 定义
```

---

## 7. Prompt 管理 — 代码内嵌 + 版本化

### 7.1 基本原则（AI Scientist 法则 7）

**Herald 当前阶段不使用配置文件管理 Prompt**，理由：
- M0 Prompt 频繁迭代，代码内修改更快
- 避免"配置地狱"（多个 YAML 文件散落各处）
- 版本控制友好（Prompt 变更直接在 Git diff 中可见）

### 7.2 组织方式

```python
# ✅ 优秀示例（pes.py）
def _build_plan_prompt(self, description_text: str, schema: GenomeSchema) -> str:
    """构造 Plan 阶段 prompt

    包含：
    1. 系统角色定义
    2. 赛题信息
    3. GenomeSchema 信息
    4. 输出格式要求（JSON schema）
    5. 重要提示
    """
    # Phase 1: 构造 schema slots 信息
    slots_info = []
    for slot in schema.slots:
        slots_info.append(f"""
## Slot: {slot.name}
- **描述**: {slot.description}
- **接口契约**: `{slot.contract.function_name}(...)` -> {slot.contract.return_type}
""")

    slots_text = "\n".join(slots_info)

    # Phase 2: 组装完整 prompt
    prompt = f"""你是 Herald 自动化科研系统的 Planner...

# 赛题信息
{description_text}

# 基因模板
{slots_text}

# 输出要求
...
"""
    return prompt
```

**关键设计**：
- 用方法封装 Prompt 构造逻辑（`_build_plan_prompt` / `_build_execute_prompt`）
- 用 f-string 动态拼接，而非 Jinja2 模板引擎
- 用注释说明 Prompt 包含的关键部分

### 7.3 多阶段 Prompt 管理

```python
# ✅ 按阶段分离方法
class DraftPES:
    async def plan(self, solution):
        prompt = self._build_plan_prompt(...)
        ...

    async def execute(self, solution):
        prompt = self._build_execute_prompt_full(...)
        ...

    async def summarize(self, solution):
        prompt = self._build_summarize_prompt(...)
        ...
```

**M1 演进路径**（未来参考）：
- 若 Prompt 超过 200 行 → 考虑拆分到 `prompts/plan.txt` 模板文件
- 若有多语言需求 → 使用 `prompts/{lang}/plan.txt`
- 仍优先代码内嵌，只在必要时外部化

---

## 8. 错误处理 — 分层策略 + 降级设计

### 8.1 三层错误处理（nanobot 法则 7）

```python
# 底层：详细日志 + 异常传播
async def fetch_data():
    try:
        ...
    except HTTPError as e:
        logger.error(f"HTTP error: {e}")
        raise  # 向上传播

# 中层：降级策略
async def process():
    try:
        return await fetch_data()
    except HTTPError:
        logger.warning("Fetch failed, using fallback")
        return fallback_data()

# 顶层：用户友好错误
async def handle_request():
    try:
        return await process()
    except Exception as e:
        logger.exception(f"Request failed: {e}")
        return {"status": "error", "message": "处理失败，请稍后重试"}
```

### 8.2 快速失败 vs 优雅降级

**快速失败场景**（autoresearch 法则 6）：
- 训练/执行核心路径：错误直接暴露，不做隐藏
- 配置验证：启动时检查，失败立即退出

```python
# ✅ 快速失败示例
if not competition_dir.exists():
    logger.error(f"赛题目录不存在: {competition_dir}")
    sys.exit(1)  # 立即退出，不继续执行

# ✅ 语法错误短路
syntax_result = check_syntax(code)
if not syntax_result.passed:
    return [syntax_result]  # 不执行后续检查
```

**优雅降级场景**：
- LLM 调用失败 → 重试 N 次
- Prompt 解析失败 → 返回默认值 + 警告日志
- 可选功能失败 → 记录日志，不影响主流程

```python
# ✅ 优雅降级示例（llm.py）
last_error = None
for attempt in range(self.max_retries + 1):
    try:
        return await self._execute_request()
    except Exception as e:
        last_error = e
        if attempt < self.max_retries:
            continue  # 重试
        else:
            raise RuntimeError(f"Failed after {self.max_retries + 1} attempts") from e
```

### 8.3 异常粒度控制

**Herald 当前阶段**（M0）：粗粒度捕获 `Exception`，快速迭代优先。

```python
# ✅ M0 阶段可接受
try:
    solution = await self.plan(solution)
except Exception as e:
    solution.status = "failed"
    raise RuntimeError(f"Plan 阶段失败: {e}") from e
```

**M1 演进路径**：
- 定义业务异常：`PlanError` / `ExecuteError` / `ContractViolationError`
- 细化捕获策略：区分瞬态错误（重试）vs 永久错误（快速失败）

---

## 9. 抽象策略 — 条件分支 > 继承（法则 5）

### 9.1 何时使用条件分支

**当差异度 < 30%** 时，用 if-elif 而非继承体系。

```python
# ✅ Herald 未来可能的场景（多模型适配）
def create_llm_client(model_name: str) -> LLMClient:
    if "claude" in model_name:
        return LLMClient(provider="anthropic", model=model_name)
    elif "gpt" in model_name:
        return LLMClient(provider="openai", model=model_name)
    elif "llama" in model_name:
        return LLMClient(provider="local", model=model_name)
    else:
        raise ValueError(f"Unsupported model: {model_name}")

# ❌ 过度抽象（10 个模型 → 10 个子类）
class ClaudeClient(LLMClient): ...
class GPTClient(LLMClient): ...
class LlamaClient(LLMClient): ...
```

### 9.2 何时使用继承/协议

**当差异度 > 70%** 或需要插件化扩展时，使用抽象基类。

```python
# ✅ Herald 未来可能场景（多 Executor 策略）
from abc import ABC, abstractmethod

class Executor(ABC):
    @abstractmethod
    async def execute(self, code: str) -> ExecutionResult:
        """执行代码并返回结果"""
        pass

class SandboxExecutor(Executor):
    async def execute(self, code: str) -> ExecutionResult:
        # 沙箱隔离执行
        ...

class RemoteExecutor(Executor):
    async def execute(self, code: str) -> ExecutionResult:
        # 远程机器执行
        ...
```

**判断标准**：
- 有 3+ 个实现 → 需要抽象
- 只有 1-2 个实现 → 过度设计

---

## 10. 配置管理 — dataclass + YAML + .env

### 11.1 三层优先级

```
CLI args > 环境变量 (.env) > YAML 配置 > dataclass 默认值
```

### 11.2 配置数据类设计

```python
# ✅ 优秀示例（未来 config.py）
from dataclasses import dataclass

@dataclass
class LLMConfig:
    """LLM 配置"""
    model: str = "claude-sonnet-4-20250514"
    max_turns: int = 15
    timeout_s: int = 120

@dataclass
class SandboxConfig:
    """沙箱配置"""
    timeout_s: int = 600
    conda_env: str = "herald"
    python_cmd: str | None = None

@dataclass
class HeraldConfig:
    """Herald 全局配置"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    db_path: str = "herald.db"
```

### 11.3 配置加载逻辑

```python
# ✅ 优秀示例
def load_config() -> HeraldConfig:
    """加载配置（优先级：CLI > ENV > YAML > 默认值）"""
    # 1. 加载默认值
    config = HeraldConfig()

    # 2. 从 YAML 覆盖
    yaml_path = Path("herald.yaml")
    if yaml_path.exists():
        with yaml_path.open() as f:
            yaml_data = yaml.safe_load(f)
            # 更新 config...

    # 3. 从环境变量覆盖
    if "HERALD_MODEL" in os.environ:
        config.llm.model = os.environ["HERALD_MODEL"]

    # 4. 从 CLI 参数覆盖（在 main.py 中处理）
    return config
```

### 11.4 超参数管理

**禁止硬编码超参数**（AI Scientist 启示）：

```python
# ❌ 避免硬编码
MAX_ITERS = 5  # 写在代码里

# ✅ 写在配置类中
@dataclass
class ExecutionConfig:
    max_iters: int = 5
    max_runs: int = 5
    timeout_s: int = 600
```

---

## 11. 日志规范 — 结构化 + 分级

### 12.1 日志级别定义

| 级别 | 用途 | 示例 |
|------|------|------|
| DEBUG | 调试信息（M0 不使用，M1 启用） | `logger.debug(f"Parsing JSON: {json_text[:100]}")` |
| INFO | 关键流程节点 | `logger.info("开始执行 Draft PES")` |
| WARNING | 非致命警告 | `logger.warning("description.md 不存在，跳过赛题描述")` |
| ERROR | 可恢复错误 | `logger.error(f"LLM 调用失败（第 {attempt} 次重试）")` |
| EXCEPTION | 带堆栈的错误 | `logger.exception(f"Plan 阶段失败: {e}")` |

### 12.2 日志格式

```python
# ✅ 优秀示例（main.py 配置）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ✅ 输出示例
# 2026-03-17 14:23:45 [INFO] 开始执行 Draft PES
# 2026-03-17 14:24:12 [ERROR] LLM 调用失败（第 1 次重试）
```

### 12.3 禁止 print() 调试

```python
# ❌ 禁止在生产代码中使用 print()
print("Processing message...")
print(f"Result: {result}")

# ✅ 使用结构化日志
logger.info("Processing message from channel=%s", channel_id)
logger.debug("Result: %s", result)  # M1 启用
```

**例外场景**：
- CLI 主入口的用户反馈（如 `print("✓ 执行成功")`）
- 临时 debug 代码（提交前必须删除）

---

## 12. Herald 当前阶段应学习什么

### 13.1 立即应用的技巧（参考三个项目）

| 来源 | 技巧 | Herald 应用场景 |
|------|------|----------------|
| **AI Scientist** | 阶段化注释（`## PHASE`） | `pes.py` 的 Plan/Execute/Summarize 流程 |
| **autoresearch** | 常量区块化 + 注释分节 | `# Phase 1: 数据类定义` |
| **nanobot** | 极简事件总线（37 行完整功能） | M1 可能需要的消息队列 |

### 13.2 当前阶段不该做什么

| 过度设计 | 为什么不做 | 何时做 |
|---------|-----------|--------|
| 为每个模型创建适配器类 | M0 只用 Claude，条件分支足够 | M1 支持 3+ 模型时 |
| 自定义异常类体系 | 粗粒度 `Exception` 快速迭代 | M1 错误处理细化时 |
| Prompt 外部化到 YAML | Prompt 频繁迭代，代码内更快 | M1 Prompt 稳定后 |
| 完整测试覆盖率 | 集成测试优先，快速验证流程 | M1 核心稳定后补单元测试 |

---

## 13. 代码审查 Checklist

### 14.1 每次 PR 必查

- [ ] **类型注解完整？** 所有函数签名有类型
- [ ] **阶段化注释？** 流程编排函数有 `# Phase N:` 分隔
- [ ] **常量带单位？** `timeout_s` / `latency_ms` 而非 `TIMEOUT`
- [ ] **错误处理合理？** 快速失败 vs 优雅降级场景正确
- [ ] **日志级别正确？** INFO/WARNING/ERROR 使用恰当
- [ ] **无 print() 调试？** 生产代码无 print 语句
- [ ] **数据模型一致？** 与 `docs/TD.md` 规范匹配
- [ ] **Docstring 完整？** 类/复杂方法有清晰文档

### 14.2 代码风格工具

```bash
# 运行检查（发现问题）
ruff check core/ --fix

# 运行格式化（自动修复）
ruff format core/
```

---

## 14. 代码清洁法则速查表

| 法则 | 原则 | 检测方法 |
|------|------|---------|
| **扁平优于嵌套** | 目录层级 ≤2 层 | `find core/ -type d | wc -l` |
| **动词驱动命名** | 函数名以动作动词开头 | 人工审查（`generate_`, `check_`, `insert_`） |
| **阶段化注释强制** | 流程函数必须有 Phase 注释 | `grep -n "# Phase" core/*.py` |
| **常量就近原则** | 常量定义在使用它的文件顶部 | 无单独 `constants.py` |
| **条件分支 > 多态** | 差异度 < 30% 用 if-elif | 人工审查（避免过度抽象） |
| **快速失败** | 检测到错误立即返回/退出 | `grep -n "sys.exit\|return False" core/*.py` |
| **Prompt 即代码** | Prompt 写在代码里 | 无 `prompts/*.yaml` 文件 |
| **参数最小化** | 核心函数参数 ≤5 | 人工审查函数签名 |

---

## 附录：常见错误与修正

### A.1 类型注解缺失

```python
# ❌ 错误
def process(data):
    return data["result"]

# ✅ 修正
def process(data: dict[str, Any]) -> Any:
    return data["result"]
```

### A.2 可变默认值陷阱

```python
# ❌ 错误
@dataclass
class Gene:
    constraints: list[str] = []  # 所有实例共享同一列表

# ✅ 修正
@dataclass
class Gene:
    constraints: list[str] = field(default_factory=list)
```

### A.3 SQL 注入风险

```python
# ❌ 错误（潜在 SQL 注入）
cursor.execute(f"SELECT * FROM solutions WHERE id = '{solution_id}'")

# ✅ 修正（参数化查询）
cursor.execute("SELECT * FROM solutions WHERE id = ?", (solution_id,))
```

### A.4 资源泄漏

```python
# ❌ 错误（异常时连接未关闭）
client = ClaudeSDKClient()
await client.connect()
await client.query(...)
await client.disconnect()

# ✅ 修正（确保清理）
client = ClaudeSDKClient()
try:
    await client.connect()
    await client.query(...)
finally:
    await client.disconnect()
```

---

**更新历史**：
- 2026-03-17：M0 初版，基于 AI Scientist / autoresearch / nanobot 三项目分析
