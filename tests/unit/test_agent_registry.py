"""AgentRegistry 单元测试。"""

from __future__ import annotations

from pathlib import Path

from core.agent.registry import AgentRegistry


def setup_function() -> None:
    """每个测试前重置单例。"""

    AgentRegistry.reset()


def test_load_returns_complete_profile() -> None:
    """load 返回完整 AgentProfile。"""

    registry = AgentRegistry()
    profile = registry.load("kaggle_master")

    assert profile.name == "kaggle_master"
    assert profile.display_name == "Kaggle Master"
    assert len(profile.prompt_text) > 0
    assert "你是 `kaggle_master`" in profile.prompt_text
    assert "执行风格与策略偏好" in profile.prompt_text


def test_system_context_only_contains_global_rules() -> None:
    """system_context 只承载全局规则，不承载 Agent 身份。"""

    fragment_path = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "prompts"
        / "fragments"
        / "system_context.md"
    )
    content = fragment_path.read_text(encoding="utf-8")

    assert "全局系统规则" in content
    assert "你是一个自动化机器学习竞赛 Agent" not in content
    assert "以下规则对所有 Agent、所有 phase、所有任务上下文恒成立" in content


def test_list_all_returns_available_agents() -> None:
    """list_all 返回可用 Agent。"""

    registry = AgentRegistry()

    assert registry.list_all() == ["kaggle_master"]
