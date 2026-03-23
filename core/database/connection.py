from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from core.database.schema import ALL_DDL, INDEXES, VIEW_GENERATION_STATS


class DatabaseConnection:
    """SQLite 连接管理、schema 初始化、事务上下文。"""

    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")

        self.create_schema()

    def create_schema(self) -> None:
        cursor = self.conn.cursor()
        for ddl in ALL_DDL:
            cursor.execute(ddl)
        for idx_sql in INDEXES:
            cursor.execute(idx_sql)
        cursor.execute(VIEW_GENERATION_STATS)
        self.conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        统一事务入口：
            with db.connection.transaction():
                ...
        """
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def close(self) -> None:
        self.conn.close()
