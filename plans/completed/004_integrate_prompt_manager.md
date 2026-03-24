# 集成 PromptManager V3

## 元信息
- 状态: in_progress
- 创建: 2026-03-24
- 负责人: Claude Agent

## 目标

将 PromptManager V3 模块（`prompt_spec + fragments + templates` 三层架构）集成到 Herald2 项目，替代当前的 `str.format_map()` + 内联模板方案。

## 背景分析

**当前实现**：
- `BasePES.render_prompt()` 使用 `format_map()` 渲染
- 模板存储在 `PhaseConfig.prompt_template` 字段
- 无独立的 templates/fragments 目录
- 存在代码重复：`core/pes/config.py` 与 `config/classconfig/pes.py`

**目标架构**：
- PromptManager V3: `spec.yaml + templates/*.j2 + fragments/*.md`
- 使用 Jinja2 替代 `format_map()`

## 目录结构

```
Herald2/
├── core/
│   └── prompts/                    # [NEW]
│       ├── __init__.py
│       ├── manager.py              # PromptManager V3
│       └── types.py
├── config/
│   └── prompts/                    # [NEW]
│       ├── prompt_spec.yaml
│       ├── templates/               # *.j2
│       └── fragments/               # *.md
```

## 检查点

### Phase 1: 创建 PromptManager 模块
- [ ] 创建 `core/prompts/__init__.py`
- [ ] 创建 `core/prompts/manager.py` (PromptManager V3)
- [ ] 创建 `core/prompts/types.py`

### Phase 2: 创建配置目录
- [ ] 创建 `config/prompts/prompt_spec.yaml`
- [ ] 创建 `config/prompts/templates/` 目录
- [ ] 创建 `config/prompts/fragments/` 目录

### Phase 3: 修改 PhaseConfig
- [ ] 移除 `prompt_template` 字段
- [ ] 添加 `template_name` 字段（可选）
- [ ] 文件: `core/pes/config.py`

### Phase 4: 集成到 BasePES
- [ ] 添加 `prompt_manager` 参数到 `__init__`
- [ ] 实现 `_create_default_prompt_manager()`
- [ ] 改造 `render_prompt()` 使用 PromptManager
- [ ] 文件: `core/pes/base.py`

### Phase 5: 清理重复代码
- [ ] 删除 `config/classconfig/pes.py`
- [ ] 更新 `config/classconfig/loader.py` 的 import
- [ ] 更新 `config/classconfig/__init__.py` 的导出

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `core/prompts/__init__.py` | NEW |
| `core/prompts/manager.py` | NEW |
| `core/prompts/types.py` | NEW |
| `config/prompts/prompt_spec.yaml` | NEW |
| `config/prompts/templates/*.j2` | NEW |
| `config/prompts/fragments/*.md` | NEW |
| `core/pes/base.py` | MODIFY |
| `core/pes/config.py` | MODIFY |
| `config/classconfig/pes.py` | DELETE |
| `config/classconfig/loader.py` | MODIFY |
| `config/classconfig/__init__.py` | MODIFY |

## 关键代码位置

- `core/pes/base.py:263-272` — `render_prompt()` 改造点
- `core/pes/config.py:14-22` — `PhaseConfig` 定义
- `config/classconfig/pes.py` — 重复代码，待删除

## 验证方案

1. 单元测试: `tests/unit/prompts/test_manager.py`
2. 集成测试: 验证 `BasePES._run_phase()` 流程
3. 确认 `before_prompt` Hook 和 `PromptHookContext` 兼容

## 阻塞项

无

## 决策日志

- 2026-03-24: 采用 PromptManager V3 三层架构 — 用户确认
- 2026-03-24: 使用 Jinja2 替代 format_map — 支持更强大的模板功能
