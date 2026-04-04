# 045 实现 .env 配置加载层

## 元信息
- 状态: draft
- 创建: 2026-04-03
- 对应: CLAUDE.md §4.2 配置管理规范

## 1.1 摘要

当前 `ConfigManager.parse()` 只有 `dataclass 默认值 → YAML → CLI` 三层，缺少 CLAUDE.md §4.2 要求的 `.env` 层。本次在 `parse()` 中插入 `.env` 加载（位于 YAML 之后、CLI 之前），使敏感配置（API key）和模型超参数可通过 `.env` 文件管理。同时修复 YAML 不自动加载的问题，补充 `.env.example` 和 `.gitignore`。

## 1.2 审查点

- [ ] `.env` 优先级：CLAUDE.md 规范是 `CLI > .env > YAML`，但当前 YAML 需要 `--config` 显式传入（不传则不加载）。是否同时让 `config/herald.yaml` 自动加载？
- [ ] `ANTHROPIC_API_KEY` 无需写入 HeraldConfig——`claude_agent_sdk` 子进程通过 `os.environ` 继承。`.env` 中设置后 `load_dotenv()` 注入 `os.environ` 即可。是否认同这一判断？
- [ ] `LLM_MODEL` 等超参数通过 `.env` 覆盖 dataclass/YAML 默认值的映射规则：`HERALD_LLM_MODEL` → `llm.model`，前缀 `HERALD_` 避免污染。是否接受这个前缀约定？

## 1.3 流程图与嵌合说明

### 当前加载链（有缺陷）

```
ConfigManager.parse()
  ├── Phase 1: final_dict = asdict(HeraldConfig())     # dataclass 默认值
  ├── Phase 2: if --config → deep_update(yaml_data)    # YAML（需显式传 --config，不传则跳过）
  ├── Phase 3: CLI args 覆盖 final_dict                # CLI 最高优先级
  └── Phase 4: _dict_to_dataclass(final_dict)           # 重建 dataclass
```

问题：
1. **YAML 不自动加载**：不传 `--config` 就完全不读 herald.yaml
2. **无 .env 层**：敏感信息和模型超参数只能通过 CLI 传入
3. **ANTHROPIC_API_KEY 无处设置**：herald.yaml 的注释说"从环境变量读取"但没有代码实现

### 修改后加载链

```
main.py:
  load_dotenv()                                         # [NEW] 注入 .env 到 os.environ

ConfigManager.parse():
  ├── Phase 1: final_dict = asdict(HeraldConfig())      # dataclass 默认值
  ├── Phase 2: auto-load config/herald.yaml             # [MODIFY] 自动加载，不再需要 --config
  │            if --config → 用指定路径覆盖
  ├── Phase 2.5: _apply_env_overrides(final_dict)       # [NEW] 读 os.environ 中 HERALD_* 变量
  │            HERALD_LLM_MODEL → llm.model
  │            HERALD_LLM_MAX_TOKENS → llm.max_tokens
  │            HERALD_LLM_MAX_TURNS → llm.max_turns
  │            HERALD_RUN_MAX_TASKS → run.max_tasks
  ├── Phase 3: CLI args 覆盖 final_dict                 # CLI 最高优先级（不变）
  └── Phase 4: _dict_to_dataclass(final_dict)            # 不变
```

最终优先级：**CLI > .env(环境变量) > YAML > dataclass 默认值**，符合 CLAUDE.md §4.2。

### Claude CLI 原生环境变量（不进入 HeraldConfig）

以下变量由 bundled Claude CLI 子进程直接读取（`subprocess_cli.py:347` 做 `**os.environ` 全量传递），`load_dotenv()` 注入 `os.environ` 后子进程自动继承，**无需代码显式处理**：

| 环境变量 | 用途 |
|----------|------|
| `ANTHROPIC_API_KEY` | API 认证密钥 |
| `ANTHROPIC_BASE_URL` | 自定义 API 端点（中转平台） |
| `ANTHROPIC_MODEL` | CLI 级别模型覆盖 |

## 1.4 拟议变更

### `core/main.py` [MODIFY]

