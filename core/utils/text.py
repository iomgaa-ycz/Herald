"""文本处理工具函数。"""

from __future__ import annotations

import re


def extract_summary_excerpt(text: str, max_len: int = 300) -> str:
    """从 summarize_insight 中提取 '# 摘要' 小节的第一段。

    解析逻辑：
    1. 匹配 '# 摘要' 标题后到下一个 '#' 标题之间的内容
    2. 取第一个非空段落
    3. 截断到 max_len 字符

    如果匹配不到 '# 摘要'，fallback 取 text 前 max_len 字符。

    Args:
        text: summarize_insight 全文
        max_len: 最大字符数，默认 300

    Returns:
        摘要摘录文本
    """
    if not text or not text.strip():
        return ""

    # Phase 1: 匹配 "# 摘要" 小节内容（到下一个 # 标题或文末）
    pattern = r"#\s*摘要\s*\n(.*?)(?=\n#\s|\Z)"
    match = re.search(pattern, text, flags=re.DOTALL)

    section = match.group(1).strip() if match else text.strip()

    # Phase 2: 取第一个非空段落（按空行分段）
    paragraphs = re.split(r"\n\s*\n", section)
    first_paragraph = ""
    for para in paragraphs:
        stripped = para.strip()
        if stripped:
            first_paragraph = stripped
            break

    if not first_paragraph:
        first_paragraph = section.strip()

    # Phase 3: 截断
    if len(first_paragraph) > max_len:
        return first_paragraph[:max_len]
    return first_paragraph
