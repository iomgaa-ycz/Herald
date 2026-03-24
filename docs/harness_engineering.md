# Herald2 Harness Engineering

> **定位**: 本文档阐述 Herald2 的 Harness 工程哲学——让 AI Agent 能高效、可靠地完成 ML 竞赛任务的基础设施设计原则。
> **更新**: 2026-03-24
> **状态**: 持续演进

---

## 1. 核心前提：Agent 看不见的知识不存在

Herald2 是一个由 AI Agent 主导的自动化系统。**Agent 的上下文窗口是稀缺资源**，它在运行时无法访问存在于 Slack、脑海或口头讨论中的知识。

**推论**：
- 架构决策必须写进 `docs/`
- 技术债务必须追踪在 `plans/tech_debt.md`
- 实验洞察必须落入 `docs/archivement.md` 或 DB
- 临时讨论的结论必须在结束后同步进 repo

这是 Herald2 所有文档规范的根本动机，不是形式主义。

---

## 2. Herald2 的 Harness 层次

```
┌─────────────────────────────────────────────────┐
│  L3: 竞赛环境可读性                               │
│      沙箱执行日志、GPU 指标、提交分数              │
│      → Agent 能自主验证"当前方案是否更好"         │
├─────────────────────────────────────────────────┤
│  L2: 执行结果可读性                               │
│      HeraldDB：exec_logs / solutions / genes     │
│      → Agent 能查询历史，进行方案间对比            │
├─────────────────────────────────────────────────┤
│  L1: 文档知识可读性                               │
│      docs/ 作为知识记录系统                       │
│      CLAUDE.md 作为目录（非百科全书）             │
└─────────────────────────────────────────────────┘
```

### L1：文档层（当前重点）

`CLAUDE.md` 是导航地图，应保持 ≤150 行，指向 `docs/` 中的具体文档。
`docs/` 是知识库，每个文档覆盖一个主题，由专职的"文档维护"任务保持新鲜。

| 文档 | 职责 |
|------|------|
| `docs/architecture.md` | 系统架构全景，模块依赖关系 |
| `docs/TD.md` | 模块接口规格（函数签名级别） |
| `docs/experiment_plan.md` | 当前实验方案与假设 |
| `docs/harness_engineering.md` | 本文档：Harness 工程哲学 |
| `docs/coding_guide.md` | 代码规范与风格 |
| `docs/archivement.md` | 实验发现与历史成果 |
| `plans/tech_debt.md` | 已知技术债务追踪 |

### L2：数据库层（进行中）

`HeraldDB` 已有的表：`solutions`, `genes`, `exec_logs`, `llm_calls`。

**Harness 要求**：Summarize 阶段的 Agent 必须能通过查询 DB 回答：
- "这个 Gene 版本的得分是否高于上一版？"
- "历史上哪种 MODEL 策略在此类赛题表现最好？"

目前缺失：`solutions` 表的 `score` 字段及排行查询接口。这是 L2 的主要缺口。

### L3：执行环境层（待建）

沙箱执行后的日志、错误栈、资源占用应以结构化形式存入 DB，使 PES 的 Execute→Summarize 循环能自主判断：
- OOM / 超时 → 触发 Gene 修改
- 分数下降 → 回滚到上一个 Gene 版本
- 训练曲线异常 → 调整超参数 Gene

---

## 3. 架构约束机械化执行

Herald2 的架构规则写在 `docs/coding_guide.md`，但**文档规则不会自动执行**。

当前已有：`ruff check` + `ruff format`（格式层）

**待建**：`scripts/check_conventions.py`，检查内容：

```
□ 所有流程编排函数是否有 # Phase N: 注释
□ 是否有 print() 调试语句（非 CLI 入口）
□ 核心函数参数是否 ≤ 5 个
□ 新增文档是否注册进 CLAUDE.md 导航表
```

**关键原则**：linter 错误信息本身应包含修复建议，这样 Agent 收到 CI 失败时能直接修复。

---

## 4. 执行计划作为一等公民

Herald2 的开发工作和实验任务都通过 `plans/` 目录管理。

```
plans/
├── active/          # 当前正在执行的计划
├── completed/       # 已完成的计划（归档）
└── tech_debt.md     # 技术债务追踪（持续更新）
```

计划文件格式见 `plans/README.md`。

**核心价值**：Lead Agent 在跨 session 工作时，通过读取 `plans/active/` 即可恢复上下文，无需人类手工交接。

---

## 5. 人类工程师的角色定位

类比 OpenAI Codex 团队的经验，Herald2 中人类的工作重心：

| 高价值工作（人类做） | 低价值工作（Agent 做） |
|---------------------|----------------------|
| 设计 GenomeSchema（哪些 Slot，契约是什么） | 实现每个 Slot 的具体代码 |
| 判断竞赛策略方向 | 调试运行时错误 |
| 审核关键架构决策 | 补全测试、文档、日志 |
| 定义"什么是成功" | 迭代超参数组合 |

当 Agent 遇到阻碍时，人类的正确响应是：**识别 Harness 缺失了什么**，而不是手工修复问题本身。

---

## 6. 熵管理：防止代码库腐烂

高频 Agent 写代码会积累技术债。Herald2 的应对策略：

1. **黄金原则**（在 `docs/coding_guide.md` 中定义，通过 linter 机械执行）
2. **tech_debt.md**（每次发现技术债时记录，而非立即修复）
3. **定期文档核查**（每个 milestone 结束时，检查 `docs/` 是否与代码实际行为一致）

---

## 7. 对 mle-bench 竞赛的特殊 Harness 考量

Herald2 的目标场景带来独特需求：

- **依赖库约束**：GenomeSchema 的 SlotContract 应推荐训练数据充足的库（sklearn / lightgbm / pandas），避免 Agent 选择 LLM 不熟悉的冷门库
- **评分可观测**：竞赛提交后的得分必须进入 DB，形成 Gene 演化压力
- **长时间运行**：PES 循环可能运行数小时，Harness 必须支持断点续跑（基于 DB 状态恢复）
- **隔离执行**：每次 Gene 变更在独立沙箱中验证，避免污染全局环境

---

*参考来源：OpenAI Engineering Blog "Engineering in an Agent-First World with Codex" (2026-02-11)*