在 `main()` 函数最前面（`logging.basicConfig` 之前）加一行：

```python
from dotenv import load_dotenv
load_dotenv()  # 加载 .env 到 os.environ
```

### `core/load_config.py` [MODIFY]

**变更 1**：Phase 2 自动加载默认 YAML

```python
# 当前：
if temp_args.config:
    with open(temp_args.config, encoding="utf-8") as f:
        ...

# 修改为：
config_path = temp_args.config or self._default_config_path()
if Path(config_path).exists():
    with open(config_path, encoding="utf-8") as f:
        ...
```

新增静态方法：
```python
@staticmethod
def _default_config_path() -> str:
    """返回默认配置文件路径（项目根目录/config/herald.yaml）。"""
    return str(Path(__file__).resolve().parents[1] / "config" / "herald.yaml")
```

**变更 2**：Phase 2.5 新增 `_apply_env_overrides()`

```python
def _apply_env_overrides(self, final_dict: dict, all_fields: dict) -> None:
    """从 os.environ 读取 HERALD_* 变量覆盖配置。

    映射规则：HERALD_LLM_MODEL → llm.model
    即 HERALD_ 前缀 + 字段路径（点号转下划线，全大写）。
    """
    for field_path, field_type in all_fields.items():
        env_key = "HERALD_" + field_path.replace(".", "_").upper()
        env_val = os.environ.get(env_key)
        if env_val is not None:
            cast_fn = self._smart_cast(field_type)
            self._set_nested_value(final_dict, field_path, cast_fn(env_val))
```

在 `parse()` 中插入调用（Phase 2 和 Phase 3 之间）：

```python
# 2.5 环境变量覆盖（优先级高于 YAML，低于 CLI）
all_cli_fields = self._get_all_fields(HeraldConfig)
self._apply_env_overrides(final_dict, all_cli_fields)

# 3. CLI 动态解析（最高优先级）
...
```

### `.env.example` [NEW]

```env
# Herald2 环境配置
# 复制为 .env 后填入真实值

# === 敏感信息（必填）===
ANTHROPIC_API_KEY=sk-ant-xxx

# === LLM 超参数（可选，覆盖 herald.yaml）===
# HERALD_LLM_MODEL=claude-sonnet-4-20250514
# HERALD_LLM_MAX_TOKENS=32768
# HERALD_LLM_MAX_TURNS=16

# === 运行时配置（可选）===
# HERALD_RUN_MAX_TASKS=3
```

### `.gitignore` [MODIFY]

新增一行：
```
.env
```

### `config/herald.yaml` [MODIFY]

删除 `api_key: null` 注释行（误导性，API key 不走配置链）：

```yaml
llm:
  model: glm-5
  max_tokens: 32768
  max_turns: 16
  setting_sources: ["project"]
  # api_key 通过 .env 中的 ANTHROPIC_API_KEY 设置，不走配置链
```

## 1.5 验证计划

| 验证项 | 方法 | 预期结果 |
|--------|------|----------|
| .env 中 ANTHROPIC_API_KEY 生效 | 创建 .env 设置 key，运行 main.py，观察是否还报 exit code 1 | 子进程能正常启动 |
| .env 中 HERALD_LLM_MODEL 覆盖 YAML | 在 .env 设置 `HERALD_LLM_MODEL=test-model`，打印 config.llm.model | 输出 test-model 而非 glm-5 |
| CLI 优先于 .env | 同时设 .env 和 `--llm_model xxx` | CLI 值优先 |
| YAML 自动加载 | 不传 --config 运行 | config.llm.model = glm-5（来自 herald.yaml） |
| .gitignore 包含 .env | 检查 .gitignore | 含 .env 行 |

## 涉及文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `core/main.py` | MODIFY | 顶部加 `load_dotenv()` |
| `core/load_config.py` | MODIFY | 自动加载 YAML + 新增 `_apply_env_overrides()` |
| `.env.example` | NEW | 环境变量模板 |
| `.gitignore` | MODIFY | 新增 `.env` |
| `config/herald.yaml` | MODIFY | 澄清 api_key 注释 |
