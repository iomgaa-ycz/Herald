# 计划：初始化 EventBus 事件流系统

## 1.1 摘要

在 `core/main.py` 中添加 EventBus 单例初始化，作为 Phase 4 加入主流程，确保事件系统在应用启动时可用。

## 1.2 审查点

- EventBus 初始化位置是否合适（Phase 3 数据库初始化之后）

## 1.3 拟议变更

### 文件：`core/main.py`

| 行号 | 操作 | 描述 |
|------|------|------|
| 10 | `[MODIFY]` | 添加 `from core.events import EventBus` 导入 |
| 37 | `[NEW]` | 添加 Phase 4：初始化 EventBus |

**具体变更**：

```python
# 新增导入
from core.events import EventBus

# Phase 4: 初始化事件流系统（在 Phase 3 之后）
EventBus.get()
logger.info("事件流系统已初始化")
```

## 1.4 验证计划

- `python core/main.py --run_competition_dir /tmp/test` 执行无报错
- 日志输出包含 "事件流系统已初始化"
