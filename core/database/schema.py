DDL_SOLUTIONS = """
CREATE TABLE IF NOT EXISTS solutions (
    id TEXT PRIMARY KEY,
    generation INTEGER NOT NULL,
    lineage TEXT,
    schema_task_type TEXT,
    operation TEXT,
    mutated_slot TEXT,
    parent_ids TEXT,
    fitness REAL,
    metric_name TEXT,
    metric_value REAL,
    metric_direction TEXT,
    run_id TEXT,
    workspace_dir TEXT,
    solution_file_path TEXT,
    submission_file_path TEXT,
    plan_summary TEXT,
    execute_summary TEXT,
    summarize_insight TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    finished_at TEXT
)
"""

DDL_GENES = """
CREATE TABLE IF NOT EXISTS genes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    solution_id TEXT NOT NULL,
    slot TEXT NOT NULL,
    description TEXT,
    rationale TEXT,
    contract_json TEXT,
    constraints_json TEXT,
    version INTEGER DEFAULT 1,
    code_anchor TEXT,
    FOREIGN KEY(solution_id) REFERENCES solutions(id) ON DELETE CASCADE
)
"""

DDL_CODE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS code_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    solution_id TEXT NOT NULL,
    full_code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(solution_id) REFERENCES solutions(id) ON DELETE CASCADE
)
"""

DDL_LLM_CALLS = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id TEXT PRIMARY KEY,
    solution_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    purpose TEXT,
    model TEXT,
    input_messages_json TEXT,
    output_text TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    latency_ms REAL,
    cost_usd REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(solution_id) REFERENCES solutions(id) ON DELETE CASCADE
)
"""

DDL_EXEC_LOGS = """
CREATE TABLE IF NOT EXISTS exec_logs (
    id TEXT PRIMARY KEY,
    solution_id TEXT NOT NULL,
    command TEXT,
    stdout TEXT,
    stderr TEXT,
    exit_code INTEGER,
    duration_ms REAL,
    metrics_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(solution_id) REFERENCES solutions(id) ON DELETE CASCADE
)
"""

DDL_CONTRACT_CHECKS = """
CREATE TABLE IF NOT EXISTS contract_checks (
    id TEXT PRIMARY KEY,
    solution_id TEXT NOT NULL,
    slot TEXT,
    check_type TEXT NOT NULL,
    passed INTEGER NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(solution_id) REFERENCES solutions(id) ON DELETE CASCADE
)
"""

DDL_L2_INSIGHTS = """
CREATE TABLE IF NOT EXISTS l2_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slot TEXT NOT NULL,
    task_type TEXT NOT NULL,
    pattern TEXT NOT NULL,
    insight TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(slot, task_type, pattern)
)
"""

DDL_L2_EVIDENCE = """
CREATE TABLE IF NOT EXISTS l2_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    insight_id INTEGER NOT NULL,
    solution_id TEXT,
    evidence_type TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(insight_id) REFERENCES l2_insights(id) ON DELETE CASCADE
)
"""

DDL_L3_WISDOM = """
CREATE TABLE IF NOT EXISTS l3_wisdom (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    wisdom TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

DDL_L3_SOURCES = """
CREATE TABLE IF NOT EXISTS l3_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wisdom_id INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(wisdom_id) REFERENCES l3_wisdom(id) ON DELETE CASCADE
)
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_solutions_generation ON solutions(generation)",
    "CREATE INDEX IF NOT EXISTS idx_solutions_status ON solutions(status)",
    "CREATE INDEX IF NOT EXISTS idx_solutions_fitness ON solutions(fitness)",
    "CREATE INDEX IF NOT EXISTS idx_genes_solution_id ON genes(solution_id)",
    "CREATE INDEX IF NOT EXISTS idx_genes_slot ON genes(slot)",
    "CREATE INDEX IF NOT EXISTS idx_snapshots_solution_id ON code_snapshots(solution_id)",
    "CREATE INDEX IF NOT EXISTS idx_llm_calls_solution_id ON llm_calls(solution_id)",
    "CREATE INDEX IF NOT EXISTS idx_exec_logs_solution_id ON exec_logs(solution_id)",
    "CREATE INDEX IF NOT EXISTS idx_contract_checks_solution_id ON contract_checks(solution_id)",
    "CREATE INDEX IF NOT EXISTS idx_l2_insights_lookup ON l2_insights(slot, task_type, pattern)",
    "CREATE INDEX IF NOT EXISTS idx_l2_evidence_insight_id ON l2_evidence(insight_id)",
]

VIEW_GENERATION_STATS = """
CREATE VIEW IF NOT EXISTS generation_stats AS
SELECT
    s.generation AS generation,
    COUNT(DISTINCT s.id) AS total_solutions,
    AVG(s.fitness) AS avg_fitness,
    MAX(s.fitness) AS best_fitness,
    MIN(s.fitness) AS worst_fitness,
    SUM(COALESCE(lc.cost_usd, 0)) AS total_cost_usd,
    SUM(COALESCE(lc.tokens_in, 0)) AS total_tokens_in,
    SUM(COALESCE(lc.tokens_out, 0)) AS total_tokens_out,
    MIN(s.created_at) AS start_time,
    MAX(s.finished_at) AS end_time
FROM solutions s
LEFT JOIN llm_calls lc ON lc.solution_id = s.id
GROUP BY s.generation
"""

ALL_DDL = [
    DDL_SOLUTIONS,
    DDL_GENES,
    DDL_CODE_SNAPSHOTS,
    DDL_LLM_CALLS,
    DDL_EXEC_LOGS,
    DDL_CONTRACT_CHECKS,
    DDL_L2_INSIGHTS,
    DDL_L2_EVIDENCE,
    DDL_L3_WISDOM,
    DDL_L3_SOURCES,
]
