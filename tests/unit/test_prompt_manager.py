"""PromptManager 模板加载测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.prompts.manager import PromptManager


def _build_prompt_manager() -> PromptManager:
    """构造指向仓库内配置目录的 PromptManager。"""

    base_dir = Path(__file__).resolve().parents[2] / "config" / "prompts"
    return PromptManager(
        template_dir=base_dir / "templates",
        fragments_dir=base_dir / "fragments",
        spec_path=base_dir / "prompt_spec.yaml",
    )


def _build_draft_context() -> dict[str, Any]:
    """构造 Draft 模板渲染所需的最小上下文。"""

    return {
        "solution": {
            "id": "solution-1",
            "status": "running",
            "plan_summary": "使用最小 baseline 方案。",
            "execute_summary": "已完成一次训练与验证。",
            "genes": {
                "MODEL": {
                    "target": "训练一个轻量基线模型",
                }
            },
            "metrics": {
                "metric_name": "accuracy",
                "metric_value": 0.75,
                "metric_direction": "max",
            },
            "fitness": 0.75,
        },
        "task_spec": {
            "task_type": "tabular_ml",
            "competition_name": "demo",
            "objective": "maximize accuracy",
            "metric_name": "accuracy",
            "metric_direction": "max",
        },
        "schema": {
            "task_type": "tabular_ml",
            "slots": {
                "MODEL": {
                    "function_name": "build_model",
                    "params": [
                        {"name": "features", "type": "DataFrame"},
                    ],
                    "return_type": "Model",
                }
            },
        },
        "workspace": {
            "workspace_root": "/tmp/herald",
            "data_dir": "/tmp/herald/data",
            "working_dir": "/tmp/herald/work",
            "logs_dir": "/tmp/herald/logs",
            "db_path": "/tmp/herald/herald.db",
        },
        "execution_log": "训练完成，得到基线分数。",
        "recent_error": "无",
        "template_content": "def build_model():\n    pass",
        "allowed_tools": ["Bash", "Read"],
        "agent": {
            "name": "draft-agent",
            "display_name": "Draft Agent",
            "prompt_text": "优先保证 MVP 跑通。",
        },
    }


def test_prompt_manager_can_load_draft_template_specs() -> None:
    """`PromptManager` 能读取三份 Draft 模板配置。"""

    manager = _build_prompt_manager()

    for phase in ("plan", "execute", "summarize"):
        template_spec = manager.get_template_spec("draft", phase)
        assert template_spec["static_fragments"] == ["system_context"]
        assert isinstance(template_spec["required_context"], list)
        assert isinstance(template_spec["artifacts"], list)


def test_prompt_manager_can_render_all_draft_templates() -> None:
    """`PromptManager` 能渲染三份 Draft 模板。"""

    manager = _build_prompt_manager()
    context = _build_draft_context()

    expected_stage_markers = {
        "plan": "draft_plan",
        "execute": "draft_execute",
        "summarize": "draft_summarize",
    }

    for phase, expected_marker in expected_stage_markers.items():
        prompt = manager.build_prompt("draft", phase, context)
        assert expected_marker in prompt
        assert "全局系统规则" in prompt


def test_system_context_has_no_overengineering_rule() -> None:
    """system_context 不含与金牌目标冲突的规则。"""

    fragment_path = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "prompts"
        / "fragments"
        / "system_context.md"
    )
    content = fragment_path.read_text(encoding="utf-8")

    assert "过度工程化" not in content
    assert "持续优化" in content or "最佳分数" in content
    assert "禁止抄袭" in content


def test_draft_execute_has_tools_and_format() -> None:
    """draft_execute.j2 含可用工具清单和强制输出格式。"""

    manager = _build_prompt_manager()
    context = _build_draft_context()

    prompt = manager.build_prompt("draft", "execute", context)

    assert "可用工具" in prompt
    assert "执行报告" in prompt
    assert "代码实现" in prompt
    assert "验证结果" in prompt
