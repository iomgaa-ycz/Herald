#!/usr/bin/env python3
"""表格文件预览 CLI。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from preview_support import summarize_table_file


def _build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""

    parser = argparse.ArgumentParser(description="输出 train/test 表格预览。")
    parser.add_argument("--file", required=True, help="CSV 文件路径")
    parser.add_argument(
        "--sample-rows",
        type=int,
        default=5,
        help="输出多少条样本记录",
    )
    parser.add_argument(
        "--profile-rows",
        type=int,
        default=2000,
        help="统计时最多读取多少行",
    )
    return parser


def main() -> None:
    """执行表格文件预览。"""

    parser = _build_parser()
    args = parser.parse_args()
    payload = summarize_table_file(
        csv_path=Path(args.file),
        sample_rows=args.sample_rows,
        profile_rows=args.profile_rows,
    )
    sys.stdout.write(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n")


if __name__ == "__main__":
    main()
