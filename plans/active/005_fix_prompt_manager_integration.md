# 005: 修复 PromptManager 集成孤立问题

## 元信息
- 状态: in_progress
- 创建: 2026-03-24
- 负责人: Claude Agent

## 目标

修复 PromptManager V3 集成后发现的所有孤立问题，确保系统可正常运行。

## 背景

检测发现：
1. **P0 Bug**: `loader.py:229` 使用 `prompt_template` 字段，但 `PhaseConfig` 定义为 `template_name`，导致运行时 TypeError
2. **P1**: `config/prompts/` 目录为空，PromptManager 无法加载配置
3. **P1**: `config/classconfig/pes.py` 与 `core/pes/config.py` 代码重复
4. **P2**: `docs/coding_guide.md` 第7节描述旧版方案

## 检查点

### Phase 1: 修复 P0 Bug
- [ ] 修改 `config/classconfig/loader.py:229` — `prompt_template` → `template_name`
- [ ] 验证 `Config.get_pes_config()` 可正常调用

### Phase 2: 创建配置文件
- [ ] 创建 `config/prompts/prompt_spec.yaml`
- [ ] 创建 `config/prompts/templates/` 目录及示例模板
- [ ] 创建 `config/prompts/fragments/` 目录及静态片段

### Phase 3: 清理重复代码
- [ ] 删除 `config/classconfig/pes.py`
- [ ] 更新 `config/classconfig/__init__.py` 导出
- [ ] 更新 `config/classconfig/loader.py` 导入来源

### Phase 4: 更新文档
- [ ] 更新 `docs/coding_guide.md:396-470` 为 PromptManager V3 说明

## 文件变更清单

| 文件 | 操作 |
|------|------|
| `config/classconfig/loader.py` | MODIFY |
| `config/prompts/prompt_spec.yaml` | NEW |
| `config/prompts/templates/*.j2` | NEW |
| `config/prompts/fragments/*.md` | NEW |
| `config/classconfig/pes.py` | DELETE |
| `config/classconfig/__init__.py` | MODIFY |
| `docs/coding_guide.md` | MODIFY |

## 验证方案

1. 单元测试: `python -c "from config.classconfig.loader import Config; ..."`
2. 集成测试: 验证 `BasePES._run_phase()` 完整流程
3. 导入测试: 确认无循环依赖

## 阻塞项

无

## 决策日志

- 2026-03-24: 完整修复所有发现的问题 — 用户确认
