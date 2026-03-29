"""DraftPES 最小可运行实现。"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any

from core.pes.base import BasePES
from core.pes.submission import validate_submission_against_sample
from core.pes.types import PESSolution
from core.utils.utils import utc_now_iso


class DraftPES(BasePES):
    """DraftPES 的最小可运行版本。"""

    def build_phase_model_options(
        self,
        phase: str,
        solution: PESSolution,
        parent_solution: PESSolution | None,
    ) -> dict[str, Any]:
        """为 execute phase 提供工作目录与环境变量。"""

        del solution, parent_solution
        if phase != "execute" or self.workspace is None:
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
        """处理 execute 阶段的 tool-write 契约与首次运行事实。"""

        self._attach_workspace_artifacts(solution)
        self._assert_tool_write_contract(solution)
        code = self._load_written_solution_code(solution)
        self._validate_python_code(solution=solution, code=code)
        self._persist_code_snapshot(solution=solution, code=code)
        exec_result = self._extract_execute_fact(response)
        self._assert_execute_fact_matches_final_solution(solution, exec_result)
        exec_result = self._fill_exec_fact_from_runtime_artifacts(exec_result)
        self._persist_exec_log(solution=solution, exec_result=exec_result)

        exit_code = exec_result["exit_code"]
        if exit_code != 0:
            solution.execute_summary = self._format_execute_summary(exec_result)
            raise ValueError(f"solution.py 首次运行失败：{solution.execute_summary}")

        metrics = self._extract_val_metrics(solution=solution, exec_result=exec_result)
        self._apply_val_metrics(solution=solution, metrics=metrics)
        validation = self._validate_submission_artifact(solution)
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

    def _extract_execute_fact(self, response: object) -> dict[str, Any]:
        """从 execute phase 的真实工具轨迹中提取首次运行事实。"""

        turns = getattr(response, "turns", None)
        if not isinstance(turns, list):
            raise ValueError("execute 响应缺少 turns，无法提取首次运行事实")

        fallback_fact: dict[str, Any] | None = None
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            tool_calls = turn.get("tool_calls")
            if not isinstance(tool_calls, list):
                continue

            for tool_call in tool_calls:
                fact = self._parse_exec_fact_from_tool_call(tool_call)
                if fact is None:
                    continue
                if self._command_targets_solution_file(str(fact["command"]), None):
                    return fact
                if fallback_fact is None:
                    fallback_fact = fact

        if fallback_fact is not None:
            return fallback_fact
        raise ValueError("未从 execute turns 中提取到 solution.py 的真实运行事实")

    def _parse_exec_fact_from_tool_call(
        self,
        tool_call: object,
    ) -> dict[str, Any] | None:
        """从单次工具调用中提取执行事实。"""

        if not isinstance(tool_call, dict):
            return None

        tool_input = tool_call.get("input")
        if not isinstance(tool_input, dict):
            return None

        command = self._normalize_command(
            self._first_non_none(
                tool_input.get("command"),
                tool_input.get("cmd"),
                tool_input.get("argv"),
                tool_input.get("args"),
            )
        )
        if command is None:
            return None

        result_payload = self._normalize_tool_result(tool_call.get("result"))
        exit_code = self._coerce_int(
            self._first_non_none(
                result_payload.get("exit_code"),
                tool_call.get("exit_code"),
            )
        )
        duration_ms = self._coerce_float(
            self._first_non_none(
                result_payload.get("duration_ms"),
                result_payload.get("duration"),
                tool_call.get("duration_ms"),
            )
        )
        stdout = self._coerce_optional_text(
            self._first_non_none(
                result_payload.get("stdout"),
                tool_call.get("stdout"),
            )
        )
        stderr = self._coerce_optional_text(
            self._first_non_none(
                result_payload.get("stderr"),
                tool_call.get("stderr"),
            )
        )

        if exit_code is None:
            return None

        return {
            "command": command,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
        }

    def _normalize_tool_result(self, result: object) -> dict[str, Any]:
        """将工具结果归一化为字典结构。"""

        if isinstance(result, dict):
            return result

        if isinstance(result, list):
            merged: dict[str, Any] = {}
            text_fragments: list[str] = []
            for item in result:
                if isinstance(item, dict):
                    merged.update(
                        {
                            key: value
                            for key, value in item.items()
                            if key
                            in {"stdout", "stderr", "exit_code", "duration_ms", "text"}
                        }
                    )
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        text_fragments.append(text.strip())
                elif isinstance(item, str) and item.strip():
                    text_fragments.append(item.strip())
            if text_fragments and "stdout" not in merged:
                merged["stdout"] = "\n".join(text_fragments)
            return merged

        if isinstance(result, str):
            return {"stdout": result}

        return {}

    def _normalize_command(self, command: object) -> str | None:
        """将工具输入中的命令归一化为字符串。"""

        if isinstance(command, str):
            normalized = command.strip()
            return normalized or None
        if isinstance(command, list):
            parts = [str(part).strip() for part in command if str(part).strip()]
            if not parts:
                return None
            return " ".join(parts)
        return None

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

    def _assert_execute_fact_matches_final_solution(
        self,
        solution: PESSolution,
        exec_fact: dict[str, Any],
    ) -> None:
        """确认执行事实对应最终的 working/solution.py。"""

        solution_path = solution.solution_file_path
        if solution_path is None:
            raise ValueError("solution_file_path 为空，无法校验执行事实")

        if not self._command_targets_solution_file(
            command=str(exec_fact["command"]),
            solution_path=Path(solution_path),
        ):
            raise ValueError(f"执行事实未指向最终 solution.py：{exec_fact['command']}")

    def _command_targets_solution_file(
        self,
        command: str,
        solution_path: Path | None,
    ) -> bool:
        """判断命令是否在运行目标 solution.py。"""

        try:
            parts = shlex.split(command)
        except ValueError:
            parts = command.split()

        working_dir = getattr(self.workspace, "working_dir", None)
        workspace_dir = (
            Path(working_dir).resolve()
            if isinstance(working_dir, (str, Path))
            else None
        )
        expected_path = solution_path.resolve() if solution_path is not None else None

        for part in parts:
            if not part.endswith(".py"):
                continue
            candidate = Path(part)
            if not candidate.is_absolute() and workspace_dir is not None:
                candidate = (workspace_dir / candidate).resolve()
            elif candidate.is_absolute():
                candidate = candidate.resolve()

            if expected_path is not None and candidate == expected_path:
                return True
            if (
                expected_path is None
                and candidate.name == self.config.solution_file_name
            ):
                return True

        return False

    def _fill_exec_fact_from_runtime_artifacts(
        self,
        exec_fact: dict[str, Any],
    ) -> dict[str, Any]:
        """使用运行时工件补全缺失的 stdout/stderr。"""

        if self.workspace is None or not hasattr(
            self.workspace, "read_runtime_artifact"
        ):
            return exec_fact

        read_artifact = self.workspace.read_runtime_artifact
        if not callable(read_artifact):
            return exec_fact

        filled_fact = dict(exec_fact)
        if filled_fact.get("stdout") in (None, ""):
            filled_fact["stdout"] = read_artifact("stdout.log")
        if filled_fact.get("stderr") in (None, ""):
            filled_fact["stderr"] = read_artifact("stderr.log")

        metrics = self._load_metrics_artifact()
        if metrics is not None:
            filled_fact["metrics"] = metrics

        return filled_fact

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
        """从 stdout 中抽取指标。"""

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

        patterns = {
            "val_metric_name": [
                r"val_metric_name\s*[:=]\s*([A-Za-z0-9_./-]+)",
                r"metric_name\s*[:=]\s*([A-Za-z0-9_./-]+)",
            ],
            "val_metric_value": [
                r"val_metric_value\s*[:=]\s*([-+]?\d+(?:\.\d+)?)",
                r"metric_value\s*[:=]\s*([-+]?\d+(?:\.\d+)?)",
            ],
            "val_metric_direction": [
                r"val_metric_direction\s*[:=]\s*(maximize|max|minimize|min)",
                r"metric_direction\s*[:=]\s*(maximize|max|minimize|min)",
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
                Path(workspace_data_dir).expanduser().resolve() / "sample_submission.csv"
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
