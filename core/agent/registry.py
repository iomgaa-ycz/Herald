"""Agent 注册表实现。"""

from __future__ import annotations

from pathlib import Path

import yaml

from core.agent.profile import AgentProfile


class AgentRegistry:
    """Agent 注册表。"""

    _instance: AgentRegistry | None = None

    def __init__(self, agents_dir: Path | str | None = None) -> None:
        """初始化 Agent 注册表。"""

        self.agents_dir = self._resolve_agents_dir(agents_dir)
        self._cache: dict[str, AgentProfile] = {}

    @classmethod
    def get(cls, agents_dir: Path | str | None = None) -> AgentRegistry:
        """获取全局单例。"""

        resolved_dir = cls._resolve_agents_dir(agents_dir)
        if cls._instance is None or resolved_dir != cls._instance.agents_dir:
            cls._instance = cls(resolved_dir)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例。"""

        cls._instance = None

    @staticmethod
    def _resolve_agents_dir(agents_dir: Path | str | None) -> Path:
        """解析 Agent 配置目录。"""

        if agents_dir is None:
            return (
                Path(__file__).resolve().parents[2] / "config" / "agents"
            ).resolve()
        return Path(agents_dir).expanduser().resolve()

    def load(self, name: str) -> AgentProfile:
        """加载并缓存指定 Agent。"""

        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Agent 名称不能为空")

        if normalized_name in self._cache:
            return self._cache[normalized_name]

        config_path = self.agents_dir / f"{normalized_name}.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"Agent 配置不存在: {config_path}")

        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"Agent 配置格式非法: {config_path}")

        agent_name = str(payload.get("name", normalized_name)).strip()
        display_name = str(payload.get("display_name", agent_name)).strip()
        prompt_file = str(payload.get("prompt_file", "")).strip()
        if not agent_name:
            raise ValueError(f"Agent 配置缺少 name: {config_path}")
        if not display_name:
            raise ValueError(f"Agent 配置缺少 display_name: {config_path}")
        if not prompt_file:
            raise ValueError(f"Agent 配置缺少 prompt_file: {config_path}")

        prompt_path = (self.agents_dir / prompt_file).resolve()
        if not prompt_path.exists():
            raise FileNotFoundError(f"Agent Prompt 不存在: {prompt_path}")

        profile = AgentProfile(
            name=agent_name,
            display_name=display_name,
            prompt_text=prompt_path.read_text(encoding="utf-8").strip(),
        )
        self._cache[normalized_name] = profile
        return profile

    def reload(self, name: str) -> AgentProfile:
        """强制重新加载指定 Agent。"""

        normalized_name = name.strip()
        self._cache.pop(normalized_name, None)
        return self.load(normalized_name)

    def list_all(self) -> list[str]:
        """列出所有可用 Agent 名称。"""

        if not self.agents_dir.exists():
            return []
        return sorted(path.stem for path in self.agents_dir.glob("*.yaml"))
