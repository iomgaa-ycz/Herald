#!/usr/bin/env python3
"""描述文件预览 CLI。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from preview_support import summarize_description_file


def _build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""

    parser = argparse.ArgumentParser(description="输出描述文件预览。")
    parser.add_argument("--file", required=True, help="描述文件路径")
    parser.add_argument(
        "--max-lines",
        type=int,
        default=40,
        help="最多读取多少行",
    )
    return parser


def main() -> None:
    """执行描述文件预览。"""

    parser = _build_parser()
    args = parser.parse_args()
    payload = summarize_description_file(
        file_path=Path(args.file),
        max_lines=args.max_lines,
    )
    sys.stdout.write(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n")


if __name__ == "__main__":
    main()
