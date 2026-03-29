"""FeatureExtract -> Draft 两阶段链路集成测试。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.agent.registry import AgentRegistry
from core.events import EventBus, setup_task_dispatcher
from core.pes.config import load_pes_config
from core.pes.draft import DraftPES
from core.pes.feature_extract import FeatureExtractPES
from core.pes.registry import PESRegistry
from core.prompts.manager import PromptManager
from core.scheduler import Scheduler
from core.workspace import Workspace


def setup_function() -> None:
    """每个测试前重置全局单例。"""

    EventBus.reset()
    AgentRegistry.reset()
    PESRegistry.reset()


@dataclass(slots=True)
class DummyResponse:
    """测试用模型响应。"""

    result: str
    turns: list[dict[str, object]]
    model: str = "dummy-model"
    tokens_in: int = 1
    tokens_out: int = 1
    cost_usd: float | None = None
    duration_ms: int = 0
    session_id: str | None = None


class SequencedLLM:
    """按顺序返回预设响应并记录 Prompt。"""

    def __init__(
        self,
        responses: list[str],
        execute_code: str | None = None,
    ) -> None:
        """初始化测试桩。"""

        self.responses = responses
        self.execute_code = execute_code
        self.calls: list[dict[str, object]] = []
        self._index = 0

    async def execute_task(self, prompt: str, **kwargs: object) -> DummyResponse:
        """返回当前序号的响应。"""

        self.calls.append({"prompt": prompt, **kwargs})
        turns: list[dict[str, object]] = []
        if (
            self.execute_code is not None
            and isinstance(kwargs.get("cwd"), str)
            and "draft_execute" in prompt
        ):
            working_dir = Path(kwargs["cwd"])
            (working_dir / "solution.py").write_text(
                self.execute_code,
                encoding="utf-8",
            )
            (working_dir / "submission.csv").write_text(
                "id,target\n3,0.8\n",
                encoding="utf-8",
            )
            (working_dir / "metrics.json").write_text(
                '{"val_metric_name":"auc","val_metric_value":0.5,"val_metric_direction":"max"}',
                encoding="utf-8",
            )
            turns = [
                {
                    "role": "assistant",
                    "text": "已执行 solution.py。",
                    "tool_calls": [
                        {
                            "name": "Bash",
                            "input": {"command": "python solution.py"},
                            "result": {
                                "stdout": (
                                    "ok\n"
                                    '{"val_metric_name":"auc",'
                                    '"val_metric_value":0.5,'
                                    '"val_metric_direction":"max"}\n'
                                ),
                                "stderr": "",
                                "exit_code": 0,
                                "duration_ms": 15,
                            },
                        }
                    ],
                }
            ]
        result = self.responses[self._index]
        self._index += 1
        return DummyResponse(result=result, turns=turns)


def _build_prompt_manager() -> PromptManager:
    """构造真实 PromptManager。"""

    base_dir = Path(__file__).resolve().parents[2] / "config" / "prompts"
    return PromptManager(
        template_dir=base_dir / "templates",
        fragments_dir=base_dir / "fragments",
        spec_path=base_dir / "prompt_spec.yaml",
    )


def _build_competition_dir(tmp_path: Path) -> Path:
    """构造最小竞赛目录。"""

    competition_dir = tmp_path / "competition"
    competition_dir.mkdir(parents=True, exist_ok=True)
    (competition_dir / "train.csv").write_text(
        "id,feature,target\n1,0.1,0\n2,0.2,1\n",
        encoding="utf-8",
    )
    (competition_dir / "test.csv").write_text(
        "id,feature\n3,0.3\n",
        encoding="utf-8",
    )
    (competition_dir / "sample_submission.csv").write_text(
        "id,target\n3,0\n",
        encoding="utf-8",
    )
    (competition_dir / "description.md").write_text(
        "# Demo Competition\n\nmetric: auc\n",
        encoding="utf-8",
    )
    return competition_dir


def _make_feature_extract_execute_response() -> str:
    """构造 FeatureExtract execute 阶段的结构化输出。"""

    payload = {
        "task_spec": {
            "task_type": "tabular",
            "competition_name": "demo-competition",
            "objective": "predict target",
            "metric_name": "auc",
            "metric_direction": "maximize",
        },
        "data_profile": "训练集 2 行，1 个数值特征，无缺失值，目标列为 target。",
        "genome_template": "tabular",
    }
    return f"分析完成。\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"


def test_feature_extract_output_flows_to_draft_context(tmp_path: Path) -> None:
    """Scheduler 能把 FeatureExtract 产出注入 DraftPES。"""

    competition_dir = _build_competition_dir(tmp_path)
    workspace = Workspace(tmp_path / "workspace")
    workspace.create(competition_dir)
    setup_task_dispatcher()

    feature_extract_llm = SequencedLLM(
        responses=[
            "先看 description、train.csv 和 sample_submission.csv。",
            _make_feature_extract_execute_response(),
            "数据是标准 tabular 二分类任务。",
        ]
    )
    draft_llm = SequencedLLM(
        responses=[
            "总体策略：先做最小 baseline。",
            "## 执行报告\n实现完成。\n\n## 代码实现\n```python\nprint('ok')\n```\n\n## 验证结果\n- 指标名: auc\n- 指标值: 0.50\n- 提交路径: ./submission.csv",
            "总结：baseline 已生成。",
        ],
        execute_code=(
            "def solve() -> None:\n"
            "    print('ok')\n"
            "\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    solve()\n"
        ),
    )

    feature_extract_pes = FeatureExtractPES(
        config=load_pes_config("config/pes/feature_extract.yaml"),
        llm=feature_extract_llm,
        workspace=workspace,
        runtime_context={
            "competition_dir": str(competition_dir),
            "run_id": "run-001",
        },
        prompt_manager=_build_prompt_manager(),
    )
    draft_pes = DraftPES(
        config=load_pes_config("config/pes/draft.yaml"),
        llm=draft_llm,
        workspace=workspace,
        runtime_context={
            "competition_dir": str(competition_dir),
            "run_id": "run-001",
        },
        prompt_manager=_build_prompt_manager(),
    )

    scheduler = Scheduler(
        competition_dir=str(competition_dir),
        max_tasks=1,
        context={"run_id": "run-001"},
        task_stages=[("feature_extract", 1), ("draft", 1)],
    )
    scheduler.run()

    assert feature_extract_pes.received_execute_event is not None
    assert draft_pes.received_execute_event is not None
    assert (
        draft_pes.received_execute_event.context["task_spec"]["task_type"] == "tabular"
    )
    assert "训练集 2 行" in draft_pes.received_execute_event.context["data_profile"]
    assert draft_pes.received_execute_event.context["schema"].task_type == "tabular"
    assert (
        "def build_model(config: dict[str, object])"
        in draft_pes.received_execute_event.context["template_content"]
    )
    assert "训练集 2 行" in str(draft_llm.calls[0]["prompt"])
    assert "数据概况" in str(draft_llm.calls[0]["prompt"])
    assert "训练集 2 行" in str(draft_llm.calls[1]["prompt"])
    assert workspace.read_working_solution().startswith("def solve()")
