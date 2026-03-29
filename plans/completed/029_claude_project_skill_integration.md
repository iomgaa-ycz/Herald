# 029：接通 Claude Agent SDK 的 project skill 机制

## 元信息
- 状态: completed
- 创建: 2026-03-29
- 对应 TD: Task 13（§6.13），联动 Task 16（§6.16）

## 1.1 摘要

本任务聚焦把 `FeatureExtractPES` 所依赖的 Claude Agent SDK project skill 机制正式接入当前 MVP 主链路。最小可用闭环是：`LLMClient` 默认以 `setting_sources=["project"]` 运行；`config` 层显式暴露该配置；`feature_extract.execute` 允许 `"Skill"` 工具；并且当 phase `cwd` 切到 `workspace/working` 时，项目根 `.claude/skills/` 能通过软链接稳定暴露到 `working/.claude/skills/`。

当前仓库里，`core/llm.py` 虽然已经使用 `claude_agent_sdk.query()`，但 `setting_sources` 被硬编码为空列表；`feature_extract.yaml` 尚未打开 `"Skill"`；`Workspace` 也还没有暴露 project skills 的能力。这意味着即便后续补了 skill 本体，Agent 也无法稳定自动发现。因此 `029` 的重点不是新增 skill 内容，而是把“配置来源 + 工具权限 + cwd 下可见性 + 测试”这四条链路一次接通。

## 1.2 审查点（Review Required）

1. `setting_sources` 默认值
   当前倾向默认仅启用 `("project",)`，不加载 `user` / `local`。
   原因：`docs/TD.md` 已明确要求默认只启用 project，避免个人环境 skill 污染研究结果。
2. Task 13 与 Task 16 的实现边界
   当前倾向在本任务内一并完成 `workspace/working/.claude/skills` 软链接暴露。
   原因：若只改 SDK 配置和 `allowed_tools`，真实运行时在 `cwd=working/` 下仍发现不到 project skill，Task 13 的目标无法成立。
3. DraftPES 的 skill 策略
   当前倾向不改 `config/pes/draft.yaml`，保持 Draft 默认不依赖 skill。
   原因：TD 明确要求当前阶段只给 `FeatureExtractPES.execute` 打开 `"Skill"`，避免扩大行为面。

## 1.3 拟议变更（Proposed Changes）

### A. 补齐任务029计划文件

- [NEW] [plans/active/029_claude_project_skill_integration.md](/home/yuchengzhang/Code/Herald2/plans/active/029_claude_project_skill_integration.md)
  - 固化 Task 13 的目标、审查点、实现边界与验证计划

### B. 让 LLM 配置显式支持 project skill 来源

- [MODIFY] [core/llm.py](/home/yuchengzhang/Code/Herald2/core/llm.py)
  - [MODIFY] `LLMConfig`
    - 新增 `setting_sources: tuple[str, ...] = ("project",)`
  - [MODIFY] `LLMClient._build_options()`
    - 将 `self.config.setting_sources` 透传给 `ClaudeAgentOptions.setting_sources`
- [MODIFY] [config/classconfig/llm.py](/home/yuchengzhang/Code/Herald2/config/classconfig/llm.py)
  - [MODIFY] `LLMConfig`
    - 同步新增 `setting_sources`
- [MODIFY] [config/herald.yaml](/home/yuchengzhang/Code/Herald2/config/herald.yaml)
  - [MODIFY] `llm.setting_sources`
    - 默认声明为 `["project"]`
- [MODIFY] [core/main.py](/home/yuchengzhang/Code/Herald2/core/main.py)
  - [MODIFY] `_build_llm_client()`
    - 把配置中的 `setting_sources` 传入运行时 `LLMConfig`

### C. 让 FeatureExtract execute 显式允许 Skill 工具

- [MODIFY] [config/pes/feature_extract.yaml](/home/yuchengzhang/Code/Herald2/config/pes/feature_extract.yaml)
  - [MODIFY] `phases.execute.allowed_tools`
    - 从 `["Bash", "Read", "Glob", "Grep"]` 调整为包含 `"Skill"`

### D. 在 working 目录暴露 project skills

- [MODIFY] [core/workspace.py](/home/yuchengzhang/Code/Herald2/core/workspace.py)
  - [NEW] `Workspace.expose_project_skills(project_root: str | Path) -> Path | None`
    - 当项目根存在 `.claude/skills/` 时，在 `working/.claude/skills` 创建软链接
    - 缺少目录时安全返回 `None`
  - [MODIFY] `Workspace.summary()`
    - 暴露当前可见的 `project_skills_dir`
- [MODIFY] [core/main.py](/home/yuchengzhang/Code/Herald2/core/main.py)
  - [MODIFY] `main()`
    - 在 `workspace.create()` 后调用 `workspace.expose_project_skills(project_root)`
    - 将结果记录到日志，缺失时仅提示不阻塞

### E. 补齐 Task 13 / 16 的测试

- [NEW] [tests/unit/test_llm_skill_config.py](/home/yuchengzhang/Code/Herald2/tests/unit/test_llm_skill_config.py)
  - [NEW] `test_llm_config_defaults_to_project_setting_source()`
  - [NEW] `test_llm_client_build_options_passes_setting_sources()`
  - [NEW] `test_feature_extract_yaml_enables_skill_tool()`
- [NEW] [tests/unit/test_workspace_skill_link.py](/home/yuchengzhang/Code/Herald2/tests/unit/test_workspace_skill_link.py)
  - [NEW] `test_expose_project_skills_creates_symlink()`
  - [NEW] `test_expose_project_skills_skips_when_missing()`
  - [NEW] `test_summary_exposes_project_skills_dir()`
- [MODIFY] [tests/unit/test_main_bootstrap.py](/home/yuchengzhang/Code/Herald2/tests/unit/test_main_bootstrap.py)
  - [NEW] `test_main_exposes_project_skills_when_present()`
- [NEW] [tests/integration/test_feature_extract_skill_flow.py](/home/yuchengzhang/Code/Herald2/tests/integration/test_feature_extract_skill_flow.py)
  - [NEW] `test_feature_extract_execute_receives_skill_tool_and_project_setting_sources()`
  - [NEW] `test_feature_extract_execute_uses_working_dir_with_visible_project_skills()`

### F. 文档同步

- [MODIFY] [docs/TD.md](/home/yuchengzhang/Code/Herald2/docs/TD.md)
  - 若本任务完成且测试通过，将 Task 13 / Task 16 状态同步为已实现或已完成语义
- [MODIFY] [docs/test_matrix.md](/home/yuchengzhang/Code/Herald2/docs/test_matrix.md)
  - 将新增测试文件登记到存在性清单

## 1.4 验证计划（Verification Plan）

1. 运行 `pytest tests/unit/test_llm_skill_config.py`
2. 运行 `pytest tests/unit/test_workspace_skill_link.py`
3. 运行 `pytest tests/unit/test_main_bootstrap.py`
4. 运行 `pytest tests/integration/test_feature_extract_skill_flow.py`
5. 回归运行
   - `pytest tests/unit/test_feature_extract_pes.py`
   - `pytest tests/integration/test_feature_extract_draft_pipeline.py`
6. 人工验证点
   - `LLMClient._build_options()` 产出的 `setting_sources == ["project"]` 或等价元组值
   - `feature_extract.yaml` 的 execute `allowed_tools` 包含 `"Skill"`
   - 若项目根存在 `.claude/skills/`，则 `workspace/working/.claude/skills` 为有效软链接
   - 若项目根不存在 `.claude/skills/`，主链路不会失败
