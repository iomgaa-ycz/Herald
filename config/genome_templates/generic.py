"""通用任务 Genome 模板。"""

from __future__ import annotations

import json
import os
import sys

DATA_DIR = os.environ["HERALD_DATA_DIR"]


# === GENE:DATA_START ===
def load_data(config: dict[str, object]) -> dict[str, object]:
    """从 DATA_DIR 读取任务输入。"""
    pass  # LLM 填充


# === GENE:DATA_END ===


# === GENE:PROCESS_START ===
def process(
    data: dict[str, object],
    config: dict[str, object],
) -> dict[str, object]:
    """把原始数据处理为模型可消费的结构。"""
    pass  # LLM 填充


# === GENE:PROCESS_END ===


# === GENE:MODEL_START ===
def build_model(config: dict[str, object]) -> object:
    """构建任务模型或推理器。"""
    pass  # LLM 填充


# === GENE:MODEL_END ===


# === GENE:POSTPROCESS_START ===
def build_postprocess(config: dict[str, object]) -> dict[str, object]:
    """返回预测函数与结果格式化函数。"""
    pass  # LLM 填充


# === GENE:POSTPROCESS_END ===


# === FIXED:EVALUATE ===
def evaluate(raw_output: object, config: dict[str, object]) -> dict[str, object]:
    """汇总通用任务的运行结果。"""
    del raw_output, config
    return {}


# === FIXED:EVALUATE_END ===


# === FIXED:MAIN ===
def main(config: dict[str, object]) -> dict[str, object]:
    """最小通用任务主流程骨架。"""
    data = load_data(config)
    processed = process(data, config)
    model = build_model(config)

    postprocess = build_postprocess(config)
    raw_output = postprocess["predict_fn"](model, processed)
    formatted_output = postprocess["format_output"](raw_output)

    output_path = os.path.join(os.getcwd(), "submission.csv")
    if hasattr(formatted_output, "to_csv"):
        formatted_output.to_csv(output_path, index=False)

    return {
        "result": evaluate(raw_output, config),
        "output_path": output_path,
    }


# === FIXED:MAIN_END ===


# === FIXED:ENTRY ===
if __name__ == "__main__":
    runtime_config = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(main(runtime_config), ensure_ascii=False))


# === FIXED:ENTRY_END ===
