"""DraftPES 最小可运行实现。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from core.pes.base import BasePES
from core.pes.gene_utils import parse_genes_from_code
from core.pes.submission import validate_submission_against_sample
from core.pes.types import PESSolution
from core.utils.text import extract_summary_excerpt
from core.utils.utils import utc_now_iso

logger = logging.getLogger(__name__)

class DraftPES(BasePES):
    """DraftPES 的最小可运行版本。"""

    def build_phase_model_options(
        self,
        phase: str,
        solution: PESSolution,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        """为所有 phase 提供工作目录与环境变量。"""

        del phase, solution, parent_solution
        if self.workspace is None:
            return {}

        working_dir = getattr(self.workspace, "working_dir", None)
        db_path = getattr(self.workspace, "db_path", None)
        if working_dir is None or db_path is None:
            return {}

        return {
            "cwd": str(working_dir),
            "env": {
                "HERALD_DB_PATH": str(db_path),
            },
        }

    async def handle_phase_response(
        self,
        phase: str,
        solution: PESSolution,
        response: object,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        """以最小方式消费 phase 响应，保证 DraftPES.run() 可完成。"""

        del parent_solution
        response_text = self._extract_response_text(response)

        # Phase 1: 写入各阶段最小摘要
        if phase == "plan":
            solution.plan_summary = response_text
        elif phase == "execute":
            return self._handle_execute_response(
                solution=solution,
                response=response,
                response_text=response_text,
            )
        elif phase == "summarize":
            solution.summarize_insight = response_text
            solution.status = "completed"
            solution.finished_at = utc_now_iso()
            self._archive_completed_solution(solution)
            self._write_genes(solution)  # 新增
            self._write_l2_knowledge(solution)
            self._emit_task_complete_event(solution=solution, status="completed")
        else:
            raise ValueError(f"不支持的 DraftPES phase: {phase}")

        return {
            "phase": phase,
            "response_text": response_text,
        }

    def _handle_execute_response(
        self,
        solution: PESSolution,
        response: object,
        response_text: str,
    ) -> dict[str, Any]:
        """处理 execute 阶段的 tool-write 契约与运行产物验证。"""

        del response  # 不再从 tool calls 解析命令，改用产物验证

        self._attach_workspace_artifacts(solution)
        self._assert_tool_write_contract(solution)
        code = self._load_written_solution_code(solution)
        self._validate_python_code(solution=solution, code=code)
        self._persist_code_snapshot(solution=solution, code=code)
        exec_result = self._build_exec_result_from_artifacts(solution)
        self._persist_exec_log(solution=solution, exec_result=exec_result)

        try:
            metrics = self._extract_val_metrics(
                solution=solution, exec_result=exec_result
            )
        except ValueError:
            solution.metadata["_l2_failure_context"] = {
                "reason": "missing_metric",
                "stdout_tail": (
                    self._coerce_optional_text(exec_result.get("stdout")) or ""
                )[-500:],
            }
            raise
        self._apply_val_metrics(solution=solution, metrics=metrics)
        try:
            validation = self._validate_submission_artifact(solution)
        except ValueError:
            solution.metadata["_l2_failure_context"] = {
                "reason": "submission_invalid",
                "errors": list(
                    solution.metadata.get("submission_validation_errors", [])
                ),
            }
            raise
        self._apply_submission_validation(solution=solution, result=validation)
        solution.execute_summary = self._format_execute_summary(
            exec_result=exec_result,
            metrics=solution.metrics,
        )

        return {
            "phase": "execute",
            "response_text": response_text,
            "code": code,
            "solution_file_path": solution.solution_file_path,
            "exec_result": exec_result,
            "metrics": solution.metrics,
        }

    def _build_exec_result_from_artifacts(
        self,
        solution: PESSolution,
    ) -> dict[str, Any]:
        """从运行时产物构建执行结果。

        判断逻辑：submission.csv 存在 → agent 成功执行了 solution.py。
        stdout/metrics 从 run.log / metrics.json 读取。
        """

        submission_path = solution.submission_file_path
        if not submission_path or not Path(submission_path).exists():
            raise ValueError(
                "workspace 中未找到 submission.csv，"
                "agent 可能未成功执行 solution.py"
            )

        stdout: str | None = None
        stderr: str | None = None

        if self.workspace is not None and hasattr(
            self.workspace, "read_runtime_artifact"
        ):
            read_artifact = self.workspace.read_runtime_artifact
            if callable(read_artifact):
                for artifact_name in ("stdout.log", "run.log"):
                    content = read_artifact(artifact_name)
                    if content not in (None, ""):
                        stdout = content
                        break
                stderr = read_artifact("stderr.log") or None

        metrics = self._load_metrics_artifact()

        result: dict[str, Any] = {
            "command": "artifact-based-validation",
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": 0,
            "duration_ms": None,
        }
        if metrics is not None:
            result["metrics"] = metrics
        return result

    def _first_non_none(self, *values: object) -> object | None:
        """返回第一个非 None 值。"""

        for value in values:
            if value is not None:
                return value
        return None

    def _coerce_int(self, value: object) -> int | None:
        """将值转换为整数。"""

        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                return None
        return None

    def _coerce_float(self, value: object) -> float | None:
        """将值转换为浮点数。"""

        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return None
        return None

    def _coerce_optional_text(self, value: object) -> str | None:
        """将值转换为可选文本。"""

        if value is None:
            return None
        text = str(value)
        return text

    def _load_metrics_artifact(self) -> dict[str, Any] | None:
        """读取 execute 阶段产出的 metrics.json。"""

        if self.workspace is None or not hasattr(
            self.workspace, "read_runtime_artifact"
        ):
            return None

        read_artifact = self.workspace.read_runtime_artifact
        if not callable(read_artifact):
            return None

        metrics_raw = read_artifact("metrics.json")
        if metrics_raw in (None, ""):
            return None

        try:
            metrics = json.loads(metrics_raw)
        except json.JSONDecodeError:
            return None

        if not isinstance(metrics, dict):
            return None
        return metrics

    def _persist_exec_log(
        self,
        solution: PESSolution,
        exec_result: dict[str, Any],
    ) -> None:
        """将首次运行事实写入 exec_logs。"""

        if self.db is None or not hasattr(self.db, "log_exec"):
            return

        self.db.log_exec(
            solution_id=solution.id,
            command=str(exec_result["command"]),
            stdout=self._coerce_optional_text(exec_result.get("stdout")),
            stderr=self._coerce_optional_text(exec_result.get("stderr")),
            exit_code=self._coerce_int(exec_result.get("exit_code")),
            duration_ms=self._coerce_float(exec_result.get("duration_ms")),
            metrics=(
                exec_result.get("metrics")
                if isinstance(exec_result.get("metrics"), dict)
                else None
            ),
        )

    def _extract_val_metrics(
        self,
        solution: PESSolution,
        exec_result: dict[str, Any],
    ) -> dict[str, Any]:
        """从真实运行事实中提取本地验证指标。"""

        del solution
        structured_payload = exec_result.get("metrics")
        if isinstance(structured_payload, dict):
            metrics = self._extract_val_metrics_from_structured_payload(
                structured_payload
            )
            if metrics is not None:
                return self._complete_val_metrics_from_task_spec(metrics)

        stdout = self._coerce_optional_text(exec_result.get("stdout"))
        if stdout:
            metrics = self._extract_val_metrics_from_stdout(stdout)
            if metrics is not None:
                return self._complete_val_metrics_from_task_spec(metrics)

        raise ValueError("首次运行成功，但未提取到 val_metric_value")

    def _extract_val_metrics_from_structured_payload(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """从结构化 payload 中抽取指标。"""

        metric_value = self._coerce_float(
            self._first_non_none(
                payload.get("val_metric_value"),
                payload.get("metric_value"),
            )
        )
        if metric_value is None:
            return None

        metric_name_raw = self._first_non_none(
            payload.get("val_metric_name"),
            payload.get("metric_name"),
        )
        metric_direction_raw = self._first_non_none(
            payload.get("val_metric_direction"),
            payload.get("metric_direction"),
        )
        return {
            "val_metric_name": (
                str(metric_name_raw).strip()
                if metric_name_raw not in (None, "")
                else None
            ),
            "val_metric_value": metric_value,
            "val_metric_direction": self._normalize_metric_direction(
                metric_direction_raw
            ),
        }

    def _extract_val_metrics_from_stdout(self, stdout: str) -> dict[str, Any] | None:
        """从 stdout 中抽取指标。

        支持三种格式：
        1. 单行 JSON: {"metric_value": 0.99, ...}
        2. 多行 JSON: { \\n  "metric_value": 0.99, \\n ... }
        3. 正则 fallback: metric_value: 0.99 或 "metric_value": 0.99
        """

        # Phase 1: 单行 JSON
        for line in stdout.splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                metrics = self._extract_val_metrics_from_structured_payload(payload)
                if metrics is not None:
                    return metrics

        # Phase 2: 多行 JSON（收集 { ... } 块）
        brace_depth = 0
        json_lines: list[str] = []
        for line in stdout.splitlines():
            stripped = line.strip()
            if brace_depth == 0 and stripped.startswith("{"):
                brace_depth = stripped.count("{") - stripped.count("}")
                json_lines = [stripped]
                if brace_depth <= 0:
                    # 单行闭合，已在 Phase 1 处理过
                    brace_depth = 0
                    json_lines = []
            elif brace_depth > 0:
                json_lines.append(stripped)
                brace_depth += stripped.count("{") - stripped.count("}")
                if brace_depth <= 0:
                    blob = " ".join(json_lines)
                    brace_depth = 0
                    json_lines = []
                    try:
                        payload = json.loads(blob)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict):
                        metrics = self._extract_val_metrics_from_structured_payload(
                            payload
                        )
                        if metrics is not None:
                            return metrics

        # Phase 3: 正则 fallback（兼容 JSON 引号格式和朴素 key=value 格式）
        patterns = {
            "val_metric_name": [
                r'"?val_metric_name"?\s*[:=]\s*"?([A-Za-z0-9_./-]+)"?',
                r'"?metric_name"?\s*[:=]\s*"?([A-Za-z0-9_./-]+)"?',
            ],
            "val_metric_value": [
                r'"?val_metric_value"?\s*[:=]\s*([-+]?\d+(?:\.\d+)?)',
                r'"?metric_value"?\s*[:=]\s*([-+]?\d+(?:\.\d+)?)',
            ],
            "val_metric_direction": [
                r'"?val_metric_direction"?\s*[:=]\s*"?(maximize|max|minimize|min)"?',
                r'"?metric_direction"?\s*[:=]\s*"?(maximize|max|minimize|min)"?',
            ],
        }

        extracted: dict[str, Any] = {}
        for key, key_patterns in patterns.items():
            for pattern in key_patterns:
                match = re.search(pattern, stdout, flags=re.IGNORECASE)
                if match is None:
                    continue
                extracted[key] = match.group(1)
                break

        metric_value = self._coerce_float(extracted.get("val_metric_value"))
        if metric_value is None:
            return None

        return {
            "val_metric_name": extracted.get("val_metric_name"),
            "val_metric_value": metric_value,
            "val_metric_direction": self._normalize_metric_direction(
                extracted.get("val_metric_direction")
            ),
        }

    def _complete_val_metrics_from_task_spec(
        self,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        """使用 task_spec 补齐指标名和方向。"""

        task_spec = self._execution_context.get(
            "task_spec",
            self.runtime_context.get("task_spec"),
        )
        metric_name: str | None = None
        metric_direction: str | None = None
        if isinstance(task_spec, dict):
            raw_metric_name = task_spec.get("metric_name")
            raw_metric_direction = task_spec.get("metric_direction")
            if raw_metric_name not in (None, ""):
                metric_name = str(raw_metric_name).strip()
            metric_direction = self._normalize_metric_direction(raw_metric_direction)

        completed_metrics = dict(metrics)
        if completed_metrics.get("val_metric_name") in (None, ""):
            completed_metrics["val_metric_name"] = metric_name
        if completed_metrics.get("val_metric_direction") in (None, ""):
            completed_metrics["val_metric_direction"] = metric_direction
        return completed_metrics

    def _normalize_metric_direction(self, direction: object) -> str | None:
        """将指标方向归一化为 max/min。"""

        if direction in (None, ""):
            return None

        normalized = str(direction).strip().lower()
        if normalized.startswith("max"):
            return "max"
        if normalized.startswith("min"):
            return "min"
        return normalized or None

    def _apply_val_metrics(
        self,
        solution: PESSolution,
        metrics: dict[str, Any],
    ) -> None:
        """将 val_metric_* 写回 solution。"""

        metric_name = metrics.get("val_metric_name")
        metric_value = self._coerce_float(metrics.get("val_metric_value"))
        metric_direction = self._normalize_metric_direction(
            metrics.get("val_metric_direction")
        )
        if metric_value is None:
            raise ValueError("val_metric_value 为空，无法回写 fitness")

        solution.metrics = {
            "val_metric_name": metric_name,
            "val_metric_value": metric_value,
            "val_metric_direction": metric_direction,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "metric_direction": metric_direction,
        }
        solution.fitness = metric_value

    def _format_execute_summary(
        self,
        exec_result: dict[str, Any],
        metrics: dict[str, Any] | None = None,
    ) -> str:
        """生成简洁的人类可读执行摘要。"""

        exit_code = self._coerce_int(exec_result.get("exit_code"))
        duration_ms = self._coerce_float(exec_result.get("duration_ms"))
        duration_text = (
            "unknown"
            if duration_ms is None
            else str(int(duration_ms))
            if duration_ms.is_integer()
            else f"{duration_ms:.1f}"
        )
        summary = (
            f"已记录首次运行事实：{exec_result['command']} "
            f"(exit_code={exit_code}, duration_ms={duration_text})"
        )
        if metrics is None:
            return summary

        metric_value = self._coerce_float(
            self._first_non_none(
                metrics.get("val_metric_value"),
                metrics.get("metric_value"),
            )
        )
        if metric_value is None:
            return summary

        metric_name = self._first_non_none(
            metrics.get("val_metric_name"),
            metrics.get("metric_name"),
        )
        metric_direction = self._first_non_none(
            metrics.get("val_metric_direction"),
            metrics.get("metric_direction"),
        )
        metric_name_text = (
            str(metric_name).strip() if metric_name not in (None, "") else "unknown"
        )
        metric_direction_text = (
            str(metric_direction).strip()
            if metric_direction not in (None, "")
            else "unknown"
        )
        return (
            f"{summary} "
            f"(val_metric_name={metric_name_text}, "
            f"val_metric_value={metric_value}, "
            f"val_metric_direction={metric_direction_text})"
        )

    def _extract_response_text(self, response: object) -> str:
        """提取模型响应文本。"""

        result = getattr(response, "result", "")
        if result is None:
            return ""
        return str(result).strip()

    def _assert_tool_write_contract(self, solution: PESSolution) -> Path:
        """确认工具已将 solution.py 写入工作区。"""

        if self.workspace is None:
            raise ValueError("DraftPES 缺少 workspace，无法校验 tool-write 契约")

        get_path = getattr(self.workspace, "get_working_file_path", None)
        if callable(get_path):
            solution_path = get_path(self.config.solution_file_name)
        else:
            working_dir = getattr(self.workspace, "working_dir", None)
            if working_dir is None:
                raise ValueError("workspace 未提供 working_dir，无法校验 solution.py")
            solution_path = Path(working_dir) / self.config.solution_file_name

        if not solution_path.exists():
            detail = f"execute 阶段未写出代码文件: {solution_path}"
            self._log_contract_check(
                solution.id, "tool_write_solution_file", False, detail
            )
            raise ValueError(detail)

        self._log_contract_check(
            solution.id,
            "tool_write_solution_file",
            True,
            f"代码文件已生成: {solution_path}",
        )
        return solution_path

    def _load_written_solution_code(self, solution: PESSolution) -> str:
        """读取工作区中已写出的 solution.py。"""

        if self.workspace is None:
            raise ValueError("DraftPES 缺少 workspace，无法读取 solution.py")

        reader = getattr(self.workspace, "read_working_solution", None)
        if callable(reader):
            try:
                code = reader(self.config.solution_file_name)
            except ValueError as error:
                self._log_contract_check(
                    solution.id,
                    "tool_write_solution_content",
                    False,
                    str(error),
                )
                raise
            self._log_contract_check(
                solution.id,
                "tool_write_solution_content",
                True,
                "solution.py 内容非空且可读取",
            )
            return code

        working_dir = getattr(self.workspace, "working_dir", None)
        if working_dir is None:
            raise ValueError("workspace 未提供 working_dir，无法读取 solution.py")

        solution_path = Path(working_dir) / self.config.solution_file_name
        try:
            code = solution_path.read_text(encoding="utf-8")
        except OSError as error:
            detail = f"读取代码文件失败: {solution_path}"
            self._log_contract_check(
                solution.id,
                "tool_write_solution_content",
                False,
                detail,
            )
            raise ValueError(detail) from error

        if not code.strip():
            detail = f"代码文件为空: {solution_path}"
            self._log_contract_check(
                solution.id,
                "tool_write_solution_content",
                False,
                detail,
            )
            raise ValueError(detail)
        self._log_contract_check(
            solution.id,
            "tool_write_solution_content",
            True,
            "solution.py 内容非空且可读取",
        )
        return code

    def _validate_python_code(
        self,
        solution: PESSolution,
        code: str,
    ) -> None:
        """对生成代码做最小 Python 语法检查。"""

        try:
            compile(code, "<solution.py>", "exec")
        except SyntaxError as error:
            detail = f"solution.py 语法错误: line {error.lineno}, {error.msg}"
            self._log_contract_check(solution.id, "python_syntax", False, detail)
            raise ValueError(detail) from error

        self._log_contract_check(
            solution.id,
            "python_syntax",
            True,
            "solution.py 通过语法校验",
        )

    def _persist_code_snapshot(
        self,
        solution: PESSolution,
        code: str,
    ) -> None:
        """持久化完整代码快照。"""

        if self.db is None or not hasattr(self.db, "insert_code_snapshot"):
            return
        self.db.insert_code_snapshot(solution.id, code)

    def _attach_workspace_artifacts(self, solution: PESSolution) -> None:
        """在有工作空间时挂载最小工件路径。"""

        if self.workspace is None:
            return

        working_dir = getattr(self.workspace, "working_dir", None)
        if working_dir is None:
            return

        working_dir_path = Path(working_dir)
        working_dir_path.mkdir(parents=True, exist_ok=True)
        solution.workspace_dir = str(working_dir_path)

        solution_path = working_dir_path / self.config.solution_file_name
        solution.solution_file_path = str(solution_path)

        if self.config.submission_file_name:
            get_submission_path = getattr(
                self.workspace, "get_working_submission_path", None
            )
            if callable(get_submission_path):
                submission_path = get_submission_path(self.config.submission_file_name)
            else:
                submission_path = working_dir_path / self.config.submission_file_name
            solution.submission_file_path = str(submission_path)
        self._persist_solution_artifacts(solution)

    def _validate_submission_artifact(
        self,
        solution: PESSolution,
    ) -> dict[str, Any]:
        """校验 execute 阶段产出的 submission.csv。"""

        submission_path = solution.submission_file_path
        if submission_path in (None, ""):
            raise ValueError("submission_file_path 为空，无法校验 submission.csv")

        sample_submission_path = self._resolve_sample_submission_path()
        validation = validate_submission_against_sample(
            submission_path=submission_path,
            sample_submission_path=sample_submission_path,
        )
        if not validation.is_valid:
            errors_text = "; ".join(validation.errors)
            solution.metadata["submission_validated"] = False
            solution.metadata["submission_validation_errors"] = list(validation.errors)
            solution.metadata["sample_submission_path"] = str(sample_submission_path)
            raise ValueError(f"submission.csv 校验失败: {errors_text}")

        return {
            "is_valid": validation.is_valid,
            "errors": validation.errors,
            "submission_schema_columns": validation.submission_schema.columns,
            "submission_row_count": validation.submission_schema.row_count,
            "sample_schema_columns": validation.sample_schema.columns,
            "sample_row_count": validation.sample_schema.row_count,
            "sample_submission_path": str(sample_submission_path),
        }

    def _resolve_sample_submission_path(self) -> Path:
        """定位真实 sample_submission.csv。"""

        competition_dir = self._execution_context.get(
            "competition_dir",
            self.runtime_context.get("competition_dir"),
        )
        if competition_dir in (None, ""):
            raise ValueError("缺少 competition_dir，无法定位 sample_submission.csv")

        competition_root = Path(str(competition_dir)).expanduser().resolve()
        candidate_paths = [
            competition_root / "prepared" / "public" / "sample_submission.csv",
            competition_root / "sample_submission.csv",
        ]
        workspace_data_dir = getattr(self.workspace, "data_dir", None)
        if isinstance(workspace_data_dir, (str, Path)):
            candidate_paths.append(
                Path(workspace_data_dir).expanduser().resolve()
                / "sample_submission.csv"
            )
        for candidate_path in candidate_paths:
            if candidate_path.exists():
                return candidate_path

        raise ValueError(
            "未找到 sample_submission.csv: "
            + ", ".join(str(path) for path in candidate_paths)
        )

    def _apply_submission_validation(
        self,
        solution: PESSolution,
        result: dict[str, Any],
    ) -> None:
        """将 submission 校验结果写入 solution.metadata。"""

        solution.metadata["submission_validated"] = bool(result.get("is_valid"))
        solution.metadata["submission_validation_errors"] = list(
            result.get("errors", [])
        )
        solution.metadata["submission_schema_columns"] = list(
            result.get("submission_schema_columns", [])
        )
        solution.metadata["submission_row_count"] = result.get("submission_row_count")
        solution.metadata["sample_submission_path"] = result.get(
            "sample_submission_path"
        )

    def _archive_completed_solution(self, solution: PESSolution) -> None:
        """在成功完成后归档版本，并在更优时提升 best。"""

        version_dir = self._archive_successful_solution(solution)
        if version_dir is None:
            return

        promoted = self._maybe_promote_best(solution=solution, version_dir=version_dir)
        solution.metadata["best_promoted"] = promoted

    def _write_genes(self, solution: PESSolution) -> None:
        """从 code_snapshots 解析 GENE 标记并写入 genes 表。

        Args:
            solution: 当前 PESSolution 对象
        """

        if self.db is None or not hasattr(self.db, "insert_genes"):
            return

        code = self.db.get_full_code(solution.id)
        if code is None:
            logger.warning(
                "genes 写入跳过：无 code_snapshot [solution_id=%s]", solution.id
            )
            return

        genes = parse_genes_from_code(code)
        if not genes:
            logger.info(
                "genes 写入跳过：代码无 GENE 标记 [solution_id=%s]", solution.id
            )
            return

        shared_desc = (solution.summarize_insight or "")[:500]
        gene_records = [
            {
                "slot": slot_name,
                "description": shared_desc or None,
                "code_anchor": slot_code[:200],
            }
            for slot_name, slot_code in genes.items()
        ]
        self.db.insert_genes(solution.id, gene_records)
        logger.info(
            "genes 已写入: solution_id=%s, slots=%s",
            solution.id,
            sorted(genes.keys()),
        )

    def _archive_successful_solution(self, solution: PESSolution) -> Path | None:
        """将当前 working 工件保存到 history/。"""

        if self.workspace is None:
            return None

        save_version = getattr(self.workspace, "save_version", None)
        read_solution = getattr(self.workspace, "read_working_solution", None)
        read_submission = getattr(self.workspace, "read_working_submission", None)
        if (
            not callable(save_version)
            or not callable(read_solution)
            or not callable(read_submission)
        ):
            return None

        code = read_solution(self.config.solution_file_name)
        submission = read_submission(self.config.submission_file_name)
        version_dir = save_version(
            code=code,
            submission=submission,
            generation=solution.generation,
            solution_id=solution.id,
        )
        solution.metadata["version_dir"] = str(version_dir)
        return Path(version_dir)

    def _maybe_promote_best(
        self,
        solution: PESSolution,
        version_dir: Path,
    ) -> bool:
        """仅在当前解更优时更新 best/。"""

        if solution.status != "completed":
            return False
        if solution.fitness is None:
            return False
        if solution.metadata.get("submission_validated") is not True:
            return False
        if self.workspace is None:
            return False

        promote_best = getattr(self.workspace, "promote_best", None)
        if not callable(promote_best):
            return False

        best_fitness = self._get_current_best_fitness(solution)
        if best_fitness is not None and solution.fitness <= best_fitness:
            return False

        metadata = self._build_best_metadata(solution=solution, version_dir=version_dir)
        promote_best(version_dir=version_dir, metadata=metadata)
        return True

    def _get_current_best_fitness(self, solution: PESSolution) -> float | None:
        """读取当前 run 中除自身外的最高 fitness。"""

        if self.db is None or not hasattr(self.db, "get_best_fitness"):
            return None

        return self.db.get_best_fitness(
            run_id=solution.run_id,
            exclude_solution_id=solution.id,
        )

    def _build_best_metadata(
        self,
        solution: PESSolution,
        version_dir: Path,
    ) -> dict[str, Any]:
        """构造 best/metadata.json。"""

        return {
            "solution_id": solution.id,
            "generation": solution.generation,
            "fitness": solution.fitness,
            "run_id": solution.run_id,
            "version_dir": str(version_dir),
            "promoted_at": utc_now_iso(),
        }

    # ── L2 知识写入 ──────────────────────────────────────────────

    def _get_task_type(self) -> str:
        """从 execution_context / runtime_context 的 task_spec 中提取 task_type。"""

        task_spec = self._execution_context.get(
            "task_spec",
            self.runtime_context.get("task_spec"),
        )
        if isinstance(task_spec, dict):
            task_type = task_spec.get("task_type")
            if task_type not in (None, ""):
                return str(task_type).strip()
        return "unknown"

    def _write_l2_knowledge(self, solution: PESSolution) -> None:
        """将方案级经验写入 L2 知识层。

        成功路径：从 summarize_insight 提取摘要作为 pattern，evidence_type="support"。
        失败路径：从 metadata["_l2_failure_context"] 组装 insight，evidence_type="contradict"。
        写入失败仅 warn，不阻塞主链路。
        """

        if self.db is None or not hasattr(self.db, "upsert_l2_insight"):
            return

        try:
            task_type = self._get_task_type()
            failure_ctx = solution.metadata.get("_l2_failure_context")

            if failure_ctx is not None:
                # 失败路径
                evidence_type = "contradict"
                insight = self._build_failure_insight(solution, failure_ctx)
                pattern = insight[:300]
            else:
                # 成功路径
                evidence_type = "support"
                insight = solution.summarize_insight or ""
                pattern = extract_summary_excerpt(insight, max_len=300)

            if not pattern.strip():
                logger.warning(
                    "L2 写入跳过：pattern 为空 [solution_id=%s]", solution.id
                )
                return

            self.db.upsert_l2_insight(
                slot="strategy",
                task_type=task_type,
                pattern=pattern,
                insight=insight,
                solution_id=solution.id,
                evidence_type=evidence_type,
            )
        except Exception:
            logger.warning(
                "L2 知识写入失败，不阻塞主链路 [solution_id=%s]",
                solution.id,
                exc_info=True,
            )

    def _build_failure_insight(
        self,
        solution: PESSolution,
        failure_ctx: dict[str, Any],
    ) -> str:
        """从失败上下文组装 L2 insight 文本。"""

        reason = failure_ctx.get("reason", "unknown")
        parts = [f"[FAILED:{reason}] {solution.execute_summary}"]

        stderr_tail = failure_ctx.get("stderr_tail")
        if stderr_tail:
            parts.append(f"stderr: {stderr_tail}")

        stdout_tail = failure_ctx.get("stdout_tail")
        if stdout_tail:
            parts.append(f"stdout_tail: {stdout_tail}")

        errors = failure_ctx.get("errors")
        if errors:
            parts.append(f"errors: {'; '.join(str(e) for e in errors)}")

        return "\n".join(parts)

    def handle_phase_failure(
        self,
        phase: str,
        solution: PESSolution,
        error: Exception,
    ) -> None:
        """Override：在基类失败处理后，对有价值的失败写入 L2 contradict。"""

        super().handle_phase_failure(phase=phase, solution=solution, error=error)

        if solution.metadata.get("_l2_failure_context") is not None:
            self._write_l2_knowledge(solution)
