"""LLM project skill 配置测试。"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

from core.load_config import ConfigManager
from core.pes.config import load_pes_config


def _load_llm_module() -> types.ModuleType:
    """注入最小 Claude SDK 桩并重载 `core.llm`。"""

    sdk_stub = types.ModuleType("claude_agent_sdk")

    class _ClaudeAgentOptions:
        """记录初始化参数的最小 options 桩。"""

        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    async def _query_stub(*args: object, **kwargs: object) -> None:
        """提供最小异步生成器桩。"""

        del args, kwargs
        if False:
            yield None

    sdk_stub.AssistantMessage = object
    sdk_stub.ClaudeAgentOptions = _ClaudeAgentOptions
    sdk_stub.ResultMessage = object
    sdk_stub.TextBlock = object
    sdk_stub.ToolResultBlock = object
    sdk_stub.ToolUseBlock = object
    sdk_stub.UserMessage = object
    sdk_stub.query = _query_stub
    sys.modules["claude_agent_sdk"] = sdk_stub

    import core.llm as llm_module

    return importlib.reload(llm_module)


def test_llm_config_defaults_to_project_setting_source() -> None:
    """默认仅启用 project setting source。"""

    llm_module = _load_llm_module()

    config = llm_module.LLMConfig()

    assert config.setting_sources == ("project",)


def test_llm_client_build_options_passes_setting_sources() -> None:
    """`ClaudeAgentOptions` 会收到 `setting_sources`。"""

    llm_module = _load_llm_module()
    client = llm_module.LLMClient(
        llm_module.LLMConfig(setting_sources=("project", "local"))
    )

    options = client._build_options(allowed_tools=["Skill"])

    assert options.allowed_tools == ["Skill"]
    assert options.setting_sources == ["project", "local"]


def test_config_manager_reads_setting_sources_from_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """YAML 中的 setting_sources 能被正确解析。"""

    config_path = tmp_path / "herald.yaml"
    config_path.write_text(
        "\n".join(
            [
                "llm:",
                "  model: glm-5",
                "  max_tokens: 1024",
                "  max_turns: 4",
                "  permission_mode: bypassPermissions",
                "  setting_sources:",
                "    - project",
                "    - local",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["pytest", "--config", str(config_path)],
    )

    config = ConfigManager().parse()

    assert config.llm.setting_sources == ("project", "local")


def test_feature_extract_yaml_enables_skill_tool() -> None:
    """FeatureExtract execute phase 显式开启 Skill。"""

    config = load_pes_config("config/pes/feature_extract.yaml")

    assert config.get_phase("execute").allowed_tools is not None
    assert "Skill" in config.get_phase("execute").allowed_tools


def test_draft_summarize_yaml_enables_skill_tool() -> None:
    """Draft summarize phase 显式开启 Skill。"""

    config = load_pes_config("config/pes/draft.yaml")

    phase = config.get_phase("summarize")
    assert phase.allowed_tools is not None
    assert "Skill" in phase.allowed_tools
    assert phase.max_turns >= 2


def test_draft_summarize_format_skill_exists() -> None:
    """draft-summarize-format Skill 文件存在且可被 project skill 机制发现。"""

    skill_path = (
        Path(__file__).resolve().parents[2]
        / "core"
        / "prompts"
        / "skills"
        / "draft-summarize-format"
        / "SKILL.md"
    )
    assert skill_path.exists(), f"Skill 文件不存在: {skill_path}"

    content = skill_path.read_text(encoding="utf-8")
    assert "name: draft-summarize-format" in content
    assert "# 摘要" in content
    assert "# 策略选择" in content
    assert "# 执行结果" in content
    assert "# 关键发现" in content
    assert "# 建议方向" in content
