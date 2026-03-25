"""AgentRegistry 单元测试。"""

from __future__ import annotations

from core.agent.registry import AgentRegistry


def setup_function() -> None:
    """每个测试前重置单例。"""

    AgentRegistry.reset()


def test_load_returns_complete_profile() -> None:
    """load 返回完整 AgentProfile。"""

    registry = AgentRegistry()
    profile = registry.load("aggressive")

    assert profile.name == "aggressive"
    assert profile.display_name == "激进探索者"
    assert len(profile.prompt_text) > 0


def test_list_all_returns_available_agents() -> None:
    """list_all 返回可用 Agent。"""

    registry = AgentRegistry()

    assert registry.list_all() == ["aggressive", "balanced", "conservative"]
