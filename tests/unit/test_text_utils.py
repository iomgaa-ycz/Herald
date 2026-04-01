"""extract_summary_excerpt 单元测试。"""

from core.utils.text import extract_summary_excerpt

# ── 五小节格式正常提取 ──────────────────────────────────────

FIVE_SECTION_TEXT = """\
# 摘要
采用 LightGBM 模型对 tabular 数据进行二分类，AUC 达到 0.8123。核心发现是特征交叉对提升效果显著。

# 策略选择
选择 LightGBM 作为基线模型，使用 5 折交叉验证。

# 执行结果
AUC=0.8123，耗时 45 秒。

# 关键发现
特征交叉对 AUC 提升约 0.02。

# 建议方向
下次尝试 XGBoost 或神经网络。
"""


def test_extract_summary_excerpt_normal() -> None:
    """正常五小节格式，提取摘要第一段。"""
    result = extract_summary_excerpt(FIVE_SECTION_TEXT)
    assert "LightGBM" in result
    assert "AUC" in result
    assert "0.8123" in result
    # 不应包含其他小节内容
    assert "策略选择" not in result
    assert "执行结果" not in result


def test_extract_summary_excerpt_fallback() -> None:
    """无 '# 摘要' 标题时 fallback 到前 300 字符。"""
    text = "这是一段没有摘要标题的文本。包含了一些方案描述和结果信息。"
    result = extract_summary_excerpt(text)
    assert result == text


def test_extract_summary_excerpt_truncate() -> None:
    """超长段落截断到 300 字符。"""
    long_paragraph = "A" * 500
    text = f"# 摘要\n{long_paragraph}\n\n# 策略选择\n其他内容"
    result = extract_summary_excerpt(text, max_len=300)
    assert len(result) == 300


def test_extract_summary_excerpt_empty() -> None:
    """空文本返回空字符串。"""
    assert extract_summary_excerpt("") == ""
    assert extract_summary_excerpt("   ") == ""


def test_extract_summary_excerpt_custom_max_len() -> None:
    """自定义截断长度。"""
    result = extract_summary_excerpt(FIVE_SECTION_TEXT, max_len=10)
    assert len(result) <= 10


def test_extract_summary_excerpt_multiline_paragraph() -> None:
    """摘要段落跨多行（无空行分隔）。"""
    text = "# 摘要\n第一行内容\n第二行内容继续\n\n# 策略选择\n其他"
    result = extract_summary_excerpt(text)
    assert "第一行内容" in result
    assert "第二行内容继续" in result
