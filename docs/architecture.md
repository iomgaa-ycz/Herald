# Herald2 架构设计

> **状态**: 骨架文档，待补充
> **更新**: 2026-03-24

---

## 1. 核心定位

[待补充：一段话描述项目做什么、核心创新点]

设计原则:
- MVP 原则：能用简单方案解决的不要用复杂方案
- [待补充]
- [待补充]

## 2. 系统总览

[待补充：ASCII 流程图或 Mermaid 图，展示整体流程]

```
[输入] → [模块A] → [模块B] → [输出]
           ↓
        [模块C]
```

## 3. 各子系统详细设计

### 3.1 PES Engine

[待补充：数据流图 + 核心算法伪代码 + 设计决策]

### 3.2 HeraldDB

[待补充]

### 3.3 Sandbox

[待补充]

## 4. 文件结构

```
Herald2/
├── core/                   # 核心模块
│   ├── main.py             # CLI 入口
│   ├── pes_engine.py       # PES 引擎
│   ├── llm.py              # LLM 客户端
│   ├── database/           # 数据库层
│   └── ...
├── config/                 # 配置文件
├── tests/                  # 测试
├── docs/                   # 文档
│   ├── architecture.md     # 本文件
│   ├── experiment_plan.md  # 实验方案
│   ├── TD.md               # 技术方案
│   ├── coding_guide.md     # 代码规范
│   └── harness_engineering.md
├── plans/                  # 执行计划
├── CLAUDE.md               # Agent 指南
└── AGENTS.md               # Agent 指南（副本）
```

## 5. 可训练 vs 冻结组件

[待补充：N/A，本项目无模型训练]

---

### 必须包含的要素清单

- [ ] 核心定位（一段话）
- [ ] 设计原则（3-5 条）
- [ ] 可视化的系统流程图（ASCII 或 Mermaid）
- [ ] 每个子系统的数据流图
- [ ] 设计决策及理由
- [ ] 文件结构目录树
