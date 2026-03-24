# CLAUDE.md

> [!URGENT]
> **研究性项目 (Research Project)**
> 1. 本项目为 MVP（最小可行性产品），严禁过度工程化。
> 2. 你的所有思考过程和回复必须使用 **简体中文**。

## 1. 项目元数据 (Metadata)

- **核心目标**: 构建自动化科mle-bench竞赛Agent系统，可以生成-调试-执行-提交mle-bench竞赛并取得奖牌。
- **项目类型**: MVP / 研究性项目
- **后端架构**: Python 3.11+
- **版本管理**: Git
- **Conda 环境**: herald

## 2. 常用命令 (Commands)

### 环境管理
```bash
conda activate herald
```

### 代码质量
```bash
ruff check . --fix
ruff format .
```

### 测试
```bash
```

### 主要 CLI
```bash
python core/main.py [subcommand]
```

## 3. 标准作业程序 (Standard Operating Procedure)

### Phase 1: 规划与设计 (Planning)

1. **查阅规格 (Read Specs)**
   必须仔细阅读 `docs/` 下文档：
   - `docs/architecture.md` — 系统架构
   - `docs/experiment_plan.md` — 实验方案
   - `docs/TD.md` — 技术方案（模块接口规格）

2. **计划 (Plan)**
   使用计划模式撰写计划，包含：
   - **1.1 摘要 (Summary)** — 用 1-3 句话说明意图
   - **1.2 审查点 (Review Required)** — 列出需要确认的设计决策
   - **1.3 拟议变更 (Proposed Changes)** — 精确到函数级别，标识 `[NEW]`/`[MODIFY]`/`[DELETE]`
   - **1.4 验证计划 (Verification Plan)** — 怎么确认做对了

3. **等待审核 (Wait)**
   - **交互模式（人类操作）**：暂停等待用户审核，未经批准不得编码
   - **headless 模式（Lead Agent 调度）**：计划已写入文件，Lead Agent 会读取并审核。若审查点简单则直接批准执行，复杂则转交用户确认

### Phase 2: 执行与验证 (Execution & Verification)

1. **编码** — 按计划（或 `plans/*.md` 中的方案）逐步实现
2. **验证** — 运行测试
   - 失败 → 回到编码修复
   - 成功 → 进入 Phase 3

### Phase 3: 收尾与交付 (Finalization)

1. **文档同步** — 检查 `docs/` 是否因代码变更而过时，立即更新
2. **提交** — 按 Conventional Commits 规范提交（由 Lead Agent 执行）

## 4. 核心规则 (Rules)

### 4.1 代码开发规范
- **类型系统**: 强制所有函数签名包含完整类型注解（`Union`, `Dict`, `Optional` 等）
- **文档**: 所有模块、类、方法必须包含中文 Docstring（功能、参数、返回值）
- **MVP 原则**: 严禁过度工程化。能用简单方案解决的不要用复杂方案
- **代码组织**: 阶段化注释 (`# Phase 1: ...`, `# Phase 2: ...`)
- **命名**: PascalCase 类名，描述性变量名，`_` 前缀私有变量
- **导入顺序**: 标准库 → 第三方 → 项目内部，各组之间空行分隔
- **日志**: 使用项目日志系统，**严禁 print() 调试输出**
- **功能修改**: 不考虑向后兼容，代码简洁优先

### 4.2 配置管理
- dataclass（无默认值，纯类型定义）+ YAML（全量非敏感配置）+ `.env`（敏感信息）
- 优先级：CLI args > `.env` > YAML
- 超参数禁止硬编码

### 4.3 测试组织


### 4.4 Git 工作流
- 格式: Conventional Commits (`feat:`/`fix:`/`docs:`/`refactor:`/`test:`)
- **严禁** commit message 中添加 AI 标识
- 每个逻辑变更一个 commit，不要堆积

### 4.5 main.py 规范
- `core/main.py` 是生产 CLI 入口，不含 demo 或验证逻辑
- 模块验证通过 `tests/integration/test_{module}_flow.py` + Markdown 报告完成
- **严禁在 main.py 中使用 MagicMock/玩具参数**

### 4.6 Agent 测试输出规范

## 5. 上下文获取与迷途指南 (Context & Navigation)

> 🧭 **迷路了？** 按以下顺序阅读文档：

| 需求 | 文档路径 | 说明 |
|------|----------|------|
| 项目目标与背景 | `README.md` | 核心业务逻辑 |
| 架构与模块设计 | `docs/architecture.md` | 整体架构、三大子系统、集群智能调度 |

## 6. 输出规范
- 所有输出语言: **简体中文**
- 优先使用: 简洁文本、伪代码、表格、流程图(Mermaid)、项目符号列表
- 避免: 大段完整代码、冗长自然语言解释
- 核心原则: **用最少字符传递最多信息**
