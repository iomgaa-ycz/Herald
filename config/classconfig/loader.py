"""统一配置管理模块。

支持：
- 从 YAML 文件加载配置
- CLI 参数覆盖（优先级高于 YAML）
- 导出为细分配置（LLMConfig、PESConfig 等）
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from config.classconfig.herald import HeraldConfig
from config.classconfig.llm import LLMConfig
from config.classconfig.pes import PESConfig, PhaseConfig

DEFAULT_CONFIG_PATH = "config/herald.yaml"


class Config:
    """统一配置管理器。

    使用方式：
        # 从 YAML 加载
        config = Config.from_yaml("config/herald.yaml")

        # 从 YAML + CLI 参数加载
        config = Config.from_yaml_and_cli()

        # 导出细分配置
        llm_config = config.get_llm_config()
        pes_config = config.get_pes_config()
    """

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        """初始化配置。

        Args:
            data: 配置数据字典，支持嵌套结构
        """
        self._data: dict[str, Any] = data or {}
        self._flat_data: dict[str, Any] = self._flatten(self._data)

    @staticmethod
    def _flatten(data: dict[str, Any], parent_key: str = "", sep: str = "_") -> dict[str, Any]:
        """将嵌套字典展平为单层字典。

        例如: {"llm": {"model": "gpt"}} -> {"llm_model": "gpt"}
        """
        items: list[tuple[str, Any]] = []
        for key, value in data.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key
            if isinstance(value, dict):
                items.extend(Config._flatten(value, new_key, sep).items())
            else:
                items.append((new_key, value))
        return dict(items)

    @staticmethod
    def _unflatten(data: dict[str, Any], sep: str = "_") -> dict[str, Any]:
        """将展平的字典还原为嵌套结构。"""
        result: dict[str, Any] = {}
        for key, value in data.items():
            parts = key.split(sep)
            current = result
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        return result

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> Config:
        """从 YAML 文件加载配置。

        Args:
            path: YAML 文件路径，默认为 config/herald.yaml

        Returns:
            Config 实例
        """
        config_path = Path(path or DEFAULT_CONFIG_PATH).expanduser().resolve()
        if not config_path.exists():
            return cls({})

        content = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content) or {}
        return cls(data)

    @classmethod
    def from_yaml_and_cli(cls, path: str | Path | None = None, args: list[str] | None = None) -> Config:
        """从 YAML 文件和 CLI 参数加载配置，CLI 优先级更高。

        Args:
            path: YAML 文件路径，默认为 config/herald.yaml
            args: CLI 参数列表，默认为 sys.argv[1:]

        Returns:
            合并后的 Config 实例
        """
        # 先加载 YAML 配置
        config = cls.from_yaml(path)

        # 解析 CLI 参数
        parser = cls._create_argparser(config._flat_data)
        cli_args = parser.parse_args(args)

        # CLI 参数覆盖 YAML（只覆盖非 None 的值）
        for key, value in vars(cli_args).items():
            if value is not None:
                config._flat_data[key] = value

        # 重建嵌套结构
        config._data = cls._unflatten(config._flat_data)
        return config

    @staticmethod
    def _create_argparser(defaults: dict[str, Any]) -> argparse.ArgumentParser:
        """根据配置项自动生成 CLI 参数解析器。

        Args:
            defaults: 默认值字典

        Returns:
            配置好的 ArgumentParser
        """
        parser = argparse.ArgumentParser(
            description="Herald - AI 驱动的代码生成与执行系统",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )

        # 添加配置文件路径参数
        parser.add_argument(
            "--config",
            type=str,
            default=DEFAULT_CONFIG_PATH,
            help="配置文件路径",
        )

        # 根据配置项自动添加参数
        for key, default_value in defaults.items():
            arg_name = f"--{key.replace('_', '-')}"
            arg_type = type(default_value) if default_value is not None else str

            # 处理不同类型
            if isinstance(default_value, bool):
                parser.add_argument(
                    arg_name,
                    action="store_true",
                    default=None,
                    help=f"设置 {key}",
                )
                parser.add_argument(
                    f"--no-{key.replace('_', '-')}",
                    dest=key,
                    action="store_false",
                    help=f"取消设置 {key}",
                )
            elif arg_type in (int, float, str):
                parser.add_argument(
                    arg_name,
                    type=arg_type,
                    default=None,
                    help=f"{key} (默认: {default_value})",
                )
            elif arg_type is list:
                parser.add_argument(
                    arg_name,
                    nargs="*",
                    default=None,
                    help=f"{key} (默认: {default_value})",
                )
            else:
                # 其他类型作为字符串处理
                parser.add_argument(
                    arg_name,
                    type=str,
                    default=None,
                    help=f"{key} (默认: {default_value})",
                )

        return parser

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（支持嵌套键，如 llm.model）。"""
        # 先尝试展平键
        if key in self._flat_data:
            return self._flat_data[key]

        # 尝试嵌套访问
        parts = key.split(".")
        current = self._data
        for part in parts:
            if not isinstance(current, dict):
                return default
            current = current.get(part)
            if current is None:
                return default
        return current

    def get_llm_config(self) -> LLMConfig:
        """导出 LLMConfig。"""
        return LLMConfig(
            model=self.get("llm_model", self.get("llm.model", "glm-5")),
            max_tokens=self.get("llm_max_tokens", self.get("llm.max_tokens", 32 * 1024)),
            max_turns=self.get("llm_max_turns", self.get("llm.max_turns", 16)),
            api_key=self.get("llm_api_key", self.get("llm.api_key")),
        )

    def get_pes_config(self) -> PESConfig:
        """导出 PESConfig。

        Note: PES 配置通常从独立的 YAML 文件加载，
        这里提供从主配置获取的基本支持。
        """
        phases_data = self.get("phases", {})
        phases: dict[str, PhaseConfig] = {}

        if isinstance(phases_data, dict):
            for phase_name, phase_data in phases_data.items():
                if isinstance(phase_data, dict):
                    phases[phase_name] = PhaseConfig(
                        name=phase_name,
                        prompt_template=phase_data.get("prompt_template", ""),
                        tool_names=phase_data.get("tool_names", []),
                        max_retries=phase_data.get("max_retries", 1),
                    )

        return PESConfig(
            name=self.get("pes_name", self.get("pes.name", "")),
            operation=self.get("pes_operation", self.get("pes.operation", "")),
            solution_file_name=self.get("pes_solution_file_name", self.get("pes.solution_file_name", "")),
            submission_file_name=self.get("pes_submission_file_name", self.get("pes.submission_file_name")),
            phases=phases,
        )

    def get_herald_config(self) -> HeraldConfig:
        """导出 HeraldConfig（组合 LLM 和 PES 配置）。"""
        return HeraldConfig(
            llm=self.get_llm_config(),
            pes=self.get_pes_config(),
        )

    def to_dict(self) -> dict[str, Any]:
        """返回配置的字典表示。"""
        return self._data.copy()

    def update(self, key: str, value: Any) -> None:
        """更新配置值。"""
        self._flat_data[key] = value
        self._data = self._unflatten(self._flat_data)

    def merge(self, other: dict[str, Any]) -> None:
        """合并另一个字典到当前配置。"""
        def deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
            result = base.copy()
            for key, value in update.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result

        self._data = deep_merge(self._data, other)
        self._flat_data = self._flatten(self._data)
