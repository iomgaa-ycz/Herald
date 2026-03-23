from __future__ import annotations

import json
import uuid
from typing import Any

from core.database.repositories.base import BaseRepository
from core.utils.utils import utc_now_iso


class TracingRepository(BaseRepository):
    """L1 追踪：LLM 调用、执行日志、契约检查。"""

    def log_llm_call(
        self,
        solution_id: str,
        phase: str,
        purpose: str | None = None,
        model: str | None = None,
        input_messages: list[dict[str, Any]] | None = None,
        output_text: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        latency_ms: float | None = None,
        cost_usd: float | None = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        self._execute(
            """
            INSERT INTO llm_calls (
                id, solution_id, phase, purpose, model,
                input_messages_json, output_text, tokens_in,
                tokens_out, latency_ms, cost_usd, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                solution_id,
                phase,
                purpose,
                model,
                json.dumps(input_messages) if input_messages is not None else None,
                output_text,
                tokens_in,
                tokens_out,
                latency_ms,
                cost_usd,
                utc_now_iso(),
            ),
        )
        return event_id

    def log_exec(
        self,
        solution_id: str,
        command: str,
        stdout: str | None = None,
        stderr: str | None = None,
        exit_code: int | None = None,
        duration_ms: float | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        self._execute(
            """
            INSERT INTO exec_logs (
                id, solution_id, command, stdout, stderr,
                exit_code, duration_ms, metrics_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                solution_id,
                command,
                stdout,
                stderr,
                exit_code,
                duration_ms,
                json.dumps(metrics) if metrics is not None else None,
                utc_now_iso(),
            ),
        )
        return event_id

    def log_contract_check(
        self,
        solution_id: str,
        check_type: str,
        passed: bool,
        detail: str | None = None,
        slot: str | None = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        self._execute(
            """
            INSERT INTO contract_checks (
                id, solution_id, slot, check_type, passed, detail, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                solution_id,
                slot,
                check_type,
                1 if passed else 0,
                detail,
                utc_now_iso(),
            ),
        )
        return event_id

    def get_llm_calls(self, solution_id: str) -> list[dict]:
        rows = self._fetchall(
            "SELECT * FROM llm_calls WHERE solution_id = ? ORDER BY created_at ASC",
            (solution_id,),
        )
        for row in rows:
            if row.get("input_messages_json"):
                try:
                    row["input_messages"] = json.loads(row["input_messages_json"])
                except Exception:
                    row["input_messages"] = None
        return rows

    def get_exec_logs(self, solution_id: str) -> list[dict]:
        rows = self._fetchall(
            "SELECT * FROM exec_logs WHERE solution_id = ? ORDER BY created_at ASC",
            (solution_id,),
        )
        for row in rows:
            if row.get("metrics_json"):
                try:
                    row["metrics"] = json.loads(row["metrics_json"])
                except Exception:
                    row["metrics"] = None
        return rows

    def get_contract_checks(self, solution_id: str) -> list[dict]:
        return self._fetchall(
            """
            SELECT * FROM contract_checks
            WHERE solution_id = ?
            ORDER BY created_at ASC
            """,
            (solution_id,),
        )
