#!/usr/bin/env python3
"""submission 约束预览 CLI。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from preview_support import summarize_submission_constraints


def _build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""

    parser = argparse.ArgumentParser(description="输出 sample_submission 约束预览。")
    parser.add_argument("--file", required=True, help="sample_submission.csv 路径")
    parser.add_argument("--test-file", default="", help="可选的 test.csv 路径")
    return parser


def main() -> None:
    """执行 submission 约束预览。"""

    parser = _build_parser()
    args = parser.parse_args()
    test_file = Path(args.test_file) if args.test_file else None
    payload = summarize_submission_constraints(
        sample_submission_path=Path(args.file),
        test_path=test_file,
    )
    sys.stdout.write(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n")


if __name__ == "__main__":
    main()
