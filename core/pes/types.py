"""PES 运行期核心数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


def _get_metric_field(
    metrics: dict[str, Any] | None,
    canonical_key: str,
    legacy_key: str,
) -> object | None:
    """从指标字典中按新旧键顺序读取字段。"""

    if metrics is None:
        return None
    if canonical_key in metrics:
        return metrics.get(canonical_key)
    return metrics.get(legacy_key)


def _build_metric_aliases(metrics: dict[str, Any] | None) -> dict[str, Any] | None:
    """为 Prompt 和持久化构造带新旧别名的指标字典。"""

    if metrics is None:
        return None

    metric_name = _get_metric_field(metrics, "val_metric_name", "metric_name")
    metric_value = _get_metric_field(metrics, "val_metric_value", "metric_value")
    metric_direction = _get_metric_field(
        metrics,
        "val_metric_direction",
        "metric_direction",
    )

    aliased_metrics = dict(metrics)
    aliased_metrics["val_metric_name"] = metric_name
    aliased_metrics["val_metric_value"] = metric_value
    aliased_metrics["val_metric_direction"] = metric_direction
    aliased_metrics["metric_name"] = metric_name
    aliased_metrics["metric_value"] = metric_value
    aliased_metrics["metric_direction"] = metric_direction
    return aliased_metrics


def _to_plain_data(value: object) -> object:
    """将复杂对象递归转换为可序列化的基础结构。"""

    if is_dataclass(value):
        return {key: _to_plain_data(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain_data(item) for item in value]
    return value


@dataclass(slots=True)
class PESSolution:
    """PES 运行中的方案状态。"""

    id: str
    operation: str
    generation: int
    status: str
    created_at: str
    parent_ids: list[str]
    lineage: str | None
    run_id: str | None
    finished_at: str | None = None
    target_slot: str | None = None
    workspace_dir: str | None = None
    solution_file_path: str | None = None
    submission_file_path: str | None = None
    plan_summary: str = ""
    execute_summary: str = ""
    summarize_insight: str = ""
    genes: dict[str, dict[str, Any]] = field(default_factory=dict)
    metrics: dict[str, Any] | None = None
    fitness: float | None = None
    phase_outputs: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """转换为数据库可消费的字典结构。"""

        metric_name = _get_metric_field(self.metrics, "val_metric_name", "metric_name")
        metric_value = _get_metric_field(
            self.metrics,
            "val_metric_value",
            "metric_value",
        )
        metric_direction = _get_metric_field(
            self.metrics,
            "val_metric_direction",
            "metric_direction",
        )

        return {
            "id": self.id,
            "generation": self.generation,
            "lineage": self.lineage,
            "schema_task_type": self.metadata.get("schema_task_type"),
            "operation": self.operation,
            "mutated_slot": self.target_slot,
            "parent_ids": self.parent_ids,
            "fitness": self.fitness,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "metric_direction": metric_direction,
            "run_id": self.run_id,
            "workspace_dir": self.workspace_dir,
            "solution_file_path": self.solution_file_path,
            "submission_file_path": self.submission_file_path,
            "plan_summary": self.plan_summary,
            "execute_summary": self.execute_summary,
            "summarize_insight": self.summarize_insight,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }

    def to_prompt_payload(self) -> dict[str, Any]:
        """转换为 Prompt 可消费的轻量上下文。"""

        payload = _to_plain_data(self)
        payload["metrics"] = _build_metric_aliases(self.metrics)
        return payload
