#!/usr/bin/env python3
"""完整竞赛数据预览 CLI。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from preview_support import render_preview_report


def _build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""

    parser = argparse.ArgumentParser(description="输出完整竞赛数据预览。")
    parser.add_argument("--data-dir", required=True, help="竞赛数据目录")
    parser.add_argument(
        "--sample-rows",
        type=int,
        default=5,
        help="表格预览时输出的样本记录数",
    )
    parser.add_argument(
        "--profile-rows",
        type=int,
        default=2000,
        help="表格统计时最多读取的行数",
    )
    return parser


def main() -> None:
    """执行完整竞赛数据预览。"""

    parser = _build_parser()
    args = parser.parse_args()
    report = render_preview_report(
        data_dir=Path(args.data_dir),
        sample_rows=args.sample_rows,
        profile_rows=args.profile_rows,
    )
    sys.stdout.write(f"{report}\n")


if __name__ == "__main__":
    main()
