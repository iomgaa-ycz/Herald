from __future__ import annotations

import sqlite3
from typing import Any


class BaseRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _execute(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> sqlite3.Cursor:
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        return cursor

    def _executemany(
        self,
        sql: str,
        seq_of_params: list[tuple[Any, ...]],
    ) -> sqlite3.Cursor:
        cursor = self._conn.cursor()
        cursor.executemany(sql, seq_of_params)
        return cursor

    def _fetchone(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> dict | None:
        row = self._execute(sql, params).fetchone()
        return dict(row) if row else None

    def _fetchall(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> list[dict]:
        rows = self._execute(sql, params).fetchall()
        return [dict(row) for row in rows]