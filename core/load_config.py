import argparse
from dataclasses import asdict, fields, is_dataclass
from typing import TypeVar, Union, get_args, get_origin, get_type_hints

import yaml

from config.classconfig.herald import HeraldConfig
from config.classconfig.llm import LLMConfig
from core.pes.config import PESConfig

T = TypeVar("T")


class ConfigManager:
    def __init__(self) -> None:
        # 初始默认配置
        self.config: HeraldConfig = HeraldConfig()

    def _resolve_actual_type(self, cls: type[object], field_name: str) -> object:
        """解决 PEP 563 导致的字符串类型注释问题。"""
        hints = get_type_hints(cls)
        actual_type = hints.get(field_name)

        # 处理 Union[T, None] (Optional) 和 T | None (types.UnionType)
        try:
            import types

            union_type = types.UnionType
        except ImportError:
            union_type = None

        origin = get_origin(actual_type)
        if origin is Union or (union_type and origin is union_type):
            args = get_args(actual_type)
            # 取非 None 的第一个有效类型
            for arg in args:
                if arg is not type(None):
                    return arg
        return actual_type

    def _get_all_fields(
        self,
        cls: type[object],
        prefix: str = "",
    ) -> dict[str, object]:
        """递归遍历 Dataclass，获取所有叶子节点的配置项。"""
        items: dict[str, object] = {}
        for field in fields(cls):
            name = f"{prefix}{field.name}"
            actual_type = self._resolve_actual_type(cls, field.name)

            if is_dataclass(actual_type):
                items.update(self._get_all_fields(actual_type, prefix=f"{name}."))
            else:
                items[name] = actual_type
        return items

    def _set_nested_value(
        self,
        data: dict[str, object],
        path: str,
        value: object,
    ) -> None:
        """将 'llm.model' 这种路径转换为嵌套字典结构。"""
        keys = path.split(".")
        for key in keys[:-1]:
            nested = data.setdefault(key, {})
            if not isinstance(nested, dict):
                nested = {}
                data[key] = nested
            data = nested
        data[keys[-1]] = value

    def _deep_update(
        self,
        base: dict[str, object],
        updater: dict[str, object],
    ) -> None:
        """递归合并字典。"""
        for k, v in updater.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v

    def _smart_cast(self, type_hint: object) -> object:
        """处理 argparse 的类型转换逻辑。"""
        origin = get_origin(type_hint)
        if origin in (list, tuple):
            return str
        if type_hint is bool:
            return lambda x: str(x).lower() in ["true", "1", "yes", "on"]
        return type_hint

    def parse(self) -> HeraldConfig:
        # 1. 基础字典 (由默认配置生成)
        final_dict = asdict(self.config)

        # 2. YAML 解析 (第二优先级)
        temp_parser = argparse.ArgumentParser(add_help=False)
        temp_parser.add_argument("--config", type=str, default=None)
        temp_args, _ = temp_parser.parse_known_args()

        if temp_args.config:
            with open(temp_args.config, encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f)
                if yaml_data:
                    self._deep_update(final_dict, yaml_data)

        # 3. CLI 动态解析 (第一优先级)
        all_cli_fields = self._get_all_fields(HeraldConfig)
        cli_parser = argparse.ArgumentParser(description="Herald Configuration System")
        cli_parser.add_argument("--config", type=str, help="Path to YAML config file")

        for field_name, field_type in all_cli_fields.items():
            # 将 llm.model 转为 llm_model 作为 CLI 参数名
            cli_arg_name = field_name.replace(".", "_")
            origin = get_origin(field_type)
            if origin in (list, tuple):
                cli_parser.add_argument(
                    f"--{cli_arg_name}",
                    nargs="*",
                    type=self._smart_cast(field_type),
                )
            else:
                cli_parser.add_argument(
                    f"--{cli_arg_name}",
                    type=self._smart_cast(field_type),
                )

        cli_args = cli_parser.parse_args()

        # 将 CLI 的有效输入覆盖到字典中
        for field_name in all_cli_fields:
            val = getattr(cli_args, field_name.replace(".", "_"), None)
            if val is not None:
                self._set_nested_value(final_dict, field_name, val)

        # 4. 转换回 Dataclass (解决 slots=True 问题)
        self.config = self._dict_to_dataclass(HeraldConfig, final_dict)
        return self.config

    def _dict_to_dataclass(self, cls: type[T], data: dict[str, object]) -> T:
        """
        稳健地将字典转换为 Dataclass。
        对于 slots=True 的类，它通过 fields 过滤无效键。
        """
        if not is_dataclass(cls):
            return data

        init_args = {}

        for field in fields(cls):
            if field.name in data:
                field_val = data[field.name]
                actual_type = self._resolve_actual_type(cls, field.name)

                if is_dataclass(actual_type) and isinstance(field_val, dict):
                    init_args[field.name] = self._dict_to_dataclass(
                        actual_type, field_val
                    )
                else:
                    init_args[field.name] = field_val

        return cls(**init_args)

    @property
    def llm(self) -> LLMConfig:
        return self.config.llm

    @property
    def pes(self) -> PESConfig:
        return self.config.pes


# 暴露单例或辅助函数
# manager = ConfigManager()

# def load_all_configs():
#     config = manager.parse()
#     return config, config.llm, config.pes
