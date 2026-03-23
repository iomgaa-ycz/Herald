from __future__ import annotations

import uuid
from datetime import UTC, datetime


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def create_run_id() -> str:
    """生成运行 ID，格式: 20240315_143025_abc12345"""
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{uuid.uuid4().hex[:8]}"
