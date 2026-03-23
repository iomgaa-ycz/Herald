# HeraldDB Architecture

## Core concepts

### Solution
一次候选解 / 实验个体 / 代码方案。

存储在 `solutions` 表中，包含：
- generation
- lineage
- operation
- mutated_slot
- parent_ids
- fitness
- metric
- artifact paths
- status
- timestamps

### Gene
Solution 内部按 slot 拆分后的模块描述。

存储在 `genes` 表中，包含：
- slot
- description
- rationale
- contract
- constraints
- version
- code_anchor

### Snapshot
某个 solution 的完整代码快照。

存储在 `code_snapshots` 表中。

### Tracing (L1)
过程级追踪日志，包括：
- `llm_calls`
- `exec_logs`
- `contract_checks`

### L2
从 solution 经验中沉淀出的 slot/task/pattern 级 insight。

包含：
- `l2_insights`
- `l2_evidence`

### L3
更高层抽象 wisdom，目前仅建表预留：
- `l3_wisdom`
- `l3_sources`

---

## Layering

### connection.py
负责：
- SQLite 连接
- schema 初始化
- 事务上下文

### repositories/*
负责实体级读写：
- solution.py
- gene.py
- snapshot.py
- tracing.py
- l2.py

### queries/*
负责只读分析查询：
- population.py
- lineage.py

### herald_db.py
统一门面，聚合各 repo / query，提供便捷方法。

---

## Typical write flow

1. insert solution
2. insert genes
3. insert snapshot
4. log llm / exec / contract
5. update solution status
6. optionally upsert l2 insight

建议把相关写入放到同一个 transaction 里。