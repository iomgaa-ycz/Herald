"""PromptManager V3 模块。

统一负责基于 `prompt_spec + fragments + templates` 装配首次 Prompt。
运行时 Skills 完全交给 Claude Agent SDK。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

logger = logging.getLogger(__name__)


class PromptManager:
    """首次 Prompt 装配器。"""

    def __init__(
        self,
        template_dir: Path,
        fragments_dir: Path,
        spec_path: Path,
    ) -> None:
        """初始化 PromptManager。

        Args:
            template_dir: Jinja2 模板目录。
            fragments_dir: 静态 Prompt 片段目录。
            spec_path: PromptSpec V3 配置文件路径。
        """

        self.template_dir = Path(template_dir)
        self.fragments_dir = Path(fragments_dir)
        self.spec_path = Path(spec_path)
        self._prompt_spec = self._load_prompt_spec(self.spec_path)
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        logger.info(
            "PromptManager V3 初始化完成（template_dir=%s, fragments_dir=%s）",
            self.template_dir,
            self.fragments_dir,
        )

    def _load_prompt_spec(self, spec_path: Path) -> dict[str, Any]:
        """强制加载 PromptSpec V3 配置。

        Args:
            spec_path: PromptSpec 文件路径。

        Returns:
            解析后的配置字典。

        Raises:
            FileNotFoundError: 配置文件不存在。
            ValueError: YAML 非法或结构不符合预期。
        """

        path = Path(spec_path)
        if not path.exists():
            raise FileNotFoundError(f"prompt_spec.yaml 不存在: {path}")

        try:
            with open(path, encoding="utf-8") as file:
                spec = yaml.safe_load(file)
        except yaml.YAMLError as exc:
            raise ValueError(f"prompt_spec.yaml YAML 解析失败: {path}") from exc

        if not isinstance(spec, dict):
            raise ValueError(f"prompt_spec.yaml 顶层必须是映射: {path}")

        templates = spec.get("templates")
        if not isinstance(templates, dict):
            raise ValueError(f"prompt_spec.yaml 缺少合法 templates 映射: {path}")

        for template_key, template_spec in templates.items():
            if not isinstance(template_spec, dict):
                raise ValueError(f"prompt_spec 模板配置必须是映射: {template_key}")
            if set(template_spec.keys()) != {
                "required_context",
                "static_fragments",
                "artifacts",
            }:
                raise ValueError(f"prompt_spec 模板字段非法: {template_key}")
            for field_name in ("required_context", "static_fragments", "artifacts"):
                self._get_string_list_field(
                    template_spec=template_spec,
                    field_name=field_name,
                )

        return spec

    def get_template_spec(self, operation: str, phase: str) -> dict[str, Any]:
        """读取指定 phase 的 PromptSpec 配置。

        Args:
            operation: 操作类型。
            phase: 阶段名。

        Returns:
            对应 template_key 的配置字典。

        Raises:
            ValueError: template_key 未定义。
        """

        template_key = f"{operation}_{phase}"
        templates = self._prompt_spec["templates"]
        template_spec = templates.get(template_key)
        if not isinstance(template_spec, dict):
            raise ValueError(f"prompt_spec 未定义模板: {template_key}")

        return template_spec

    def load_fragment(self, fragment_name: str) -> str:
        """加载静态 Prompt 片段。

        Args:
            fragment_name: 片段名，不含或包含 `.md` 后缀均可。

        Returns:
            片段内容。

        Raises:
            FileNotFoundError: 片段文件不存在。
        """

        normalized_name = (
            fragment_name[:-3] if fragment_name.endswith(".md") else fragment_name
        )
        fragment_path = self.fragments_dir / f"{normalized_name}.md"
        if not fragment_path.exists():
            raise FileNotFoundError(f"Prompt fragment 不存在: {fragment_path}")

        return fragment_path.read_text(encoding="utf-8").strip()

    def build_static_fragments_text(
        self,
        template_spec: dict[str, Any],
    ) -> str:
        """按 spec 顺序拼接静态片段。"""

        fragment_names = self._get_string_list_field(
            template_spec=template_spec,
            field_name="static_fragments",
        )
        if not fragment_names:
            return ""

        fragments = [
            self.load_fragment(fragment_name) for fragment_name in fragment_names
        ]
        return "\n\n".join(fragments)

    def validate_context(
        self,
        template_key: str,
        template_spec: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        """校验 required_context，缺失即快速失败。"""

        required_fields = self._get_string_list_field(
            template_spec=template_spec,
            field_name="required_context",
        )
        missing_fields = [
            field
            for field in required_fields
            if field not in context or context[field] is None
        ]
        if missing_fields:
            missing_text = ", ".join(missing_fields)
            raise ValueError(
                f"Prompt 上下文缺少必填字段: template={template_key}, missing=[{missing_text}]"
            )

    def build_prompt(
        self,
        operation: str,
        phase: str,
        context: dict[str, Any],
    ) -> str:
        """按 V3 装配流程构建完整 Prompt。"""

        template_key = f"{operation}_{phase}"
        template_spec = self.get_template_spec(operation, phase)
        self.validate_context(template_key, template_spec, context)

        static_fragments_text = self.build_static_fragments_text(template_spec)

        template_name = f"{template_key}.j2"
        try:
            template = self.env.get_template(template_name)
        except TemplateNotFound:
            logger.error("模板文件不存在: %s", template_name)
            raise

        template_context = {
            **context,
            "static_fragments_text": static_fragments_text,
        }
        prompt = template.render(**template_context)
        logger.debug("Prompt 构建完成（template=%s）", template_key)
        return prompt

    def _get_string_list_field(
        self,
        template_spec: dict[str, Any],
        field_name: str,
    ) -> list[str]:
        """读取并校验 PromptSpec 中的字符串列表字段。"""

        raw_value = template_spec.get(field_name, [])
        if not isinstance(raw_value, list):
            raise ValueError(f"prompt_spec 字段必须是列表: {field_name}")
        if not all(isinstance(item, str) and item.strip() for item in raw_value):
            raise ValueError(f"prompt_spec 字段必须是非空字符串列表: {field_name}")

        return raw_value
