"""MLE-Bench test_score 获取模块。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from core.utils.utils import utc_now_iso

if TYPE_CHECKING:
    from mlebench.grade_helpers import CompetitionReport

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GradingConfig:
    """评分配置。"""

    enabled: bool = True
    competition_id: str | None = None
    competition_root_dir: str | Path | None = None
    public_data_dir: str | Path | None = None
    mlebench_data_dir: str | Path | None = None
    competition_dir: str | Path | None = None
    accepted_statuses: tuple[str, ...] = ("completed", "success")


@dataclass(frozen=True, slots=True)
class GradingResult:
    """归一化后的 MLE-Bench 评分结果。"""

    competition_id: str
    test_score: float
    test_score_direction: str
    test_valid_submission: bool
    test_medal_level: str
    test_above_median: bool
    gold_threshold: float | None
    silver_threshold: float | None
    bronze_threshold: float | None
    median_threshold: float | None
    graded_at: str


def resolve_competition_root(competition_dir: str | Path) -> Path:
    """将任意竞赛路径归一化到 competition root。"""

    path = Path(competition_dir).expanduser().resolve()

    if path.name in {"public", "private"} and path.parent.name == "prepared":
        return path.parent.parent
    if path.name == "prepared":
        return path.parent
    if (path / "prepared").exists():
        return path

    raise ValueError(f"无法从路径推断 competition root: {path}")


def infer_competition_id(competition_dir: str | Path) -> str:
    """从竞赛路径推断 competition_id。"""

    return resolve_competition_root(competition_dir).name


def infer_data_dir(competition_dir: str | Path) -> Path:
    """从竞赛路径推断 MLE-Bench data 根目录。"""

    return resolve_competition_root(competition_dir).parent


def _get_medal_level(report: CompetitionReport) -> str:
    """将 CompetitionReport 的奖牌字段归一化。"""

    if report.gold_medal:
        return "gold"
    if report.silver_medal:
        return "silver"
    if report.bronze_medal:
        return "bronze"
    if report.above_median:
        return "above_median"
    return "none"


def report_to_result(report: CompetitionReport) -> GradingResult:
    """将 CompetitionReport 转换为结构化结果。"""

    return GradingResult(
        competition_id=report.competition_id,
        test_score=float(report.score),
        test_score_direction="min" if report.is_lower_better else "max",
        test_valid_submission=bool(report.valid_submission),
        test_medal_level=_get_medal_level(report),
        test_above_median=bool(report.above_median),
        gold_threshold=float(report.gold_threshold)
        if report.gold_threshold is not None
        else None,
        silver_threshold=float(report.silver_threshold)
        if report.silver_threshold is not None
        else None,
        bronze_threshold=float(report.bronze_threshold)
        if report.bronze_threshold is not None
        else None,
        median_threshold=float(report.median_threshold)
        if report.median_threshold is not None
        else None,
        graded_at=utc_now_iso(),
    )


def grade_submission(
    submission_path: str | Path,
    competition_id: str,
    data_dir: str | Path,
) -> GradingResult | None:
    """调用 MLE-Bench API 对 submission.csv 进行评分。"""

    try:
        from mlebench.grade import grade_csv
        from mlebench.registry import Registry
    except ImportError:
        logger.warning("mlebench 未安装，跳过 test_score 评分")
        return None

    submission_file = Path(submission_path).expanduser().resolve()
    if not submission_file.exists():
        logger.warning("submission.csv 不存在，跳过评分: %s", submission_file)
        return None

    try:
        registry = Registry(data_dir=Path(data_dir).expanduser().resolve())
        competition = registry.get_competition(competition_id)
        report = grade_csv(submission_file, competition)
    except Exception:
        logger.exception("MLE-Bench 评分失败: competition_id=%s", competition_id)
        return None

    return report_to_result(report)


def format_grading_result(result: GradingResult) -> str:
    """将评分结果格式化为可读日志文本。"""

    medal_map = {
        "gold": "金牌",
        "silver": "银牌",
        "bronze": "铜牌",
        "above_median": "高于中位数",
        "none": "无奖牌",
    }
    direction = "↓" if result.test_score_direction == "min" else "↑"

    return (
        "\n"
        + "=" * 60
        + "\nMLE-Bench 评分结果\n"
        + "=" * 60
        + f"\n  竞赛 ID: {result.competition_id}"
        + f"\n  test_score: {result.test_score:.5f} {direction}"
        + f"\n  奖牌: {medal_map.get(result.test_medal_level, '未知')}"
        + f"\n  高于中位数: {'是' if result.test_above_median else '否'}"
        + f"\n  有效提交: {'是' if result.test_valid_submission else '否'}"
        + f"\n  阈值: 金={_format_threshold(result.gold_threshold)},"
        + f" 银={_format_threshold(result.silver_threshold)},"
        + f" 铜={_format_threshold(result.bronze_threshold)},"
        + f" 中位数={_format_threshold(result.median_threshold)}"
        + f"\n  评分时间: {result.graded_at}"
        + "\n"
        + "=" * 60
    )


def _format_threshold(value: float | None) -> str:
    """格式化阈值。"""

    if value is None:
        return "N/A"
    return f"{value:.5f}"


def grade_solution_submission(
    submission_path: str | Path,
    competition_dir: str | Path,
) -> GradingResult | None:
    """对单个 solution 的 submission.csv 执行评分。"""

    competition_id = infer_competition_id(competition_dir)
    data_dir = infer_data_dir(competition_dir)
    return grade_submission(
        submission_path=submission_path,
        competition_id=competition_id,
        data_dir=data_dir,
    )


def _resolve_context_value(context: object, name: str) -> object | None:
    """从 hook context 或其 solution 中读取字段。"""

    if hasattr(context, name):
        return getattr(context, name)

    solution = getattr(context, "solution", None)
    if solution is not None and hasattr(solution, name):
        return getattr(solution, name)

    if solution is not None:
        metadata = getattr(solution, "metadata", None)
        if isinstance(metadata, dict) and name in metadata:
            return metadata[name]

    return None


def _resolve_competition_dir(
    context: object,
    config: GradingConfig,
) -> Path | None:
    """从 config 或 context 中解析竞赛目录。"""

    for value in (
        config.competition_root_dir,
        config.public_data_dir,
        config.competition_dir,
    ):
        if value is not None:
            return Path(value).expanduser().resolve()

    for key in ("competition_root_dir", "public_data_dir", "competition_dir"):
        value = _resolve_context_value(context, key)
        if value:
            return Path(value).expanduser().resolve()

    return None


def _resolve_competition_id(
    context: object,
    config: GradingConfig,
) -> str | None:
    """优先从显式上下文解析 competition_id。"""

    if config.competition_id:
        return str(config.competition_id)

    value = _resolve_context_value(context, "competition_id")
    if value:
        return str(value)

    competition_dir = _resolve_competition_dir(context, config)
    if competition_dir is None:
        return None
    return infer_competition_id(competition_dir)


def _resolve_mlebench_data_dir(
    context: object,
    config: GradingConfig,
) -> Path | None:
    """优先从显式上下文解析 MLE-Bench data 根目录。"""

    for value in (config.mlebench_data_dir, _resolve_context_value(context, "mlebench_data_dir")):
        if value:
            return Path(value).expanduser().resolve()

    competition_dir = _resolve_competition_dir(context, config)
    if competition_dir is None:
        return None
    return infer_data_dir(competition_dir)


def _resolve_submission_file_path(context: object) -> Path | None:
    """从 hook context 中解析 submission.csv 路径。"""

    value = _resolve_context_value(context, "submission_file_path")
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _resolve_submission_validated(context: object) -> bool | None:
    """从 hook context 中解析 submission 校验状态。"""

    value = _resolve_context_value(context, "submission_validated")
    if value is None:
        return None
    return bool(value)


def _resolve_status(context: object) -> str | None:
    """从 hook context 中解析 solution 状态。"""

    value = _resolve_context_value(context, "status")
    if value is None:
        return None
    return str(value)


def _resolve_solution_id(context: object) -> str:
    """从 hook context 中解析 solution_id。"""

    value = _resolve_context_value(context, "solution_id")
    if value:
        return str(value)
    return "unknown"


def _attach_result_to_solution(context: object, result: GradingResult) -> None:
    """将 test_score 相关字段挂到 solution.metadata。"""

    solution = getattr(context, "solution", None)
    if solution is None:
        return

    metadata = getattr(solution, "metadata", None)
    if not isinstance(metadata, dict):
        return

    metadata.update(
        {
            "test_score": result.test_score,
            "test_score_direction": result.test_score_direction,
            "test_valid_submission": result.test_valid_submission,
            "test_medal_level": result.test_medal_level,
            "test_above_median": result.test_above_median,
            "test_competition_id": result.competition_id,
            "test_gold_threshold": result.gold_threshold,
            "test_silver_threshold": result.silver_threshold,
            "test_bronze_threshold": result.bronze_threshold,
            "test_median_threshold": result.median_threshold,
            "test_graded_at": result.graded_at,
        }
    )


class MLEBenchGradingHook:
    """在 hook 链路中为 solution 补采 test_score。"""

    def __init__(self, config: GradingConfig | None = None) -> None:
        """初始化评分 hook。"""

        self.config = config or GradingConfig()

    def __call__(self, context: object) -> GradingResult | None:
        """执行评分逻辑。"""

        if not self.config.enabled:
            return None

        solution_id = _resolve_solution_id(context)
        status = _resolve_status(context)
        if status not in self.config.accepted_statuses:
            logger.debug(
                "solution 不满足评分状态要求，跳过: solution_id=%s, status=%s",
                solution_id,
                status,
            )
            return None

        submission_file_path = _resolve_submission_file_path(context)
        if submission_file_path is None:
            logger.debug("submission.csv 缺失，跳过评分: solution_id=%s", solution_id)
            return None
        submission_validated = _resolve_submission_validated(context)
        if submission_validated is False:
            logger.debug(
                "submission.csv 未通过校验，跳过评分: solution_id=%s",
                solution_id,
            )
            return None

        competition_dir = _resolve_competition_dir(context, self.config)
        competition_id = _resolve_competition_id(context, self.config)
        data_dir = _resolve_mlebench_data_dir(context, self.config)
        if competition_id is None or data_dir is None:
            logger.debug(
                "评分上下文缺失，跳过评分: solution_id=%s, competition_id=%s, data_dir=%s",
                solution_id,
                competition_id,
                data_dir,
            )
            return None

        try:
            result = grade_submission(
                submission_path=submission_file_path,
                competition_id=competition_id,
                data_dir=data_dir,
            )
        except ValueError:
            logger.exception(
                "竞赛路径解析失败，跳过评分: solution_id=%s, competition_dir=%s",
                solution_id,
                competition_dir,
            )
            return None

        if result is None:
            logger.warning("test_score 评分失败: solution_id=%s", solution_id)
            return None

        _attach_result_to_solution(context, result)
        logger.info(format_grading_result(result))
        return result


def create_grading_hook(
    enabled: bool = True,
    competition_dir: str | Path | None = None,
    *,
    competition_id: str | None = None,
    competition_root_dir: str | Path | None = None,
    public_data_dir: str | Path | None = None,
    mlebench_data_dir: str | Path | None = None,
) -> MLEBenchGradingHook:
    """创建可复用的 MLE-Bench 评分 hook。"""

    return MLEBenchGradingHook(
        GradingConfig(
            enabled=enabled,
            competition_id=competition_id,
            competition_root_dir=competition_root_dir,
            public_data_dir=public_data_dir,
            mlebench_data_dir=mlebench_data_dir,
            competition_dir=competition_dir,
        )
    )
