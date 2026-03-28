"""FeatureExtractPES 前置数据分析实现。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from core.events.bus import EventBus
from core.events.types import TaskCompleteEvent
from core.pes.base import BasePES
from core.pes.schema import load_genome_template
from core.pes.types import PESSolution
from core.utils.utils import utc_now_iso

logger = logging.getLogger(__name__)

# execute 阶段 LLM 输出中 JSON code block 的正则
_JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)

# 合法的 genome 模板类型
VALID_GENOME_TEMPLATES = ("tabular", "generic")


class FeatureExtractPES(BasePES):
    """前置数据分析 PES，每竞赛运行一次。

    职责：分析竞赛数据 → 生成 TaskSpec + data_profile → 选择 GenomeSchema 模板。
    """

    def build_phase_model_options(
        self,
        phase: str,
        solution: PESSolution,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        """execute phase 设置 cwd 为 workspace.working_dir。"""

        del solution, parent_solution
        if phase != "execute" or self.workspace is None:
            return {}

        working_dir = getattr(self.workspace, "working_dir", None)
        if working_dir is None:
            return {}

        return {"cwd": str(working_dir)}

    async def handle_phase_response(
        self,
        phase: str,
        solution: PESSolution,
        response: object,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        """消费各阶段响应并更新 solution。

        Args:
            phase: 当前阶段名
            solution: 当前方案状态
            response: LLM 响应对象
            parent_solution: 父方案（当前阶段无用）

        Returns:
            解析结果字典
        """

        del parent_solution
        response_text = self._extract_response_text(response)

        if phase == "plan":
            solution.plan_summary = response_text
            return {"phase": phase, "response_text": response_text}

        if phase == "execute":
            return self._handle_execute_response(solution, response_text)

        if phase == "summarize":
            return self._handle_summarize_response(solution, response_text)

        raise ValueError(f"不支持的 FeatureExtractPES phase: {phase}")

    def _handle_execute_response(
        self,
        solution: PESSolution,
        response_text: str,
    ) -> dict[str, Any]:
        """处理 execute 阶段响应：解析 JSON → 持久化。"""

        solution.execute_summary = response_text

        # Phase 1: 解析结构化输出
        parsed = self._parse_structured_output(response_text)
        task_spec_dict = parsed.get("task_spec", {})
        data_profile = parsed.get("data_profile", "")
        genome_template = parsed.get("genome_template", "generic")

        # Phase 2: 校验 genome_template
        if genome_template not in VALID_GENOME_TEMPLATES:
            logger.warning(
                "无效的 genome_template '%s'，降级为 'generic'", genome_template
            )
            genome_template = "generic"
        schema, template_content = load_genome_template(genome_template)

        # Phase 3: 持久化到 workspace
        self._persist_task_spec(task_spec_dict)
        self._persist_data_profile(data_profile)

        # Phase 4: 更新 solution metadata
        solution.metadata["task_spec"] = task_spec_dict
        solution.metadata["data_profile"] = data_profile
        solution.metadata["genome_template"] = genome_template
        solution.metadata["schema"] = schema
        solution.metadata["template_content"] = template_content
        solution.metadata["schema_task_type"] = task_spec_dict.get("task_type", "")

        # Phase 5: 挂载工件路径
        self._attach_workspace_artifacts(solution)

        return {
            "phase": "execute",
            "task_spec": task_spec_dict,
            "data_profile": data_profile,
            "genome_template": genome_template,
            "schema": schema,
            "template_content": template_content,
        }

    def _handle_summarize_response(
        self,
        solution: PESSolution,
        response_text: str,
    ) -> dict[str, Any]:
        """处理 summarize 阶段响应：写入洞察 → 标记完成 → 发事件。"""

        solution.summarize_insight = response_text
        solution.status = "completed"
        solution.finished_at = utc_now_iso()

        EventBus.get().emit(
            TaskCompleteEvent(
                task_name=self.config.name,
                pes_instance_id=self.instance_id,
                status="completed",
                solution_id=solution.id,
                output_context=self._build_output_context(solution),
            )
        )

        return {"phase": "summarize", "response_text": response_text}

    def _build_output_context(self, solution: PESSolution) -> dict[str, Any]:
        """构造供下游 DraftPES 消费的阶段产出上下文。"""

        output_context: dict[str, Any] = {}
        for key in (
            "task_spec",
            "data_profile",
            "genome_template",
            "schema",
            "template_content",
        ):
            if key in solution.metadata:
                output_context[key] = solution.metadata[key]
        return output_context

    def _extract_response_text(self, response: object) -> str:
        """提取模型响应文本。"""

        result = getattr(response, "result", "")
        if result is None:
            return ""
        return str(result).strip()

    def _parse_structured_output(self, text: str) -> dict[str, Any]:
        """从 LLM 输出中提取最后一个 JSON code block 并解析。

        Args:
            text: LLM 原始输出文本

        Returns:
            解析后的字典，至少包含 task_spec / data_profile / genome_template

        Raises:
            ValueError: 未找到 JSON code block 或解析失败
        """

        matches = _JSON_BLOCK_RE.findall(text)
        if not matches:
            raise ValueError("LLM 输出中未找到 JSON code block")

        # 取最后一个 JSON block
        json_text = matches[-1].strip()
        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as error:
            raise ValueError(f"JSON 解析失败: {error}") from error

        if not isinstance(parsed, dict):
            raise ValueError(f"JSON 顶层必须是对象，实际类型: {type(parsed).__name__}")

        return parsed

    def _persist_task_spec(self, task_spec_dict: dict[str, Any]) -> None:
        """将 TaskSpec 字典序列化到 workspace/working/task_spec.json。"""

        if self.workspace is None:
            return

        working_dir = getattr(self.workspace, "working_dir", None)
        if working_dir is None:
            return

        working_path = Path(working_dir)
        working_path.mkdir(parents=True, exist_ok=True)
        task_spec_path = working_path / "task_spec.json"
        task_spec_path.write_text(
            json.dumps(task_spec_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("TaskSpec 已写入: %s", task_spec_path)

    def _persist_data_profile(self, data_profile: str) -> None:
        """将数据概况报告写入 workspace/working/data_profile.md。"""

        if self.workspace is None:
            return

        working_dir = getattr(self.workspace, "working_dir", None)
        if working_dir is None:
            return

        working_path = Path(working_dir)
        working_path.mkdir(parents=True, exist_ok=True)
        profile_path = working_path / "data_profile.md"
        profile_path.write_text(data_profile, encoding="utf-8")
        logger.info("data_profile 已写入: %s", profile_path)

    def _attach_workspace_artifacts(self, solution: PESSolution) -> None:
        """挂载工件路径到 solution。"""

        if self.workspace is None:
            return

        working_dir = getattr(self.workspace, "working_dir", None)
        if working_dir is None:
            return

        working_dir_path = Path(working_dir)
        solution.workspace_dir = str(working_dir_path)
        solution.solution_file_path = str(
            working_dir_path / self.config.solution_file_name
        )
